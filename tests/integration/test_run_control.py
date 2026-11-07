"""D-041 (CONTRACTS §14): auto-run, held and waiting jobs, the FIFO, session slots, run groups, deletion and cleanup.

Mock compute only; no Kaggle, no GPU.
"""

from __future__ import annotations

import itertools
import json
import time

import pytest

from aas_backend.schemas import BatchRef
from kaggle_connector.client import mock as mock_module
from models.contracts import ModelCapabilities
from models.registry import MOCK_CAPABILITIES, ModelRegistry
from tests.conftest import API, i3d_body, request_body

GIB = 2**30
GROUPABLE = "mock-t2d-group"  # a mock Text→2D record with a known per-GPU need, so it can be grouped


def groupable_registry() -> ModelRegistry:
    base = MOCK_CAPABILITIES[0].model_dump()
    record = {
        **base,
        "model_id": GROUPABLE,
        "display_name": "Mock groupable Text→2D",
        "runtime": {**base["runtime"], "minimum_gpu_vram_bytes": 8 * GIB},
    }
    multi = {
        **record,
        "model_id": "mock-t2d-multigpu",
        "runtime": {**record["runtime"], "multi_gpu": "optional"},
    }
    return ModelRegistry(
        [
            *MOCK_CAPABILITIES,
            ModelCapabilities.model_validate(record),
            ModelCapabilities.model_validate(multi),
        ]
    )


def body(auto_run: bool | None = None, *, model_id: str = "mock-t2d-basic", gpu: bool = False, **extra):
    compute = {"profile_id": "default", "accelerator_id": "gpu_t4x2" if gpu else None}
    payload = request_body(model_id=model_id, compute=compute, **extra)
    if auto_run is not None:
        payload["auto_run"] = auto_run
    return payload


def create(h, payload) -> dict:
    response = h.client.post(f"{API}/jobs", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def get(h, job_id) -> dict:
    return h.client.get(f"{API}/jobs/{job_id}").json()


def logs(h, job_id) -> list[str]:
    return [line["text"] for line in h.client.get(f"{API}/jobs/{job_id}/logs?limit=1000").json()["lines"]]


def wait_for(condition, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


# --- auto-run, held, PATCH (§14.1, §14.2, §14.5) ------------------------------------------------------------------


def test_auto_run_off_holds_the_job_until_turned_on(harness):
    job = create(harness, body(auto_run=False))
    sched = job["scheduling"]
    assert job["status"] == "created" and sched["auto_run"] is False and sched["queue_state"] == "held"
    assert sched["run_requested_at"] is None and sched["queue_position"] is None and sched["group_id"] is None
    time.sleep(0.4)
    assert get(harness, job["job_id"])["status"] == "created"
    summary = harness.client.get(f"{API}/jobs").json()["jobs"][0]
    assert summary["scheduling"]["queue_state"] == "held"

    response = harness.client.patch(f"{API}/jobs/{job['job_id']}", json={"auto_run": True})
    assert response.status_code == 200, response.text
    assert response.json()["scheduling"]["run_requested_at"] is not None
    done = harness.wait(job["job_id"])
    assert done["status"] == "completed"
    assert done["scheduling"]["queue_state"] is None and done["scheduling"]["auto_run"] is True


def test_default_auto_run_runs_at_once_and_keeps_v1_behaviour(harness):
    job = create(harness, body())
    assert (
        job["scheduling"]["auto_run"] is True and job["scheduling"]["run_requested_at"] == job["created_at"]
    )
    assert harness.wait(job["job_id"])["status"] == "completed"


def test_patch_is_refused_once_the_job_started_and_checks_its_body(harness):
    job_id = create(harness, body())["job_id"]
    harness.wait(job_id)
    response = harness.client.patch(f"{API}/jobs/{job_id}", json={"auto_run": False})
    assert response.status_code == 409 and response.json()["errors"][0]["code"] == "JOB_ALREADY_STARTED"
    held = create(harness, body(auto_run=False))["job_id"]
    for bad in ({}, {"auto_run": "yes"}, {"auto_run": True, "extra": 1}):
        response = harness.client.patch(f"{API}/jobs/{held}", json=bad)
        assert response.status_code == 422 and response.json()["errors"][0]["code"] == "REQUEST_FIELD_INVALID"
    again = harness.client.patch(f"{API}/jobs/{held}", json={"auto_run": False})  # idempotent
    assert again.status_code == 200 and again.json()["scheduling"]["queue_state"] == "held"


def test_waiting_jobs_have_fifo_positions_and_can_be_held_again(harness_factory):
    h = harness_factory(run_seconds=1.5)
    first = create(h, body())["job_id"]
    h.wait(first, until=lambda s: s in ("queued", "running"))
    second, third = create(h, body())["job_id"], create(h, body())["job_id"]
    assert [get(h, j)["scheduling"]["queue_position"] for j in (second, third)] == [1, 2]
    assert get(h, second)["scheduling"]["queue_state"] == "waiting"
    held = h.client.patch(f"{API}/jobs/{second}", json={"auto_run": False}).json()
    assert held["scheduling"]["queue_state"] == "held" and held["scheduling"]["run_requested_at"] is None
    assert get(h, third)["scheduling"]["queue_position"] == 1
    # Turned on again, it joins the END of the FIFO: the third job runs first.
    h.client.patch(f"{API}/jobs/{second}", json={"auto_run": True})
    done = {j: h.wait(j, timeout=30) for j in (first, second, third)}
    assert all(job["status"] == "completed" for job in done.values())
    assert done[third]["execution"]["submitted_at"] <= done[second]["execution"]["submitted_at"]


def test_held_and_waiting_jobs_survive_a_restart(harness_factory, tmp_path):
    first = harness_factory(run_seconds=3)
    running = create(first, body())["job_id"]
    first.wait(running, until=lambda s: s in ("queued", "running"))
    waiting = create(first, body())["job_id"]
    held = create(first, body(auto_run=False))["job_id"]
    first.close()

    second = harness_factory(compute=mock_module.MockKaggleClient(remote_root=tmp_path / "remote2"))
    assert second.wait(running)["error"]["code"] == "BACKEND_RESTARTED"  # its mock remote run is gone
    assert second.wait(waiting)["status"] == "completed"  # kept its place and ran (§4 rule 6, v1.2)
    assert get(second, held)["scheduling"]["queue_state"] == "held"
    assert any("still held" in line for line in logs(second, held))


def test_older_job_files_read_as_auto_run_and_ungrouped(harness_factory):
    first = harness_factory()
    job_id = create(first, body())["job_id"]
    first.wait(job_id)
    first.close()
    path = first.data_dir / "jobs" / f"{job_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("scheduling")
    path.write_text(json.dumps(data), encoding="utf-8")
    second = harness_factory(data_dir=first.data_dir)
    sched = get(second, job_id)["scheduling"]
    assert sched == {
        "auto_run": True,
        "queue_state": None,
        "queue_position": None,
        "run_requested_at": data["created_at"],
        "group_id": None,
        "group_job_ids": [],
        "gpu_index": None,
    }


# --- session slots (§14.3) ----------------------------------------------------------------------------------------


def test_two_session_slots_run_two_jobs_at_the_same_time(harness_factory):
    h = harness_factory(run_seconds=1.5, max_parallel_sessions=2)
    a, b = create(h, body())["job_id"], create(h, body())["job_id"]
    assert wait_for(lambda: all(get(h, j)["status"] in ("queued", "running") for j in (a, b)))
    first, second = h.wait(a), h.wait(b)
    assert first["status"] == second["status"] == "completed"
    assert second["execution"]["submitted_at"] < first["execution"]["finished_at"]  # overlapped


def test_one_slot_keeps_strict_fifo(harness_factory):
    h = harness_factory(run_seconds=0.5)
    ids = [create(h, body())["job_id"] for _ in range(3)]
    done = [h.wait(j) for j in ids]
    for previous, following in itertools.pairwise(done):
        assert previous["updated_at"] <= following["execution"]["submitted_at"]


# --- deletion (§14.6) ----------------------------------------------------------------------------------------------


def test_held_and_waiting_jobs_can_be_deleted_running_ones_cannot(harness_factory):
    h = harness_factory(run_seconds=1.5)
    running = create(h, body())["job_id"]
    h.wait(running, until=lambda s: s in ("queued", "running"))
    waiting = create(h, body())["job_id"]
    held = create(h, body(auto_run=False))["job_id"]
    assert (h.data_dir / "jobs" / f"{held}.json").is_file()
    for job_id in (waiting, held):
        assert h.client.delete(f"{API}/jobs/{job_id}").status_code == 204
        assert h.client.get(f"{API}/jobs/{job_id}").status_code == 404
        assert not (h.data_dir / "jobs" / f"{job_id}.json").exists()
    refused = h.client.delete(f"{API}/jobs/{running}")
    assert refused.status_code == 409 and refused.json()["errors"][0]["code"] == "JOB_NOT_TERMINAL"
    h.wait(running)


def test_a_waiting_batch_job_cannot_be_deleted(harness_factory):
    h = harness_factory(run_seconds=1.5)
    running = create(h, body())["job_id"]
    h.wait(running, until=lambda s: s in ("queued", "running"))
    record, _ = h.client.app.state.service.create_batch_job(
        client_request_id="11111111-1111-4111-8111-111111111111",
        model_id="mock-t2d-basic",
        asset_category="character",
        tasks=[("front_01", "A ranger front view", {"width": 512, "height": 512, "seed": 42})],
        compute={"profile_id": "default", "accelerator_id": None},
        batch=BatchRef(
            character_id="chr_111111111111",
            manifest_id="bat_111111111111",
            group_id="grp_01",
            attempt=1,
            task_ids=["front_01"],
        ),
    )
    response = h.client.delete(f"{API}/jobs/{record.job_id}")
    assert response.status_code == 409 and response.json()["errors"][0]["code"] == "JOB_NOT_TERMINAL"
    assert h.wait(record.job_id)["status"] == "completed"


def test_bulk_delete_reports_a_result_for_every_job(harness_factory):
    h = harness_factory(run_seconds=1.5)
    done = create(h, body())["job_id"]
    h.wait(done)
    running = create(h, body())["job_id"]
    h.wait(running, until=lambda s: s in ("queued", "running"))
    held = create(h, body(auto_run=False))["job_id"]
    unknown = "job_20261106T101500Z_a1b2c3"
    response = h.client.post(f"{API}/jobs/delete", json={"job_ids": [done, held, running, unknown, "bad"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["contract_version"] == "1.0" and result["deleted"] == [done, held]
    assert result["refused"] == [
        {"job_id": running, "code": "JOB_NOT_TERMINAL"},
        {"job_id": unknown, "code": "JOB_NOT_FOUND"},
        {"job_id": "bad", "code": "JOB_NOT_FOUND"},
    ]
    for bad in ({"job_ids": []}, {"job_ids": [done, done]}, {"job_ids": [unknown] * 201}, {"ids": []}):
        assert h.client.post(f"{API}/jobs/delete", json=bad).status_code == 422
    h.wait(running)


# --- kernel cleanup (§14.7) -------------------------------------------------------------------------------------


@pytest.mark.parametrize("failure", ["none", "kernel_error"])
def test_every_terminal_job_is_cleaned_up_remotely(harness_factory, failure):
    h = harness_factory(failure=failure)
    job = h.wait(create(h, body())["job_id"])
    assert job["status"] == ("completed" if failure == "none" else "failed")
    ref = job["execution"]["remote_ref"]
    assert wait_for(lambda: h.compute.released == [(ref, [job["job_id"]])])
    assert wait_for(lambda: any("Remote run cleaned up" in line for line in logs(h, job["job_id"])))


# --- prompts (§14.8) -------------------------------------------------------------------------------------------


def test_prompts_up_to_10000_characters_are_accepted(harness_factory):
    h = harness_factory(registry=groupable_registry())
    caps = h.client.get(f"{API}/catalog").json()["limits"]
    assert caps["prompt_max_length"] == 10_000
    report = h.client.post(f"{API}/validate", json=body(prompt="a" * 1001)).json()
    assert [e["code"] for e in report["errors"]] == ["MODEL_PROMPT_TOO_LONG"]  # the mock's own 1 000 limit


def test_a_coded_remote_error_fails_the_job_with_its_own_code(harness_factory, monkeypatch):
    entry = (
        "class PromptTooLong(Exception):\n"
        "    aas_code = 'MODEL_PROMPT_TOO_LONG'\n"
        "    aas_details = {'tokens': 2300, 'max_tokens': 2048}\n"
        "def main(arguments, input_dir, output_dir, progress):\n"
        "    raise PromptTooLong('The prompt has 2300 tokens; this model reads at most 2048.')\n"
    )
    monkeypatch.setattr(mock_module, "_KERNEL_ERROR_ENTRY", entry)
    h = harness_factory(failure="kernel_error")
    job = h.wait(create(h, body())["job_id"])
    assert job["status"] == "failed" and job["error"]["code"] == "MODEL_PROMPT_TOO_LONG"
    assert job["error"]["details"]["tokens"] == 2300 and job["error"]["details"]["max_tokens"] == 2048
    assert job["error"]["retryable"] is False


# --- run groups (§14.4) -----------------------------------------------------------------------------------------


def held_pair(h, **extra) -> tuple[str, str]:
    return tuple(
        create(h, body(auto_run=False, model_id=GROUPABLE, gpu=True, **extra))["job_id"] for _ in range(2)
    )


def test_a_run_group_runs_two_jobs_in_one_session_with_separate_results(harness_factory):
    h = harness_factory(registry=groupable_registry())
    a, b = held_pair(h)
    response = h.client.post(f"{API}/jobs/groups", json={"job_ids": [a, b]})
    assert response.status_code == 201, response.text
    group = response.json()
    assert group["job_ids"] == [a, b] and group["group_id"].startswith("grp_")
    jobs = [h.wait(a), h.wait(b)]
    assert [j["status"] for j in jobs] == ["completed", "completed"]
    assert jobs[0]["execution"]["remote_ref"] == jobs[1]["execution"]["remote_ref"]
    assert jobs[0]["execution"]["remote_ref"].endswith(group["group_id"])
    assert [j["scheduling"]["gpu_index"] for j in jobs] == [0, 1]
    assert all(j["scheduling"]["group_job_ids"] == [a, b] for j in jobs)
    for mine, other in ((a, b), (b, a)):
        lines = logs(h, mine)
        assert not any(f"[{other}]" in line or f"[{mine}]" in line for line in lines)
        progress = [json.loads(line.split(" ", 1)[1]) for line in lines if line.startswith("AAS_PROGRESS ")]
        assert progress and all(p["job_id"] == mine for p in progress)
        assert (
            h.data_dir / "logs" / f"{mine}.telemetry.jsonl"
        ).is_file()  # the one reporter, stored for both
        assert h.client.get(f"{API}/jobs/{mine}/artifacts").json()["artifacts"]
    ref = jobs[0]["execution"]["remote_ref"]
    assert wait_for(lambda: h.compute.released == [(ref, [a, b])])  # one cleanup, after both ended


def test_one_failed_job_in_a_group_leaves_the_other_unaffected(harness_factory, monkeypatch):
    original = mock_module.MockKaggleClient._execute

    def execute(self, run):
        package = run.sandbox / "package"
        if (package / "entry_1.py").is_file():  # the second job's process fails
            (package / "entry_1.py").write_text(mock_module._KERNEL_ERROR_ENTRY, encoding="utf-8")
        original(self, run)

    monkeypatch.setattr(mock_module.MockKaggleClient, "_execute", execute)
    h = harness_factory(registry=groupable_registry())
    a, b = held_pair(h)
    assert h.client.post(f"{API}/jobs/groups", json={"job_ids": [a, b]}).status_code == 201
    first, second = h.wait(a), h.wait(b)
    assert first["status"] == "completed" and second["status"] == "failed"
    assert second["error"]["code"] == "KAGGLE_KERNEL_ERROR"


def test_group_checks_report_every_reason(harness_factory):
    h = harness_factory(registry=groupable_registry(), run_seconds=1.5)
    a, b = held_pair(h)
    post = lambda ids: h.client.post(f"{API}/jobs/groups", json={"job_ids": ids})  # noqa: E731

    def reason(response):
        assert response.status_code == 422, response.text
        error = response.json()["errors"][0]
        assert error["code"] == "JOB_GROUP_INVALID" and error["field"] == "job_ids"
        return error["details"]["reason"]

    assert reason(post([a])) == "count"
    assert reason(post([a, a])) == "count"
    assert post([a, "job_20261106T101500Z_a1b2c3"]).status_code == 404
    cpu = create(h, body(auto_run=False, model_id=GROUPABLE))["job_id"]
    assert reason(post([a, cpu])) == "accelerator"
    basic = create(h, body(auto_run=False, gpu=True))["job_id"]
    assert reason(post([a, basic])) == "vram"  # mock-t2d-basic has no known GPU memory need
    multi = create(h, body(auto_run=False, model_id="mock-t2d-multigpu", gpu=True))["job_id"]
    assert reason(post([a, multi])) == "multi_gpu"
    front = h.upload_views(roles=("front",))
    i3d = create(h, i3d_body(front, model_id="mock-i3d-single", auto_run=False))
    assert reason(post([a, i3d["job_id"]])) == "pipeline"
    waiting = create(h, body(model_id=GROUPABLE, gpu=True))["job_id"]
    response = post([a, waiting])
    if response.status_code == 422:
        assert reason(response) == "not_held"
    else:  # it may already have started
        assert response.status_code == 409 and response.json()["errors"][0]["code"] == "JOB_ALREADY_STARTED"
    assert post([a, b]).status_code == 201
    assert post([a, b]).status_code in (409, 422)  # no longer held
    for job_id in (a, b, waiting):
        h.wait(job_id)


def test_turning_auto_run_off_or_deleting_one_member_dissolves_the_group(harness_factory):
    h = harness_factory(registry=groupable_registry(), run_seconds=1.5)
    blocker = create(h, body())["job_id"]
    h.wait(blocker, until=lambda s: s in ("queued", "running"))
    a, b = held_pair(h)
    assert h.client.post(f"{API}/jobs/groups", json={"job_ids": [a, b]}).status_code == 201
    assert get(h, a)["scheduling"]["queue_position"] == get(h, b)["scheduling"]["queue_position"] == 1
    h.client.patch(f"{API}/jobs/{a}", json={"auto_run": False})
    for job_id in (a, b):
        sched = get(h, job_id)["scheduling"]
        assert sched["queue_state"] == "held" and sched["group_id"] is None and sched["group_job_ids"] == []
    assert h.client.post(f"{API}/jobs/groups", json={"job_ids": [a, b]}).status_code == 201
    assert h.client.delete(f"{API}/jobs/{a}").status_code == 204
    assert get(h, b)["scheduling"]["queue_state"] == "held" and get(h, b)["scheduling"]["group_id"] is None
    h.wait(blocker)


def test_retrying_a_grouped_job_creates_an_ungrouped_auto_run_job(harness_factory):
    h = harness_factory(registry=groupable_registry(), failure="submit")
    a, b = held_pair(h)
    assert h.client.post(f"{API}/jobs/groups", json={"job_ids": [a, b]}).status_code == 201
    failed = h.wait(a)
    assert failed["status"] == "failed" and failed["error"]["retryable"]
    h.compute.failure = "none"
    retry = h.client.post(
        f"{API}/jobs/{a}/retry", json={"client_request_id": "22222222-2222-4222-8222-222222222222"}
    )
    assert retry.status_code == 201, retry.text
    sched = retry.json()["scheduling"]
    assert sched["group_id"] is None and sched["auto_run"] is True and sched["gpu_index"] is None
    assert h.wait(retry.json()["job_id"])["status"] == "completed"
