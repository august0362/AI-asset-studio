"""Character Production contracts v1.1 (CONTRACTS §13, TEST_PLAN §1).

Every §13.6.2 example and every shared fixture in ``tests/fixtures/contracts/v2/`` validates against its Pydantic
model and round-trips unchanged. The frontend serves the same files from its mock client (V2-3).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter

from aas_backend.characters import contracts as c
from aas_backend.schemas import ErrorResponse, GenerationResult
from tests.contract.test_contract_examples import ROOT, contract_blocks

FIXTURES = ROOT / "tests" / "fixtures" / "contracts" / "v2"
FRONTEND_FIXTURES = ROOT / "interface" / "frontend" / "tests" / "fixtures" / "contracts" / "v2"

MODELS: dict[str, type[BaseModel]] = {
    "example_create_character_request": c.CreateCharacterRequest,
    "example_character": c.Character,
    "example_character_list": c.CharacterList,
    "example_save_draft_request": c.SaveDraftRequest,
    "example_error_response": ErrorResponse,
    "example_batch_manifest": c.BatchManifest,
    "character": c.Character,
    "character_list": c.CharacterList,
    "character_workflow": c.CharacterWorkflow,
    "character_workflow_in_progress": c.CharacterWorkflow,
    "reference_image": c.ReferenceAsset,
    "reference_url": c.ReferenceAsset,
    "stage_revision_s5": c.StageRevision,
    "history_page": c.HistoryPage,
    "outputs": c.OutputList,
    "error_approval_blocked": ErrorResponse,
    "error_transition_invalid": ErrorResponse,
    "job_batch_partial": GenerationResult,
    **{
        f"stage_detail_{s}": c.StageDetail for s in ("s1", "s2", "s3", "s4", "s5", "s6", "s7", "s4_in_review")
    },
    **{
        f"batch_manifest_{s}": c.BatchManifest
        for s in ("ready", "submitted", "completed", "partially_completed", "failed")
    },
}


def fixture_files() -> list[Path]:
    files = sorted(FIXTURES.glob("*.json"))
    if FRONTEND_FIXTURES.is_dir():
        files += sorted(FRONTEND_FIXTURES.glob("*.json"))
    return files


# Fixtures that hold a list; the frontend-only names (Codex, V2-3) are not generated here.
LISTS = {"batch_jobs": TypeAdapter(list[GenerationResult])}
FRONTEND_ONLY = {"stage-configs": TypeAdapter(list[c.StageConfig]), **LISTS}
FILES = FIXTURES / "files"


def test_every_fixture_has_a_model_and_every_model_a_fixture():
    assert {p.stem for p in FIXTURES.glob("*.json")} == set(MODELS) | set(LISTS)


@pytest.mark.parametrize(
    "path", fixture_files(), ids=lambda p: f"{p.parent.parent.parent.parent.name}/{p.name}"
)
def test_fixture_validates_and_round_trips(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if path.stem in FRONTEND_ONLY:
        adapter = FRONTEND_ONLY[path.stem]
        assert adapter.dump_python(adapter.validate_python(payload), mode="json") == payload
        return
    if path.stem not in MODELS:
        pytest.fail(
            f"{path.name}: no backend model is mapped to this fixture name; add it to MODELS or FRONTEND_ONLY"
        )
    model = MODELS[path.stem]
    instance = model.model_validate(payload)
    if model is not c.CreateCharacterRequest:  # its UUID and omitted defaults are normalized
        assert instance.model_dump(mode="json") == payload


def test_the_section_13_examples_are_the_example_fixtures():
    examples = [
        json.loads(body) for section, lang, body in contract_blocks() if section == "13.6" and lang == "json"
    ]
    assert examples == [
        json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        for name in MODELS
        if name.startswith("example_")
    ]


def test_every_batch_status_and_every_stage_has_a_fixture():
    manifests = [json.loads(p.read_text(encoding="utf-8")) for p in FIXTURES.glob("batch_manifest_*.json")]
    assert {m["status"] for m in manifests} == {
        "ready",
        "submitted",
        "completed",
        "partially_completed",
        "failed",
    }
    stages = {
        json.loads(p.read_text(encoding="utf-8"))["config"]["stage_id"]
        for p in FIXTURES.glob("stage_detail_*.json")
    }
    assert stages == {"s1", "s2", "s3", "s4", "s5", "s6", "s7"}


def test_fixtures_hold_no_local_paths_or_secrets():
    for path in FIXTURES.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        for needle in (
            "C:\\",
            "C:/",
            "/Users/",
            "AppData",
            "KAGGLE_KEY",
            "KAGGLE_USERNAME",
            "kaggle.json",
            "_token",
        ):
            assert needle not in text, (path.name, needle)


def test_new_error_codes_are_documented():
    text = (ROOT / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    section = text[text.index("### 13.7 Error codes") :]
    used = set()
    for path in sorted((ROOT / "interface" / "backend" / "aas_backend" / "characters").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        used |= {
            code
            for code in (
                "CHARACTER_NOT_FOUND",
                "CHARACTER_VERSION_CONFLICT",
                "STAGE_DRAFT_CONFLICT",
                "STAGE_NOT_AVAILABLE",
                "STAGE_BLOCKED",
                "STAGE_UPSTREAM_CHANGED",
                "STAGE_CHECKLIST_INCOMPLETE",
                "STAGE_CONTENT_INCOMPLETE",
                "STAGE_TRANSITION_INVALID",
                "REVISION_NOT_FOUND",
                "REFERENCE_NOT_FOUND",
                "ASSET_NOT_FOUND",
                "REFERENCE_IN_USE",
                "REFERENCE_URL_INVALID",
                "LINKED_JOB_NOT_FOUND",
                "LINKED_JOB_NOT_COMPLETED",
                "LINKED_ARTIFACT_INVALID",
                "BATCH_NOT_FOUND",
                "BATCH_ALREADY_SUBMITTED",
                "BATCH_MANIFEST_STALE",
                "BATCH_NOTHING_TO_RETRY",
                "BATCH_ATTEMPT_RUNNING",
                "BATCH_TASK_FAILED",
                "BATCH_TASK_NOT_RUN",
            )
            if f'"{code}"' in source
        }
    assert used and all(f"`{code}`" in section for code in used)


# --- image bytes behind the fixtures (files/) -------------------------------------------------------------------


def _references(value, found: list[tuple[str, str | None]]) -> None:
    """(url, sha256 the payload states or None) for every image a fixture points to."""
    if isinstance(value, dict):
        for key in ("content_url", "cover_url"):
            url = value.get(key)
            if isinstance(url, str) and url.startswith("/api/v1/"):
                found.append((url, value.get("sha256") if key == "content_url" else None))
        job_id, artifact_id = value.get("job_id"), value.get("artifact_id")
        if isinstance(job_id, str) and isinstance(artifact_id, str):
            sha = value.get("sha256") if "content_url" not in value else None
            found.append((f"/api/v1/jobs/{job_id}/artifacts/{artifact_id}/content", sha))
        for item in value.values():
            _references(item, found)
    elif isinstance(value, list):
        for item in value:
            _references(item, found)


def test_every_indexed_file_exists_with_its_size_and_checksum():
    index = json.loads((FILES / "index.json").read_text(encoding="utf-8"))
    assert index
    for url, entry in index.items():
        path = FILES / entry["file"]
        assert path.resolve().is_relative_to(FILES.resolve()) and path.is_file(), url
        data = path.read_bytes()
        assert len(data) == entry["size_bytes"] and hashlib.sha256(data).hexdigest() == entry["sha256"], url
        assert data.startswith(b"\x89PNG") == (entry["mime_type"] == "image/png"), url


def test_every_image_a_fixture_mentions_has_matching_bytes():
    index = json.loads((FILES / "index.json").read_text(encoding="utf-8"))
    found: list[tuple[str, str | None]] = []
    for path in FIXTURES.glob("*.json"):
        if not path.stem.startswith("example_"):
            _references(json.loads(path.read_text(encoding="utf-8")), found)
    assert found
    for url, sha in found:
        assert url in index, url
        if sha is not None:
            assert index[url]["sha256"] == sha, url
    assert set(index) == {url for url, _ in found}  # no orphan files
