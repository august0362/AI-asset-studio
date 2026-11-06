"""Batch execution (docs/v2/TEST_PLAN.md §4, B-01…B-12) with the mock adapter and the mock compute client."""

from __future__ import annotations

import pytest

from models.registry import MOCK_CAPABILITIES, ModelRegistry
from tests.character_helpers import API, Driver, rid, s2, s4, s5_items
from tests.conftest import codes, request_body


def logs(harness, job_id: str) -> list[str]:
    page = harness.client.get(f"{API}/jobs/{job_id}/logs?limit=1000").json()
    return [line["text"] for line in page["lines"]]


def job(harness, job_id: str) -> dict:
    return harness.client.get(f"{API}/jobs/{job_id}").json()


def job_count(harness) -> int:
    return len(harness.client.get(f"{API}/jobs?limit=200").json()["jobs"])


def alt_registry() -> ModelRegistry:
    """The mocks plus a second Text→2D mock with the same options, so preview and production can differ (B-09)."""
    basic = next(m for m in MOCK_CAPABILITIES if m.model_id == "mock-t2d-basic")
    alt = basic.model_copy(update={"model_id": "mock-t2d-alt", "display_name": "Mock Alt Text→2D"})
    return ModelRegistry([*MOCK_CAPABILITIES, alt])


@pytest.fixture
def driver(harness) -> Driver:
    return Driver(harness)


def test_b01_one_model_load_per_job(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    assert manifest["status"] == "ready" and manifest["expected_model_loads"] == len(manifest["groups"]) == 1
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    assert len(done["attempts"]) == 1
    lines = logs(harness, done["attempts"][0]["job_id"])
    assert sum(1 for line in lines if line.startswith("MODEL_LOAD ")) == 1
    assert sum(1 for line in lines if line.startswith("TASK_START ")) == 4
    # The S3 preview batch was another model run: another job, another load.
    preview = next(b for b in driver.detail(cid, "s3")["batches"])
    assert (
        sum(1 for line in logs(harness, preview["attempts"][0]["job_id"]) if line.startswith("MODEL_LOAD "))
        == 1
    )


def test_b02_manifest_is_bound_to_the_approved_revisions(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    s4_detail = driver.detail(cid, "s4")
    approved = s4_detail["approved_revision"]
    assert manifest["approved_spec_revision"] == approved["source_revisions"]["s2"] == 1
    assert manifest["prompt_set_revision"] == approved["revision"]
    assert manifest["concept_revision"] == approved["source_revisions"]["s3"]
    fields = ("task_id", "purpose", "prompt", "negative_prompt", "seed", "width", "height")
    assert [{k: t[k] for k in fields} for t in manifest["tasks"]] == [
        {k: t[k] for k in fields} for t in approved["content"]["tasks"]
    ]
    before = job_count(harness)
    driver.approve(cid, "s2", s2(hair="Long silver hair with icy-blue ends"))  # S2 r2
    response = harness.client.post(
        f"{API}/characters/{cid}/batches/{manifest['manifest_id']}/submit",
        json={
            "contract_version": "1.1",
            "client_request_id": rid(),
            "compute": {"profile_id": "default", "accelerator_id": "auto"},
        },
    )
    assert response.status_code == 409 and codes(response.json()["errors"]) == ["BATCH_MANIFEST_STALE"]
    assert "s2_reapproved" in response.json()["errors"][0]["details"]["reasons"]
    assert job_count(harness) == before


def test_b03_no_production_or_preview_before_approval(harness, driver):
    cid = driver.create()
    response = driver.preview(cid, expect=422)
    assert (
        codes(response["errors"]) == ["STAGE_BLOCKED"]
        and response["errors"][0]["details"]["stage_id"] == "s2"
    )
    manifest = driver.through_s4(cid)
    before = job_count(harness)
    driver.save(cid, "s4", s4(), None)
    driver.decide(cid, "s4", "submit")  # S4 r2 pending
    stale = driver.submit(cid, manifest["manifest_id"], expect=409)
    assert (
        codes(stale["errors"]) == ["BATCH_MANIFEST_STALE"]
        and "s4_pending" in stale["errors"][0]["details"]["reasons"]
    )
    assert job_count(harness) == before


def test_b04_b05_partial_failure_then_task_level_retry(harness, driver, monkeypatch):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    monkeypatch.setenv("AAS_MOCK_FAIL_TASKS", "side_01")
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    first_job = job(harness, done["attempts"][0]["job_id"])
    assert first_job["status"] == "completed"
    assert codes(first_job["warnings"]) == ["BATCH_PARTIAL"]
    assert first_job["warnings"][0]["details"]["failed"] == ["side_01"]
    assert {r["task_id"]: r["status"] for r in done["results"]} == {
        "fullbody_01": "succeeded",
        "front_01": "succeeded",
        "side_01": "failed",
        "back_01": "succeeded",
    }
    primary = next(a for a in first_job["artifacts"] if a["is_primary"])
    assert primary["task_id"] == "fullbody_01"
    failed = next(r for r in done["results"] if r["task_id"] == "side_01")
    assert (
        failed["error"]["code"] == "BATCH_TASK_FAILED"
        and "Simulated task failure" in failed["error"]["details"]["message"]
    )
    assert done["status"] == "partially_completed" and done["retryable_task_ids"] == ["side_01"]

    monkeypatch.delenv("AAS_MOCK_FAIL_TASKS")
    retried = driver.settle(cid, driver.submit(cid, manifest["manifest_id"], action="retry"))
    assert [a["attempt"] for a in retried["attempts"]] == [1, 2]
    second = retried["attempts"][1]
    assert second["task_ids"] == ["side_01"]
    rendered = [line.split()[1] for line in logs(harness, second["job_id"]) if line.startswith("TASK_START ")]
    assert rendered == ["side_01"]  # the succeeded tasks were never rendered again
    assert retried["status"] == "completed" and retried["retryable_task_ids"] == []
    side = next(r for r in retried["results"] if r["task_id"] == "side_01")
    assert side["attempt"] == 2 and side["job_id"] == second["job_id"]
    nothing = driver.submit(cid, manifest["manifest_id"], action="retry", expect=409)
    assert codes(nothing["errors"]) == ["BATCH_NOTHING_TO_RETRY"]


def test_b06_deadline_marks_the_rest_not_run_and_keeps_finished_images(harness, driver, monkeypatch):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    monkeypatch.setenv("AAS_MOCK_TASK_SECONDS", "0.3")
    monkeypatch.setenv("AAS_MOCK_DEADLINE_SECONDS", "0.4")
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    statuses = [r["status"] for r in done["results"]]
    assert statuses == ["succeeded", "not_run", "not_run", "not_run"]
    not_run = done["results"][1]
    assert (
        not_run["error"]["code"] == "BATCH_TASK_NOT_RUN"
        and not_run["error"]["details"]["reason"] == "deadline"
    )
    first = job(harness, done["attempts"][0]["job_id"])
    assert first["status"] == "completed" and len(first["artifacts"]) == 1
    assert done["retryable_task_ids"] == ["front_01", "side_01", "back_01"]


def test_b07_no_lost_results_and_a_failed_job_fails_every_task(harness, driver, monkeypatch):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    record = job(harness, done["attempts"][0]["job_id"])
    by_task = {a["task_id"]: a for a in record["artifacts"]}
    for result in done["results"]:
        assert result["status"] == "succeeded"
        assert by_task[result["task_id"]]["sha256"] == result["sha256"]
        assert by_task[result["task_id"]]["artifact_id"] == result["artifact_id"]

    other = driver.create("Second")
    manifest = driver.through_s4(other)
    monkeypatch.setenv("AAS_MOCK_FAIL_TASKS", "fullbody_01,front_01,side_01,back_01")
    failed = driver.settle(other, driver.submit(other, manifest["manifest_id"]))
    failed_job = job(harness, failed["attempts"][0]["job_id"])
    assert failed_job["status"] == "failed"
    assert failed["status"] == "failed"
    assert {r["error"]["code"] for r in failed["results"]} == {failed_job["error"]["code"]}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_b08_no_invented_telemetry_in_batch_or_stage_payloads(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    keys = (
        _keys(done)
        | _keys(driver.detail(cid, "s5"))
        | _keys(harness.client.get(f"{API}/characters/{cid}").json())
    )
    for word in ("vram", "gpu", "temperature", "utilization", "percent", "similarity", "consistency_score"):
        assert not any(word in k for k in keys), word


def test_b09_preview_and_production_models_may_differ(harness_factory):
    harness = harness_factory(registry=alt_registry())
    driver = Driver(harness)
    cid = driver.create()
    manifest = driver.through_s4(cid, model_id="mock-t2d-alt")
    preview = driver.detail(cid, "s3")["batches"][0]
    assert preview["target_model_id"] == "mock-t2d-basic" and manifest["target_model_id"] == "mock-t2d-alt"
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    assert job(harness, done["attempts"][0]["job_id"])["request"]["model_id"] == "mock-t2d-alt"
    assert job(harness, preview["attempts"][0]["job_id"])["request"]["model_id"] == "mock-t2d-basic"
    frozen = driver.approve(cid, "s5", s5_items(done))["approved_revision"]["frozen_assets"]
    assert {a["source"]["model_id"] for a in frozen} == {"mock-t2d-alt"}
    concept = driver.detail(cid, "s3")["approved_revision"]["frozen_assets"][0]
    assert concept["source"]["model_id"] == "mock-t2d-basic"


def test_b10_an_image_to_3d_model_cannot_be_the_production_model(harness, driver):
    cid = driver.create()
    driver.through_s4(cid)
    content = s4("mock-i3d-single")
    driver.save(cid, "s4", content)
    driver.decide(cid, "s4", "submit")
    response = driver.decide(cid, "s4", "approve", expect=422)
    assert "MODEL_PIPELINE_INCOMPATIBLE" in codes(response["errors"])


def test_b11_v1_retry_of_a_batch_job_is_refused(harness, driver, monkeypatch):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    monkeypatch.setenv("AAS_MOCK_FAIL_TASKS", "fullbody_01,front_01,side_01,back_01")
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    response = harness.client.post(
        f"{API}/jobs/{done['attempts'][0]['job_id']}/retry", json={"client_request_id": rid()}
    )
    assert response.status_code == 409
    error = response.json()["errors"][0]
    assert error["code"] == "JOB_NOT_RETRYABLE" and error["details"]["reason"] == "use_batch_retry"


def test_b12_repeating_a_submit_creates_no_second_job(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    request_id = rid()
    first = driver.submit(cid, manifest["manifest_id"], request_id=request_id)
    count = job_count(harness)
    again = driver.submit(cid, manifest["manifest_id"], request_id=request_id)
    assert again["attempts"] == first["attempts"] and job_count(harness) == count
    other = driver.submit(cid, manifest["manifest_id"], expect=409)
    assert codes(other["errors"]) == ["BATCH_ALREADY_SUBMITTED"]
    preview_id = rid()
    driver.save(cid, "s3", driver.detail(cid, "s3")["draft"]["content"])
    one = driver.preview(cid, request_id=preview_id)
    count = job_count(harness)
    two = driver.preview(cid, request_id=preview_id)
    assert one["manifest_id"] == two["manifest_id"] and job_count(harness) == count


def test_batch_jobs_show_in_v1_job_payloads_with_their_batch_and_task_ids(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    record = job(harness, done["attempts"][0]["job_id"])
    assert record["request"]["prompt"] is None
    assert record["request"]["batch"] == {
        "character_id": cid,
        "manifest_id": manifest["manifest_id"],
        "group_id": "g01",
        "attempt": 1,
        "task_ids": ["fullbody_01", "front_01", "side_01", "back_01"],
    }
    assert [a["task_id"] for a in record["artifacts"]] == ["fullbody_01", "front_01", "side_01", "back_01"]
    plan = record["compute"]["resource_plan"]
    assert plan["estimate_basis"]["estimated_runtime_seconds"] == 30 * 4  # measured per image × tasks
    assert manifest["groups"][0]["estimated_runtime_seconds"] == 120
    normal = harness.client.post(f"{API}/jobs", json=request_body())
    assert normal.json()["request"]["batch"] is None
