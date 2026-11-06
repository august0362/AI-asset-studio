"""Character Production API in mock mode (docs/v2/TEST_PLAN.md §2-§3: I-01…I-11, approval gates, freezing)."""

from __future__ import annotations

import socket
import threading
from pathlib import Path

import pytest

from tests.character_helpers import API, Driver, V, rid, s1, s2, s3_profile, s5_items
from tests.conftest import codes, image_bytes, request_body


@pytest.fixture
def driver(harness) -> Driver:
    return Driver(harness)


def studio_job(harness, **overrides) -> dict:
    body = request_body(asset_category="character", **overrides)
    response = harness.client.post(f"{API}/jobs", json=body)
    assert response.status_code == 201, response.text
    return harness.wait(response.json()["job_id"])


def status(driver: Driver, cid: str, stage: str) -> str:
    return driver.detail(cid, stage)["state"]["editorial_status"]


# --- I-01 characters --------------------------------------------------------------------------------------------


def test_i01_create_list_search_filter_get_rename(harness, driver):
    a = driver.create("Ice Lotus Mage", ("xianxia", "mage"))
    b = driver.create("Ember Knight", ("knight",))
    driver.approve(b, "s1", s1())
    driver.save(a, "s1", s1())  # a: current stage s1 in draft; b: current stage s2 not started

    listed = harness.client.get(f"{API}/characters").json()
    assert listed["contract_version"] == "1.1" and {c["character_id"] for c in listed["characters"]} == {a, b}
    summary = next(c for c in listed["characters"] if c["character_id"] == b)
    assert summary["current_stage"] == "s2" and summary["approved_count"] == 1
    assert set(summary["stage_statuses"]) == {"s1", "s2", "s3", "s4", "s5", "s6", "s7"}
    assert [c["name"] for c in harness.client.get(f"{API}/characters?q=MAGE").json()["characters"]] == [
        "Ice Lotus Mage"
    ]
    assert [c["name"] for c in harness.client.get(f"{API}/characters?q=knight").json()["characters"]] == [
        "Ember Knight"
    ]
    assert [
        c["character_id"] for c in harness.client.get(f"{API}/characters?stage=s2").json()["characters"]
    ] == [b]
    by_status = {
        s: [
            c["character_id"] for c in harness.client.get(f"{API}/characters?status={s}").json()["characters"]
        ]
        for s in ("draft", "not_started", "approved")
    }
    assert by_status == {"draft": [a], "not_started": [b], "approved": []}
    page = harness.client.get(
        f"{API}/characters?limit=1"
    ).json()  # newest updated_at first; ties in any order
    first = page["characters"][0]["character_id"]
    assert len(page["characters"]) == 1 and page["next_cursor"] == first
    rest = harness.client.get(f"{API}/characters?limit=1&cursor={first}").json()
    assert {first, rest["characters"][0]["character_id"]} == {a, b} and rest["next_cursor"] is None

    workflow = harness.client.get(f"{API}/characters/{a}").json()
    assert workflow["character"]["version"] == 1 and len(workflow["stages"]) == 7
    assert [s["config"]["stage_id"] for s in workflow["stages"]] == ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]
    renamed = harness.client.patch(
        f"{API}/characters/{a}",
        json={"contract_version": V, "expected_version": 1, "name": "Frost Lotus Mage"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["character_id"] == a and renamed.json()["version"] == 2
    assert renamed.json()["name"] == "Frost Lotus Mage" and renamed.json()["tags"] == ["xianxia", "mage"]
    conflict = harness.client.patch(
        f"{API}/characters/{a}", json={"contract_version": V, "expected_version": 1, "name": "Again"}
    )
    assert (
        conflict.status_code == 409 and conflict.json()["errors"][0]["code"] == "CHARACTER_VERSION_CONFLICT"
    )
    assert conflict.json()["errors"][0]["details"]["current_version"] == 2
    cover = harness.client.patch(
        f"{API}/characters/{a}",
        json={"contract_version": V, "expected_version": 2, "cover_asset_id": "ast_000000000000"},
    )
    assert cover.status_code == 422 and codes(cover.json()["errors"]) == ["ASSET_NOT_FOUND"]
    events = harness.client.get(f"{API}/characters/{a}/history").json()["events"]
    assert [e["action"] for e in events] == ["character_updated", "draft_saved", "character_created"]
    assert [e["seq"] for e in events] == [3, 2, 1]


def test_create_is_idempotent_and_rejects_duplicate_tags(harness):
    body = {"contract_version": V, "client_request_id": rid(), "name": "Mage", "tags": ["a"]}
    first = harness.client.post(f"{API}/characters", json=body)
    again = harness.client.post(f"{API}/characters", json=body)
    assert first.status_code == again.status_code == 201
    assert first.json()["character_id"] == again.json()["character_id"]
    assert len(harness.client.get(f"{API}/characters").json()["characters"]) == 1
    duplicate = harness.client.post(
        f"{API}/characters", json={**body, "client_request_id": rid(), "tags": ["a", "a"]}
    )
    assert duplicate.status_code == 422


# --- I-02 full flow ---------------------------------------------------------------------------------------------


def test_i02_full_s1_to_s5_in_mock_mode(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    detail = driver.approve(cid, "s5", s5_items(done))
    frozen = detail["approved_revision"]["frozen_assets"]
    assert {a["purpose"] for a in frozen} == {"full_body", "front", "side", "back"}
    for asset in frozen:
        assert asset["frozen_in"] == {"stage_id": "s5", "revision": 1}
        assert asset["source"]["task_id"] and asset["source"]["seed"] is not None
        content = harness.client.get(asset["content_url"])
        assert content.status_code == 200 and content.headers["content-type"] == "image/png"
    outputs = harness.client.get(f"{API}/characters/{cid}/outputs").json()["outputs"]
    assert len(outputs) == 5  # the S3 concept + four S5 images
    workflow = harness.client.get(f"{API}/characters/{cid}").json()
    assert [s["state"]["editorial_status"] for s in workflow["stages"][:5]] == ["approved"] * 5
    assert workflow["stages"][5]["state"]["availability"] == "planned"
    download = harness.client.get(f"{outputs[0]['content_url']}?download=1")
    assert download.headers["content-disposition"].startswith("attachment")


# --- I-03 / I-04 references -------------------------------------------------------------------------------------


def test_i03_promote_an_upload_and_refuse_deleting_a_used_reference(harness, driver):
    cid = driver.create()
    upload = harness.upload(image_bytes(64, 48))
    body = {
        "contract_version": V,
        "client_request_id": rid(),
        "kind": "image",
        "purpose": "moodboard",
        "title": "Lotus",
    }
    created = harness.client.post(
        f"{API}/characters/{cid}/references", json={**body, "upload_id": upload["upload_id"]}
    )
    assert created.status_code == 201, created.text
    reference = created.json()
    assert (
        reference["sha256"] == upload["sha256"]
        and reference["width"] == 64
        and reference["mime_type"] == "image/png"
    )
    content = harness.client.get(reference["content_url"])
    assert content.status_code == 200 and content.content == image_bytes(64, 48)
    copied = harness.data_dir / "characters" / cid / "references" / f"{reference['reference_id']}.png"
    assert copied.is_file()

    content_s1 = {
        **s1(),
        "references": [
            {"reference_id": reference["reference_id"], "aspects": ["hair"], "likes": "the colour"}
        ],
    }
    driver.save(cid, "s1", content_s1)
    in_use = harness.client.delete(f"{API}/characters/{cid}/references/{reference['reference_id']}")
    assert in_use.status_code == 409 and in_use.json()["errors"][0]["code"] == "REFERENCE_IN_USE"
    assert in_use.json()["errors"][0]["details"]["used_by"] == ["s1:draft"]

    unused = harness.client.post(
        f"{API}/characters/{cid}/references",
        json={
            **body,
            "client_request_id": rid(),
            "upload_id": harness.upload(image_bytes(8, 8))["upload_id"],
        },
    ).json()
    assert (
        harness.client.delete(f"{API}/characters/{cid}/references/{unused['reference_id']}").status_code
        == 204
    )
    missing = harness.client.post(
        f"{API}/characters/{cid}/references",
        json={**body, "client_request_id": rid(), "upload_id": "upl_" + "0" * 32},
    )
    assert missing.status_code == 422 and codes(missing.json()["errors"]) == ["UPLOAD_NOT_FOUND"]
    unknown = driver.save(
        cid, "s1", {**s1(), "references": [{"reference_id": "ref_000000000000", "aspects": []}]}, expect=422
    )
    assert codes(unknown["errors"]) == ["REFERENCE_NOT_FOUND"]


def test_i04_url_reference_is_stored_and_never_fetched(harness, driver, monkeypatch):
    calls = []
    real_connect = socket.socket.connect

    def watch(self, address):
        calls.append(address)
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", watch)
    cid = driver.create()
    body = {"contract_version": V, "kind": "url", "purpose": "moodboard", "title": "Board"}
    good = harness.client.post(
        f"{API}/characters/{cid}/references",
        json={**body, "client_request_id": rid(), "url": "https://www.pinterest.com/example/ice-mage/"},
    )
    assert (
        good.status_code == 201
        and good.json()["url"].startswith("https://")
        and good.json()["content_url"] is None
    )
    for bad in ("ftp://example.com/x", "javascript:alert(1)", "https://" + "a" * 2000, "not a url"):
        response = harness.client.post(
            f"{API}/characters/{cid}/references", json={**body, "client_request_id": rid(), "url": bad}
        )
        assert response.status_code == 422 and codes(response.json()["errors"]) == [
            "REFERENCE_URL_INVALID"
        ], bad
    assert calls == []
    no_image = harness.client.get(f"{API}/characters/{cid}/references/{good.json()['reference_id']}/content")
    assert no_image.status_code == 404


# --- I-05 / I-06 linked jobs and frozen copies ------------------------------------------------------------------


def _s3_from_job(job_id: str) -> dict:
    content = s3_profile()
    content["candidates"] = [
        {
            "candidate_id": "cand_01",
            "source": "job_artifact",
            "job": {"job_id": job_id, "artifact_id": None},
            "verdict": "selected",
            "matches": [],
            "mismatches": [],
        }
    ]
    content["selected_candidate_id"] = "cand_01"
    return content


def test_i05_i06_linked_studio_job_is_resolved_not_copied_and_survives_deletion(harness, driver):
    cid = driver.create()
    driver.approve(cid, "s1", s1())
    driver.approve(cid, "s2", s2())
    studio = studio_job(harness)
    assert studio["status"] == "completed"
    detail = driver.save(cid, "s3", _s3_from_job(studio["job_id"]))
    resolved = detail["resolved_jobs"]
    assert (
        len(resolved) == 1 and resolved[0]["missing"] is False and resolved[0]["model_id"] == "mock-t2d-basic"
    )
    assert (
        resolved[0]["artifact"]["artifact_id"] == "art_01"
        and resolved[0]["prompt"] == studio["request"]["prompt"]
    )
    assert not (harness.data_dir / "characters" / cid / "assets").exists()  # nothing copied before approval

    driver.decide(cid, "s3", "submit")
    approved = driver.decide(cid, "s3", "approve")["approved_revision"]["frozen_assets"]
    assert len(approved) == 1 and approved[0]["purpose"] == "key_visual"
    assert approved[0]["source"]["job_id"] == studio["job_id"] and approved[0]["source"]["seed"] == 42
    assert approved[0]["sha256"] == studio["artifacts"][0]["sha256"]

    assert harness.client.delete(f"{API}/jobs/{studio['job_id']}").status_code == 204
    after = driver.detail(cid, "s3")
    assert after["state"]["editorial_status"] == "approved"
    assert after["resolved_jobs"][0]["missing"] is True and after["resolved_jobs"][0]["artifact"] is None
    frozen = harness.client.get(approved[0]["content_url"])
    assert frozen.status_code == 200 and frozen.headers["content-type"] == "image/png"


def test_freezing_checks_the_sha256_and_approves_nothing_on_a_mismatch(harness, driver):
    cid = driver.create()
    driver.approve(cid, "s1", s1())
    driver.approve(cid, "s2", s2())
    studio = studio_job(harness)
    driver.save(cid, "s3", _s3_from_job(studio["job_id"]))
    driver.decide(cid, "s3", "submit")
    stored = harness.data_dir / "outputs" / studio["job_id"] / "art_01.png"
    stored.write_bytes(image_bytes(32, 32))  # tampered after the job completed
    response = driver.decide(cid, "s3", "approve", expect=422)
    assert codes(response["errors"]) == ["LINKED_ARTIFACT_INVALID"]
    assert status(driver, cid, "s3") == "in_review"
    assert not (harness.data_dir / "characters" / cid / "assets").exists()


def test_a_sketch_reference_can_be_the_concept_and_is_frozen_as_png(harness, driver):
    cid = driver.create()
    driver.approve(cid, "s1", s1())
    driver.approve(cid, "s2", s2())
    upload = harness.upload(image_bytes(40, 30, "JPEG"), "sketch.jpg", "image/jpeg")
    reference = harness.client.post(
        f"{API}/characters/{cid}/references",
        json={
            "contract_version": V,
            "client_request_id": rid(),
            "kind": "image",
            "purpose": "sketch",
            "title": "Hand sketch",
            "upload_id": upload["upload_id"],
        },
    ).json()
    content = s3_profile()
    content["candidates"] = [
        {
            "candidate_id": "cand_01",
            "source": "reference",
            "reference_id": reference["reference_id"],
            "verdict": "selected",
        }
    ]
    content["selected_candidate_id"] = "cand_01"
    frozen = driver.approve(cid, "s3", content)["approved_revision"]["frozen_assets"][0]
    assert frozen["mime_type"] == "image/png" and frozen["source"] is None
    assert frozen["reference_id"] == reference["reference_id"] and (frozen["width"], frozen["height"]) == (
        40,
        30,
    )
    assert harness.client.get(frozen["content_url"]).content.startswith(b"\x89PNG")


# --- I-07 upstream change ---------------------------------------------------------------------------------------


def test_i07_reapproving_s2_flags_downstream_stages_without_touching_them(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    driver.approve(cid, "s5", s5_items(done))
    assets = harness.client.get(f"{API}/characters/{cid}/outputs").json()["outputs"]
    jobs_before = len(harness.client.get(f"{API}/jobs?limit=200").json()["jobs"])

    driver.approve(cid, "s2", s2(hair="Long silver hair with icy-blue ends"))
    for stage in ("s3", "s4", "s5"):
        state = driver.detail(cid, stage)["state"]
        assert state["editorial_status"] == "needs_revision", stage
        assert state["approved"]["stale"] is True and state["approved"]["revision"] == 1
        assert state["approved"]["stale_reasons"] == [
            {"upstream_stage_id": "s2", "used_revision": 1, "current_revision": 2}
        ]
    assert status(driver, cid, "s1") == "approved" and status(driver, cid, "s2") == "approved"
    assert harness.client.get(f"{API}/characters/{cid}/outputs").json()["outputs"] == assets
    for asset in assets:
        assert harness.client.get(asset["content_url"]).status_code == 200
    assert len(harness.client.get(f"{API}/jobs?limit=200").json()["jobs"]) == jobs_before
    event = harness.client.get(f"{API}/characters/{cid}/history?limit=1").json()["events"][0]
    assert (
        event["action"] == "approved"
        and event["stage_id"] == "s2"
        and event["affected_stages"] == ["s3", "s4", "s5"]
    )

    # Re-review without changes picks up the new upstream and clears the flag.
    driver.decide(cid, "s3", "submit")
    driver.decide(cid, "s3", "approve")
    assert status(driver, cid, "s3") == "approved"


# --- I-08 planned stages ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["s6", "s7"])
def test_i08_planned_stages_are_read_only(harness, driver, stage):
    cid = driver.create()
    detail = driver.detail(cid, stage)
    assert detail["state"]["availability"] == "planned" and detail["config"]["availability"] == "planned"
    saved = driver.save(cid, stage, {"stage_id": stage, "notes": "x"}, {"items": []}, expect=422)
    assert codes(saved["errors"]) == ["STAGE_NOT_AVAILABLE"]
    decided = driver.decide(cid, stage, "submit", expect=422)
    assert codes(decided["errors"]) == ["STAGE_NOT_AVAILABLE"]


# --- I-09 schema and path errors --------------------------------------------------------------------------------


def test_i09_unknown_fields_wrong_types_and_bad_ids(harness, driver):
    unknown = harness.client.post(
        f"{API}/characters",
        json={"contract_version": V, "client_request_id": rid(), "name": "X", "colour": "red"},
    )
    assert unknown.status_code == 422 and unknown.json()["errors"][0] == {
        **unknown.json()["errors"][0],
        "code": "REQUEST_FIELD_INVALID",
        "field": "colour",
    }
    wrong = harness.client.post(
        f"{API}/characters", json={"contract_version": V, "client_request_id": rid(), "name": 5}
    )
    assert codes(wrong.json()["errors"]) == ["REQUEST_FIELD_INVALID"]
    major = harness.client.post(
        f"{API}/characters", json={"contract_version": "2.0", "client_request_id": rid(), "name": "X"}
    )
    assert codes(major.json()["errors"]) == ["CONTRACT_VERSION_UNSUPPORTED"]
    for path in ("/characters/chr_XYZ", "/characters/..%2Fjobs", "/characters/chr_0123456789ab/stages/s8"):
        response = harness.client.get(f"{API}{path}")
        assert response.status_code in (400, 404) and codes(response.json()["errors"]) == ["PATH_INVALID"], (
            path
        )
    assert codes(harness.client.get(f"{API}/characters/chr_0123456789ab").json()["errors"]) == [
        "CHARACTER_NOT_FOUND"
    ]
    cid = driver.create()
    nested = driver.save(cid, "s2", {**s2(), "attributes": [{"attribute_id": "Bad Id"}]}, expect=422)
    assert all(e["code"] == "REQUEST_FIELD_INVALID" for e in nested["errors"])
    assert any(e["field"] == "content.attributes[0].attribute_id" for e in nested["errors"])
    mismatch = driver.save(cid, "s2", s1(), expect=422)
    assert mismatch["errors"][0]["field"] == "content.stage_id"
    bad_check = driver.save(
        cid, "s1", s1(), {"items": [{"item_id": "nope_item", "checked": True}]}, expect=422
    )
    assert bad_check["errors"][0]["field"] == "checklist.items[0].item_id"
    bad_revision = harness.client.get(f"{API}/characters/{cid}/stages/s1/revisions/0")
    assert bad_revision.status_code == 400
    missing_revision = harness.client.get(f"{API}/characters/{cid}/stages/s1/revisions/3")
    assert codes(missing_revision.json()["errors"]) == ["REVISION_NOT_FOUND"]


# --- I-10 concurrency -------------------------------------------------------------------------------------------


def test_i10_a_second_tab_with_an_old_draft_version_gets_409(harness, driver):
    cid = driver.create()
    driver.save(cid, "s1", s1())
    body = {"contract_version": V, "expected_draft_version": 0, "content": s1(), "checklist": {"items": []}}
    stale = harness.client.put(f"{API}/characters/{cid}/stages/s1/draft", json=body)
    assert stale.status_code == 409 and stale.json()["errors"][0]["code"] == "STAGE_DRAFT_CONFLICT"
    assert stale.json()["errors"][0]["details"]["current_draft_version"] == 1
    assert driver.detail(cid, "s1")["draft"]["content"]["idea"] == s1()["idea"]


def test_concurrent_saves_are_serialized_by_the_character_lock(harness, driver):
    cid = driver.create()
    results = []

    def save(i):
        body = {
            "contract_version": V,
            "expected_draft_version": 0,
            "content": {**s1(), "idea": f"idea {i}"},
            "checklist": {"items": []},
        }
        results.append(harness.client.put(f"{API}/characters/{cid}/stages/s1/draft", json=body).status_code)

    threads = [threading.Thread(target=save, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200] + [409] * 7
    assert driver.detail(cid, "s1")["draft"]["draft_version"] == 1


# --- status derivation and approval gates (§13.5.2, §13.5.3) ----------------------------------------------------


def test_editorial_status_follows_the_derivation_order(harness, driver):
    cid = driver.create()
    assert status(driver, cid, "s1") == "not_started" and status(driver, cid, "s2") == "blocked"
    driver.save(cid, "s2", s2())
    assert status(driver, cid, "s2") == "draft"  # exploration is allowed before S1 is approved
    driver.save(cid, "s1", s1())
    assert status(driver, cid, "s1") == "draft"
    driver.decide(cid, "s1", "submit")
    assert status(driver, cid, "s1") == "in_review"
    driver.decide(cid, "s1", "withdraw")
    assert status(driver, cid, "s1") == "draft"
    driver.decide(cid, "s1", "submit")
    driver.decide(cid, "s1", "request_revision", revision=2, note="More detail")
    assert status(driver, cid, "s1") == "needs_revision"
    driver.decide(cid, "s1", "submit")
    driver.decide(cid, "s1", "approve")
    assert status(driver, cid, "s1") == "approved"
    driver.save(cid, "s1", {**s1(), "notes": "an edit after approval"})
    detail = driver.detail(cid, "s1")
    assert detail["state"]["editorial_status"] == "draft" and detail["state"]["approved"]["revision"] == 3
    assert detail["draft"]["based_on_revision"] == 3
    assert [r["decision"] for r in detail["revisions"]] == ["approved", "revision_requested", "withdrawn"]
    driver.decide(cid, "s1", "request_revision")  # on the approved stage
    assert status(driver, cid, "s1") == "needs_revision"
    assert driver.detail(cid, "s2")["state"]["blockers"] == []


def test_each_approval_condition_alone_blocks_approval_and_changes_nothing(harness, driver):
    cid = driver.create()
    driver.save(cid, "s2", s2())
    driver.decide(cid, "s2", "submit")
    before = driver.detail(cid, "s2")["state"]
    blocked = driver.decide(cid, "s2", "approve", expect=422)
    assert (
        codes(blocked["errors"]) == ["STAGE_BLOCKED"] and blocked["errors"][0]["details"]["stage_id"] == "s1"
    )
    assert driver.detail(cid, "s2")["state"] == before
    assert codes(before["blockers"]) == ["STAGE_BLOCKED"]

    wrong = driver.decide(cid, "s2", "approve", revision=7, expect=409)
    assert codes(wrong["errors"]) == ["STAGE_TRANSITION_INVALID"]

    driver.approve(cid, "s1", s1())
    upstream = driver.decide(cid, "s2", "approve", expect=422)  # submitted before S1 had an approval
    assert codes(upstream["errors"]) == ["STAGE_UPSTREAM_CHANGED"]
    driver.decide(cid, "s2", "withdraw")

    driver.save(cid, "s2", s2(), {"items": []})
    driver.decide(cid, "s2", "submit")
    unchecked = driver.decide(cid, "s2", "approve", expect=422)
    assert codes(unchecked["errors"]) == ["STAGE_CHECKLIST_INCOMPLETE"]
    assert set(unchecked["errors"][0]["details"]["item_ids"]) == {
        "locked_clear",
        "unknowns_marked",
        "reference_map_done",
        "no_conflicts",
    }
    driver.decide(cid, "s2", "withdraw")

    unlocked = {**s2(), "attributes": [{**s2()["attributes"][1]}]}
    driver.save(cid, "s2", unlocked)
    driver.decide(cid, "s2", "submit")
    content = driver.decide(cid, "s2", "approve", expect=422)
    assert codes(content["errors"]) == ["STAGE_CONTENT_INCOMPLETE"]
    assert content["errors"][0]["details"]["rule"] == "locked_attribute_required"
    assert driver.detail(cid, "s2")["state"]["editorial_status"] == "in_review"


def test_content_rules_of_s1_s3_s4_s5(harness, driver):
    cid = driver.create()
    driver.save(cid, "s1", {"stage_id": "s1"})
    rules = {e["details"]["rule"] for e in driver.detail(cid, "s1")["state"]["blockers"]}
    assert rules == {"idea_or_reference", "direction_required"}
    driver.approve(cid, "s1", s1())
    driver.approve(cid, "s2", s2())
    driver.save(cid, "s3", s3_profile())
    assert {e["details"].get("rule") for e in driver.detail(cid, "s3")["state"]["blockers"]} == {
        "one_selected_candidate"
    }
    s4_blockers = driver.save(cid, "s4", {"stage_id": "s4"})["state"]["blockers"]
    rules = {e["details"].get("rule") for e in s4_blockers if e["code"] == "STAGE_CONTENT_INCOMPLETE"}
    assert {"required_purpose_prompt", "required_purpose_task", "production_profile_required"} <= rules
    assert "STAGE_BLOCKED" in codes(s4_blockers)  # S3 is not approved yet
    s5_blockers = driver.detail(cid, "s5")["state"]["blockers"]
    assert codes(s5_blockers) == [
        "STAGE_BLOCKED",
        "STAGE_CHECKLIST_INCOMPLETE",
        *["STAGE_CONTENT_INCOMPLETE"] * 4,
    ]
    assert {e["details"]["purpose"] for e in s5_blockers[2:]} == {"full_body", "front", "side", "back"}


def test_s4_detail_shows_the_manifest_preview_and_resource_plan(harness, driver):
    cid = driver.create()
    driver.through_s4(cid)
    detail = driver.detail(cid, "s4")
    preview = detail["manifest_preview"]
    assert preview["manifest_id"] == "bat_000000000000" and preview["status"] == "ready"
    assert preview["expected_model_loads"] == 1 and preview["groups"][0]["estimated_runtime_seconds"] == 120
    assert len(detail["resource_plans"]) == 1 and detail["resource_plans"][0]["required_seconds"] is not None
    s5 = driver.detail(cid, "s5")
    assert len(s5["batches"]) == 1 and s5["batches"][0]["kind"] == "production"
    assert len(s5["resource_plans"]) == 1
    assert [i["stage_id"] for i in s5["inputs"]] == ["s4", "s2"]
    assert s5["inputs"][0]["revision"] == 1 and s5["inputs"][1]["content"]["stage_id"] == "s2"


def test_draft_saves_check_models_options_and_linked_ids(harness, driver):
    cid = driver.create()
    bad_model = driver.save(
        cid,
        "s3",
        {**s3_profile(), "preview_profile": {**s3_profile()["preview_profile"], "model_id": "nope"}},
        expect=422,
    )
    assert codes(bad_model["errors"]) == ["MODEL_NOT_FOUND"]
    bad_option = driver.save(
        cid,
        "s3",
        {**s3_profile(), "preview_profile": {**s3_profile()["preview_profile"], "options": {"steps": 3}}},
        expect=422,
    )
    assert codes(bad_option["errors"]) == ["MODEL_OPTION_UNSUPPORTED"]
    bad_size = driver.save(
        cid,
        "s3",
        {**s3_profile(), "preview_profile": {**s3_profile()["preview_profile"], "width": 300}},
        expect=422,
    )
    assert codes(bad_size["errors"]) == ["MODEL_OPTION_INVALID"]
    link = driver.save(cid, "s3", _s3_from_job("job_20261106T000000Z_abcdef"), expect=422)
    assert codes(link["errors"]) == ["LINKED_JOB_NOT_FOUND"]
    shape = {
        **s3_profile(),
        "candidates": [{"candidate_id": "cand_01", "source": "job_artifact", "verdict": "undecided"}],
    }
    assert codes(driver.save(cid, "s3", shape, expect=422)["errors"]) == ["REQUEST_FIELD_INVALID"]
    answers = {**s2(), "answers": [{"question_id": "q_scale", "status": "unknown", "answer": "tall"}]}
    assert driver.save(cid, "s2", answers, expect=422)["errors"][0]["field"] == "content.answers[0].answer"
    item = {"stage_id": "s5", "items": [{"item_id": "item_001", "purpose": "front", "selected": True}]}
    assert codes(driver.save(cid, "s5", item, expect=422)["errors"]) == ["REQUEST_FIELD_INVALID"]
    asset = {"stage_id": "s4", "reference_asset_ids": ["ast_000000000000"]}
    assert codes(driver.save(cid, "s4", asset, expect=422)["errors"]) == ["ASSET_NOT_FOUND"]


def test_history_records_draft_saves_at_most_once_per_minute(harness, driver):
    cid = driver.create()
    for _ in range(3):
        driver.save(cid, "s1", s1())
    events = harness.client.get(f"{API}/characters/{cid}/history").json()["events"]
    assert [e["action"] for e in events] == ["draft_saved", "character_created"]


def test_character_files_live_under_their_own_folder_only(harness, driver):
    cid = driver.create()
    driver.approve(cid, "s1", s1())
    root = harness.data_dir / "characters" / cid
    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert files == [
        "character.json",
        "history.jsonl",
        "requests.json",
        "stages/s1/draft.json",
        "stages/s1/revisions/0001.json",
        "stages/s1/state.json",
    ]
    for path in root.rglob("*.json"):
        assert str(harness.data_dir) not in path.read_text(encoding="utf-8")
    assert isinstance(root, Path)


# --- I-11 delete a character (D-038, route 19) ------------------------------------------------------------------


def test_i11_delete_removes_the_character_and_keeps_its_jobs(harness, driver):
    keep = driver.create("Ember Knight", ("knight",))
    cid = driver.create()
    manifest = driver.through_s4(cid)
    done = driver.settle(cid, driver.submit(cid, manifest["manifest_id"]))
    job_ids = [a["job_id"] for a in done["attempts"]]
    reference = harness.client.post(
        f"{API}/characters/{cid}/references",
        json={
            "contract_version": V,
            "client_request_id": rid(),
            "kind": "image",
            "purpose": "moodboard",
            "title": "Palette",
            "upload_id": harness.upload(image_bytes(64, 64))["upload_id"],
            "source_note": None,
        },
    ).json()

    response = harness.client.delete(f"{API}/characters/{cid}")
    assert response.status_code == 204 and response.content == b""
    assert not (harness.data_dir / "characters" / cid).exists()
    assert [p.name for p in (harness.data_dir / "characters").iterdir()] == [keep]
    listed = harness.client.get(f"{API}/characters").json()["characters"]
    assert [c["character_id"] for c in listed] == [keep]
    for method, path in (
        ("get", f"/characters/{cid}"),
        ("get", f"/characters/{cid}/stages/s1"),
        ("get", f"/characters/{cid}/history"),
        ("get", f"/characters/{cid}/outputs"),
        ("get", f"/characters/{cid}/batches/{manifest['manifest_id']}"),
        ("get", f"/characters/{cid}/references/{reference['reference_id']}/content"),
        ("delete", f"/characters/{cid}"),
    ):
        gone = getattr(harness.client, method)(f"{API}{path}")
        assert gone.status_code == 404, path
        assert codes(gone.json()["errors"]) == ["CHARACTER_NOT_FOUND"], path
        assert gone.json()["contract_version"] == "1.1"
    for job_id in job_ids:  # the v1 jobs stay in the Jobs history
        assert harness.client.get(f"{API}/jobs/{job_id}").json()["status"] == "completed"
    assert driver.detail(keep, "s1")["state"]["editorial_status"] == "not_started"


def test_i11_delete_is_refused_while_a_batch_attempt_runs(harness, driver):
    cid = driver.create()
    manifest = driver.through_s4(cid)
    harness.compute.run_seconds = 1.5
    submitted = driver.submit(cid, manifest["manifest_id"])
    refused = harness.client.delete(f"{API}/characters/{cid}")
    assert refused.status_code == 409
    body = refused.json()
    assert codes(body["errors"]) == ["BATCH_ATTEMPT_RUNNING"]
    assert body["errors"][0]["details"]["manifest_ids"] == [manifest["manifest_id"]]
    assert (harness.data_dir / "characters" / cid / "character.json").is_file()
    harness.compute.run_seconds = 0.0
    driver.settle(cid, submitted)
    assert harness.client.delete(f"{API}/characters/{cid}").status_code == 204


def test_i11_a_new_create_after_delete_reuses_nothing(harness, driver):
    request_id = rid()
    body = {"contract_version": V, "client_request_id": request_id, "name": "Ice Lotus Mage", "tags": []}
    first = harness.client.post(f"{API}/characters", json=body).json()["character_id"]
    assert harness.client.delete(f"{API}/characters/{first}").status_code == 204
    again = harness.client.post(f"{API}/characters", json=body)
    assert again.status_code == 201 and again.json()["character_id"] != first


def test_i11_an_interrupted_delete_is_cleaned_up_at_startup(harness):
    from aas_backend.characters.service import CharacterService

    leftover = harness.data_dir / "characters" / ".deleted-chr_0123456789ab-00ff00ff"
    (leftover / "stages").mkdir(parents=True)
    (leftover / "character.json").write_text("{}", encoding="utf-8")
    CharacterService(harness.client.app.state.characters.jobs)
    assert not leftover.exists()
    assert harness.client.get(f"{API}/characters").json()["characters"] == []
