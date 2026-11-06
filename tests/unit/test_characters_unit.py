"""Character Production units (docs/v2/TEST_PLAN.md §2): IDs and paths, storage, status and batch derivations."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from aas_backend.characters import config
from aas_backend.characters.batches import BatchService, derive
from aas_backend.characters.contracts import BatchAttempt, ProductionTask, StageHistory, StageRevision
from aas_backend.characters.store import CharacterStore, RevisionExists, StageRecord
from aas_backend.characters.workflow import CharacterView
from aas_backend.storage import files
from aas_backend.storage.paths import PathInvalid, is_valid_id, safe_path
from models.registry import MOCK_CAPABILITIES, ModelRegistry, default_registry, full_registry

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
CID = "chr_0123456789ab"

# --- identifiers and paths --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,good,bad",
    [
        (
            "character_id",
            "chr_3f9a0c1e2b7d",
            ["chr_3F9A0C1E2B7D", "chr_3f9a0c1e2b7", "chr_../etc", "char_3f9a0c1e2b7d"],
        ),
        ("stage_id", "s7", ["s0", "s8", "S1", "s1/"]),
        ("reference_id", "ref_0a1b2c3d4e5f", ["ref_0a1b2c3d4e5", "ref_0a1b2c3d4e5f0"]),
        ("asset_id", "ast_1d2e3f4a5b6c", ["ast_1d2e3f4a5b6g", "ast_"]),
        ("manifest_id", "bat_7c2d9e0f1a3b", ["bat_7c2d9e0f1a3", "bat_7c2d9e0f1a3b/../x"]),
    ],
)
def test_new_id_patterns(kind, good, bad):
    assert is_valid_id(kind, good)
    for value in bad:
        assert not is_valid_id(kind, value), value


def test_safe_path_rejects_traversal_for_character_paths(tmp_path):
    for relative in (
        "characters/../jobs/x.json",
        "characters/chr_0123456789ab/../../x",
        "/characters",
        "C:/x",
    ):
        with pytest.raises(PathInvalid):
            safe_path(tmp_path, relative)


# --- storage ----------------------------------------------------------------------------------------------------


def revision(number: int = 1) -> StageRevision:
    return StageRevision.model_validate(
        {
            "contract_version": "1.1",
            "character_id": CID,
            "stage_id": "s1",
            "revision": number,
            "content": {"stage_id": "s1", "idea": "x", "directions": ["y"]},
            "checklist": {"items": []},
            "source_revisions": {},
            "submitted_at": NOW,
            "decision": "pending",
            "decided_at": None,
            "note": None,
            "frozen_assets": [],
            "batch_manifest_id": None,
        }
    )


def test_revisions_are_created_exclusively(tmp_path):
    store = CharacterStore(tmp_path)
    store.path(CID).mkdir(parents=True)
    store.create_revision(revision())
    with pytest.raises(RevisionExists):
        store.create_revision(revision().model_copy(update={"note": "overwrite attempt"}))
    assert store.read_revision(CID, "s1", 1).note is None
    assert not list(store.path(CID, "stages", "s1", "revisions").glob(".*.tmp"))


def test_history_is_append_only_and_a_torn_last_line_is_ignored(tmp_path):
    store = CharacterStore(tmp_path)
    store.path(CID).mkdir(parents=True)
    for seq in (1, 2):
        store.append_history(
            CID,
            StageHistory(
                seq=seq,
                at=NOW,
                stage_id=None,
                action="character_created",
                revision=None,
                manifest_id=None,
                affected_stages=[],
                note=None,
            ),
        )
    with store.path(CID, "history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"seq": 3, "at": "2026-11')  # a crash in the middle of the last line
    assert [e.seq for e in store.read_history(CID)] == [1, 2]


def test_an_interrupted_atomic_write_keeps_the_old_file_and_its_temp_is_swept(tmp_path, monkeypatch):
    store = CharacterStore(tmp_path)
    store.path(CID).mkdir(parents=True)
    store.write_stage(CID, "s1", StageRecord(latest_revision=1))

    def crash(*_args, **_kwargs):
        raise OSError("power cut")

    monkeypatch.setattr(files.os, "replace", crash)
    with pytest.raises(OSError):
        store.write_stage(CID, "s1", StageRecord(latest_revision=2))
    monkeypatch.undo()
    assert store.read_stage(CID, "s1").latest_revision == 1
    leftover = store.path(CID, "stages", "s1") / ".state.json.abc.tmp"
    leftover.write_text("partial", encoding="utf-8")
    assert store.sweep_temp() == 1 and not leftover.exists()


def test_one_lock_object_per_character(tmp_path):
    store = CharacterStore(tmp_path)
    assert store.lock(CID) is store.lock(CID)
    assert store.lock(CID) is not store.lock("chr_ba9876543210")


# --- editorial status (§13.5.3), table-driven -------------------------------------------------------------------


class _Service:
    def __init__(self, tmp_path, registry=None):
        self.registry = registry or default_registry()
        self.store = CharacterStore(tmp_path)
        self.store.path(CID).mkdir(parents=True, exist_ok=True)


def view_for(
    tmp_path, records: dict[str, StageRecord], drafts: dict[str, int] | None = None
) -> CharacterView:
    service = _Service(tmp_path)
    for stage_id, record in records.items():
        service.store.write_stage(CID, stage_id, record)
        for number in {record.latest_revision, record.approved_revision} - {None}:
            sources = {u: 1 for u, _ in config.dependencies(stage_id)}
            service.store.create_revision(
                revision(number).model_copy(update={"stage_id": stage_id, "source_revisions": sources})
            )
    view = CharacterView(service, SimpleNamespace(character_id=CID))
    for stage_id, version in (drafts or {}).items():
        view.draft(stage_id).draft_version = version
    return view


APPROVED = StageRecord(
    latest_revision=1, approved_revision=1, last_decision="approved", submitted_draft_version=1
)


@pytest.mark.parametrize(
    "records,drafts,stage,expected",
    [
        ({}, {}, "s1", "not_started"),
        ({}, {}, "s2", "blocked"),
        ({"s1": APPROVED}, {"s1": 1}, "s2", "not_started"),
        ({}, {"s2": 1}, "s2", "draft"),
        (
            {"s1": StageRecord(latest_revision=1, pending_revision=1, submitted_draft_version=1)},
            {"s1": 1},
            "s1",
            "in_review",
        ),
        ({"s1": APPROVED}, {"s1": 1}, "s1", "approved"),
        (
            {"s1": APPROVED},
            {"s1": 2},
            "s1",
            "draft",
        ),  # an older approval stays in use while the draft changes
        (
            {"s1": APPROVED.model_copy(update={"last_decision": "revision_requested"})},
            {"s1": 1},
            "s1",
            "needs_revision",
        ),
        (
            {
                "s1": APPROVED.model_copy(update={"approved_revision": 2, "latest_revision": 2}),
                "s2": APPROVED,
            },
            {"s1": 1, "s2": 1},
            "s2",
            "needs_revision",  # S2 used S1 r1, S1 is now at r2: stale
        ),
        (
            {"s1": APPROVED.model_copy(update={"pending_revision": 2, "latest_revision": 2})},
            {"s1": 2},
            "s1",
            "in_review",  # in_review wins over everything
        ),
    ],
)
def test_editorial_status_derivation(tmp_path, records, drafts, stage, expected):
    view = view_for(tmp_path, records, drafts)
    assert view.status(stage) == expected


def test_staleness_is_derived_on_read_and_writes_nothing(tmp_path):
    view = view_for(
        tmp_path,
        {"s1": APPROVED.model_copy(update={"approved_revision": 2, "latest_revision": 2}), "s2": APPROVED},
        {"s1": 1, "s2": 1},
    )
    before = sorted(p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file())
    reasons = view.stale_reasons("s2")
    assert [(r.upstream_stage_id, r.used_revision, r.current_revision) for r in reasons] == [("s1", 1, 2)]
    assert view.snapshot("s2").stale is True
    assert sorted(p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()) == before


# --- stage configuration ----------------------------------------------------------------------------------------


def test_stage_graph_and_availability():
    registry = default_registry()
    configs = {s: config.stage_config(s, registry) for s in ("s1", "s2", "s3", "s4", "s5", "s6", "s7")}
    deps = {s: [(d.stage_id, d.kind) for d in c.dependencies] for s, c in configs.items()}
    assert deps["s3"] == [("s2", "hard"), ("s1", "soft")] and deps["s5"] == [("s4", "hard"), ("s2", "soft")]
    assert [c.availability for c in configs.values()] == ["available"] * 5 + ["planned", "planned"]
    assert (
        configs["s4"].required_purposes
        == configs["s5"].required_purposes
        == ["full_body", "front", "side", "back"]
    )
    assert [q.question_id for q in configs["s2"].guided_questions if q.core][:2] == [
        "q_name_role",
        "q_identity_marks",
    ]
    assert config.downstream("s2") == ["s3", "s4", "s5", "s6"]
    no_t2d = ModelRegistry([m for m in MOCK_CAPABILITIES if "text_to_2d" not in m.supported_pipeline_types])
    s5 = config.stage_config("s5", no_t2d)
    assert (s5.availability, s5.availability_reason) == ("unavailable", "no_text_to_2d_model")


# --- manifests and batch status (§13.4.10, §13.5.6) -------------------------------------------------------------


def build(registry, model_id: str, n: int = 3, references=()):
    service = SimpleNamespace(
        registry=registry,
        clock=lambda: NOW,
        model_revision=lambda m: registry.adapter(m).model_revision(),
    )
    tasks = [
        ProductionTask(task_id=f"t{i}", purpose="front", prompt="p", seed=i, width=1024, height=1024)
        for i in range(1, n + 1)
    ]
    return BatchService(service).build(
        character_id=CID,
        kind="production",
        model_id=model_id,
        tasks=tasks,
        approved_spec_revision=2,
        prompt_set_revision=1,
        concept_revision=1,
        reference_ids=list(references),
    )


def test_one_group_per_model_with_the_measured_estimate_and_recorded_references():
    manifest = build(full_registry(), "moss-image-sft", 3, ["ast_1d2e3f4a5b6c"])
    assert manifest.expected_model_loads == 1 and [g.task_ids for g in manifest.groups] == [
        ["t1", "t2", "t3"]
    ]
    group = manifest.groups[0]
    assert group.estimated_runtime_seconds == 354 * 3 and group.micro_batch_size == 1
    assert group.model_revision == manifest.model_revision == "f972bd4b4b9e3852133cc5da954d87bc32cd8fb9"
    assert [(r.asset_id, r.applied, r.reason) for r in manifest.references] == [
        ("ast_1d2e3f4a5b6c", False, "model_has_no_image_role")
    ]
    assert manifest.status == "ready" and {r.status for r in manifest.results} == {"pending"}
    styleref = build(default_registry(), "mock-t2d-styleref", 1, ["ref_0a1b2c3d4e5f"])
    assert styleref.references[0].reason == "batch_image_inputs_not_supported"
    assert styleref.model_revision is None


@pytest.mark.parametrize(
    "statuses,attempted,expected,retryable",
    [
        (["pending", "pending"], False, "ready", []),
        (["pending", "succeeded"], True, "submitted", []),
        (["succeeded", "succeeded"], True, "completed", []),
        (["failed", "not_run"], True, "failed", ["t1", "t2"]),
        (["succeeded", "failed", "not_run"], True, "partially_completed", ["t2", "t3"]),
        (["succeeded", "pending", "failed"], True, "submitted", []),  # no retry while an attempt runs
    ],
)
def test_batch_status_and_retryable_tasks(statuses, attempted, expected, retryable):
    manifest = build(default_registry(), "mock-t2d-basic", len(statuses))
    for result, value in zip(manifest.results, statuses, strict=True):
        result.status = value
    if attempted:
        manifest.attempts = [
            BatchAttempt(
                attempt=1, group_id="g01", job_id="job_20261106T120000Z_abcdef", task_ids=[], submitted_at=NOW
            )
        ]
    derive(manifest)
    assert manifest.status == expected and manifest.retryable_task_ids == retryable


def test_environment_is_untouched_by_the_tests():
    assert "AAS_MOCK_FAIL_TASKS" not in os.environ
