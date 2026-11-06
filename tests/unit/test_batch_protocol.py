"""Batch jobs inside the v1 job system (CONTRACTS §13.9): adapter arguments, the remote entries' batch loop,
``task_results.json`` reading and the ``BATCH_PARTIAL`` warning."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from PIL import Image

from aas_backend.orchestrator.worker import batch_partial
from models.adapters.base import ArtifactInvalidError, deadline_seconds
from models.adapters.diffusers_text_to_2d import ANIMAGINE_QUALITY_TAGS, remote_entry
from models.adapters.mock_text_to_2d import remote_entry as mock_entry
from models.contracts import Artifact, GenerationRequest, GenerationTask, utc_now
from models.registry import default_registry, full_registry

JOB = "job_20261106T101500Z_a1b2c3"


def batch_request(model_id: str, task_ids=("front_01", "side-01", "back_01"), budget: int | None = 1200):
    return GenerationRequest(
        contract_version="1.0",
        job_id=JOB,
        pipeline_type="text_to_2d",
        asset_category="character",
        model_id=model_id,
        prompt=None,
        inputs=[],
        options={},
        output_format="png",
        created_at=utc_now(),
        tasks=[
            GenerationTask(
                task_id=t,
                prompt=f"1girl, {t}",
                options={"seed": i, "width": 832, "height": 1216, "negative_prompt": None},
            )
            for i, t in enumerate(task_ids)
        ],
        time_budget_seconds=budget,
    )


# --- adapters ---------------------------------------------------------------------------------------------------


def test_real_adapter_builds_one_invocation_with_every_task_and_a_deadline():
    adapter = full_registry().adapter("animagine-xl-4")
    invocation = adapter.build_invocation(batch_request("animagine-xl-4"))
    args = invocation.arguments
    assert [t["task_id"] for t in args["tasks"]] == ["front_01", "side-01", "back_01"]
    assert all(
        t["prompt"].endswith(ANIMAGINE_QUALITY_TAGS) for t in args["tasks"]
    )  # per-task prompt handling
    assert args["deadline_seconds"] == 1200 - 120 and "prompt" not in args
    assert [o.name for o in invocation.expected_outputs] == [
        "task_front_01.png",
        "task_side-01.png",
        "task_back_01.png",
    ]
    assert not any(o.required for o in invocation.expected_outputs)
    assert adapter.model_revision() == args["recipe"]["revision"]


def test_deadline_margin():
    assert deadline_seconds(batch_request("mock-t2d-basic", budget=None)) is None
    assert deadline_seconds(batch_request("mock-t2d-basic", budget=600)) == 480
    assert deadline_seconds(batch_request("mock-t2d-basic", budget=43200)) == 43200 - 4320


def test_a_normal_request_serializes_exactly_as_in_v1_0():
    request = batch_request("mock-t2d-basic").model_copy(update={"tasks": None, "time_budget_seconds": None})
    assert "tasks" not in request.model_dump() and "time_budget_seconds" not in request.model_dump(
        mode="json"
    )


def test_an_adapter_without_batch_support_refuses_tasks():
    adapter = default_registry().adapter("mock-i3d-single")
    with pytest.raises(ValueError):
        adapter.build_invocation(batch_request("mock-i3d-single"))


def write_results(folder: Path, rows) -> None:
    (folder / "task_results.json").write_text(json.dumps({"v": 1, "tasks": rows}), encoding="utf-8")


def png(path: Path) -> None:
    Image.new("RGB", (16, 24), (10, 20, 30)).save(path, format="PNG")


def test_collect_maps_each_succeeded_task_to_an_artifact_and_the_first_is_primary(tmp_path):
    adapter = default_registry().adapter("mock-t2d-basic")
    request = batch_request("mock-t2d-basic")
    png(tmp_path / "task_side-01.png")
    png(tmp_path / "task_back_01.png")
    (tmp_path / "task_front_01.png").write_bytes(b"not a png")
    write_results(
        tmp_path,
        [
            {"task_id": "front_01", "status": "succeeded", "error": None},  # but its PNG is broken
            {"task_id": "side-01", "status": "succeeded", "error": None},
            {"task_id": "back_01", "status": "succeeded", "error": None},
            {"task_id": "intruder", "status": "succeeded", "error": None},
        ],
    )
    artifacts = adapter.collect_outputs(request, tmp_path)
    assert [(a.task_id, a.artifact_id, a.is_primary) for a in artifacts] == [
        ("side-01", "art_01", True),
        ("back_01", "art_02", False),
    ]
    warning = batch_partial(request, artifacts, adapter.task_report(request, tmp_path))
    assert warning.code == "BATCH_PARTIAL" and warning.details["failed"] == ["front_01"]
    assert warning.details["tasks"]["front_01"]["message"] == "The task produced no valid PNG."


def test_task_report_tolerates_a_missing_or_malformed_file(tmp_path):
    adapter = default_registry().adapter("mock-t2d-basic")
    request = batch_request("mock-t2d-basic")
    assert adapter.task_report(request, tmp_path) == {}
    (tmp_path / "task_results.json").write_text("{torn", encoding="utf-8")
    assert adapter.task_report(request, tmp_path) == {}
    with pytest.raises(ArtifactInvalidError):
        adapter.collect_outputs(request, tmp_path)


def test_batch_partial_separates_failed_and_not_run_and_is_absent_when_all_succeeded():
    request = batch_request("mock-t2d-basic")
    one = [
        Artifact(
            artifact_id="art_01",
            kind="image",
            format="png",
            mime_type="image/png",
            size_bytes=1,
            sha256="x",
            width=1,
            height=1,
            is_primary=True,
            path="p",
            task_id="front_01",
        )
    ]
    report = {
        "side-01": {"status": "failed", "message": "RuntimeError: boom", "reason": None},
        "back_01": {"status": "not_run", "message": "budget", "reason": "deadline"},
    }
    warning = batch_partial(request, one, report)
    assert warning.details["failed"] == ["side-01"] and warning.details["not_run"] == ["back_01"]
    assert warning.details["tasks"]["back_01"]["reason"] == "deadline"
    everything = [
        a.model_copy(update={"task_id": t})
        for a, t in zip(one * 3, ["front_01", "side-01", "back_01"], strict=True)
    ]
    assert batch_partial(request, everything, {}) is None


# --- the real remote entry's batch loop (model calls replaced) --------------------------------------------------


class _FakeTorch:
    def __init__(self, key):
        self.device, self.dtype, self.cpu_test = "cuda:0", "torch.float16", False


def _patch_entry(monkeypatch, tmp_path, renderer):
    monkeypatch.setattr(remote_entry, "_install", lambda pins, progress: None)
    monkeypatch.setattr(remote_entry, "_download", lambda recipe, progress: tmp_path / "weights")
    monkeypatch.setattr(remote_entry, "_Torch", _FakeTorch)
    monkeypatch.setattr(remote_entry, "_check", lambda image: None)
    monkeypatch.setattr(remote_entry, "_save_png", lambda image, path: path.write_bytes(b"png:" + image))
    monkeypatch.setitem(remote_entry.FAMILIES, "flux2_klein", renderer)


def test_remote_entry_loads_once_records_failures_and_stops_at_the_deadline(monkeypatch, tmp_path, capsys):
    def renderer(batch, folder, rt, progress):
        batch.model_loaded()
        for item in batch.pending():
            time.sleep(0.15)
            if item["task_id"] == "side-01":
                batch.failed(item, RuntimeError("CUDA out of memory"))
            else:
                batch.done(item, item["task_id"].encode())

    _patch_entry(monkeypatch, tmp_path, renderer)
    arguments = (
        full_registry()
        .adapter("flux2-klein-4b")
        .build_batch_arguments(
            batch_request("flux2-klein-4b", ("front_01", "side-01", "back_01", "extra_01"))
        )
    )
    arguments["deadline_seconds"] = 0.4
    out = tmp_path / "out"
    remote_entry.main(arguments, tmp_path, out, lambda *a: None)
    rows = json.loads((out / "task_results.json").read_text(encoding="utf-8"))["tasks"]
    assert [(r["task_id"], r["status"]) for r in rows] == [
        ("front_01", "succeeded"),
        ("side-01", "failed"),
        ("back_01", "not_run"),
        ("extra_01", "not_run"),
    ]
    assert rows[1]["error"]["message"] == "RuntimeError: CUDA out of memory"
    assert rows[2]["error"]["reason"] == "deadline" and rows[0]["seed"] == 0
    assert (out / "task_front_01.png").read_bytes() == b"png:front_01"
    log = capsys.readouterr().out
    assert log.count("MODEL_LOAD flux2-klein-4b ") == 1 and "1 of 4 task(s) succeeded; 1 model load(s)" in log


def test_remote_entry_batch_fails_only_when_no_task_succeeded(monkeypatch, tmp_path):
    def renderer(batch, folder, rt, progress):
        batch.model_loaded()
        for item in batch.pending():
            batch.failed(item, RuntimeError("blank"))

    _patch_entry(monkeypatch, tmp_path, renderer)
    arguments = (
        full_registry().adapter("flux2-klein-4b").build_batch_arguments(batch_request("flux2-klein-4b"))
    )
    with pytest.raises(RuntimeError, match="No task of this batch succeeded"):
        remote_entry.main(arguments, tmp_path, tmp_path / "out", lambda *a: None)
    rows = json.loads((tmp_path / "out" / "task_results.json").read_text(encoding="utf-8"))["tasks"]
    assert {r["status"] for r in rows} == {"failed"}


def test_a_single_image_job_still_fails_with_its_own_error(monkeypatch, tmp_path):
    def renderer(batch, folder, rt, progress):
        for item in batch.pending():
            batch.failed(item, RuntimeError("The model produced a blank image."))

    _patch_entry(monkeypatch, tmp_path, renderer)
    from tests.unit.test_real_text_to_2d import adapter, generation

    arguments = adapter("flux2-klein-4b").build_arguments(generation("flux2-klein-4b"))
    with pytest.raises(RuntimeError, match="blank image"):
        remote_entry.main(arguments, tmp_path, tmp_path / "out", lambda *a: None)
    assert not (tmp_path / "out" / "task_results.json").exists()


# --- the mock remote entry --------------------------------------------------------------------------------------


def test_mock_entry_batch_writes_one_png_per_task_and_honours_the_failure_hook(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("AAS_MOCK_FAIL_TASKS", "side-01")
    arguments = (
        default_registry()
        .adapter("mock-t2d-basic")
        .build_batch_arguments(
            batch_request("mock-t2d-basic").model_copy(
                update={
                    "tasks": [
                        GenerationTask(task_id=t, prompt="p", options={"seed": 1, "width": 64, "height": 64})
                        for t in ("front_01", "side-01")
                    ]
                }
            )
        )
    )
    mock_entry.main(arguments, tmp_path, tmp_path / "out", lambda *a: None)
    rows = json.loads((tmp_path / "out" / "task_results.json").read_text(encoding="utf-8"))["tasks"]
    assert [r["status"] for r in rows] == ["succeeded", "failed"]
    with Image.open(tmp_path / "out" / "task_front_01.png") as image:
        assert image.size == (64, 64)
    assert capsys.readouterr().out.count("MODEL_LOAD ") == 1
