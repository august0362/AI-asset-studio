"""KaggleCliClient through the real backend, against the recorded-format fake CLI (no network, no quota).

Covers the M3 acceptance flow offline: lifecycle with input upload, status mapping and the post-push grace window,
live and final logs, GPU0/GPU1 telemetry, download + manifest checks, dataset cleanup, the deliberate kernel failure,
submission that is never retried, auth checks, and the CONTRACTS §10 secret-leak scan.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aas_backend.app import create_app
from kaggle_connector.client import KaggleCliClient, KaggleProfileConfig
from models.registry import ModelRegistry, default_registry, full_registry
from tests.conftest import API, i3d_body, image_bytes, make_settings, request_body
from tests.kaggle_fake import FakeKaggleCli

TOKEN = "KGAT_fake_m3_token_0123456789abcdef"
OWNER = "leaky-owner-name"


@dataclass
class KaggleHarness:
    client: TestClient
    compute: KaggleCliClient
    fake: FakeKaggleCli
    data_dir: Path

    def wait(self, job_id: str, timeout: float = 60.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.client.get(f"{API}/jobs/{job_id}/status").json()["status"] in ("completed", "failed"):
                return self.client.get(f"{API}/jobs/{job_id}").json()
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} did not finish")

    def upload_front(self) -> str:
        files = {"file": ("front.png", image_bytes(640, 960), "image/png")}
        response = self.client.post(f"{API}/uploads", files=files)
        assert response.status_code == 201, response.text
        return response.json()["upload_id"]

    def logs(self, job_id: str) -> list[str]:
        return [line["text"] for line in self.client.get(f"{API}/jobs/{job_id}/logs").json()["lines"]]


def profiles(username: str = OWNER) -> list[KaggleProfileConfig]:
    return [
        KaggleProfileConfig("sunny", username, True, True, token=TOKEN, display_name="Sunny"),
        KaggleProfileConfig("atume", "", True, False),
    ]


@pytest.fixture
def kaggle_factory(tmp_path: Path) -> Iterator[Callable[..., KaggleHarness]]:
    opened: list[tuple[TestClient, KaggleCliClient]] = []

    def factory(
        *,
        username: str = OWNER,
        refresh: bool = True,
        test_failure: str | None = None,
        registry: ModelRegistry | None = None,
        **fake_options: Any,
    ) -> KaggleHarness:
        fake = FakeKaggleCli(tmp_path / "kaggle", owner=OWNER, **fake_options)
        compute = KaggleCliClient(
            profiles(username),
            cli_factory=lambda config, redact: fake,
            work_root=tmp_path / "work",
            background_refresh=False,
            dataset_poll_seconds=0.01,
            test_failure=test_failure,
        )
        if refresh:
            compute.refresh("sunny")
        settings = make_settings(tmp_path / "data", compute_mode="kaggle", poll_seconds=0.05)
        client = TestClient(create_app(settings, client=compute, registry=registry or default_registry()))
        client.__enter__()
        opened.append((client, compute))
        return KaggleHarness(client, compute, fake, tmp_path / "data")

    yield factory
    for client, compute in reversed(opened):
        client.__exit__(None, None, None)
        compute.close()


def i3d_single(upload_id: str) -> dict[str, Any]:
    return i3d_body(
        [{"upload_id": upload_id, "role": "front"}],
        model_id="mock-i3d-single",
        compute={"profile_id": "sunny", "accelerator_id": "gpu_t4x2"},
    )


def statuses(job: dict[str, Any]) -> list[str]:
    return [entry["status"] for entry in job["status_history"]]


def test_smoke_job_runs_the_full_lifecycle_with_inputs(kaggle_factory):
    h = kaggle_factory()
    response = h.client.post(f"{API}/jobs", json=i3d_single(h.upload_front()))
    assert response.status_code == 201, response.text
    job = h.wait(response.json()["job_id"])
    assert job["status"] == "completed", job["error"]
    assert statuses(job) == ["created", "uploading", "queued", "running", "downloading", "completed"]
    assert {a["format"] for a in job["artifacts"]} == {"glb", "png"}
    assert job["execution"]["backend"] == "kaggle"
    assert job["execution"]["remote_ref"].startswith("sunny/aas-job-")

    kernel = next(iter(h.fake.kernels.values()))
    assert kernel.accelerator == "NvidiaTeslaT4" and kernel.timeout and int(kernel.timeout) > 0
    meta = kernel.metadata
    assert meta["is_private"] is True and meta["enable_internet"] is False and meta["enable_gpu"] is True
    assert meta["id"] == f"{OWNER}/{kernel.slug}" and kernel.slug.startswith("aas-")
    assert meta["dataset_sources"] == [f"{OWNER}/aas-in-{kernel.slug.removeprefix('aas-')}"]
    assert wait_for(
        lambda: h.fake.deleted_datasets == meta["dataset_sources"]
    )  # released once terminal (DF-08)
    assert wait_for(lambda: h.fake.deleted_kernels == [meta["id"]])  # every finished job's kernel (§14.7)

    for artifact in job["artifacts"]:
        assert h.client.get(f"{API}{artifact['content_url'].removeprefix('/api/v1')}").status_code == 200
    logs = h.logs(job["job_id"])
    assert any("AAS_PROGRESS" in line for line in logs)
    assert not any(line.startswith("Warning: Looks like") for line in logs)
    assert not any(line.startswith("AAS_TELEMETRY") for line in logs)  # stored separately (§5)

    samples = [
        json.loads(line)
        for line in (h.data_dir / "logs" / f"{job['job_id']}.telemetry.jsonl").read_text().splitlines()
    ]
    assert samples and [g["index"] for g in samples[0]["gpus"]] == [0, 1]
    assert samples[0]["gpus"][0]["utilization_percent"] != samples[0]["gpus"][1]["utilization_percent"]


def test_cpu_job_without_inputs_skips_uploading(kaggle_factory):
    h = kaggle_factory(denied_status_calls=0, queued_status_calls=0)
    body = request_body(compute={"profile_id": "sunny", "accelerator_id": "cpu"})
    job = h.wait(h.client.post(f"{API}/jobs", json=body).json()["job_id"])
    assert job["status"] == "completed", job["error"]
    assert "uploading" not in statuses(job)
    kernel = next(iter(h.fake.kernels.values()))
    assert kernel.accelerator is None and kernel.metadata["enable_gpu"] is False
    assert kernel.metadata["dataset_sources"] == [] and h.fake.deleted_datasets == []


def wait_for(condition, timeout: float = 5.0) -> bool:
    """Cleanup runs right after the job becomes terminal, on the session thread."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


def test_test_switch_makes_the_real_notebook_fail_and_its_kernel_is_deleted(kaggle_factory):
    """AAS_KAGGLE_TEST_FAILURE=kernel_error: the generated notebook itself raises (D-031). Since D-041 the failed
    job's kernel is deleted too, after its final logs are stored (CONTRACTS §14.7)."""
    h = kaggle_factory(test_failure="kernel_error")
    body = request_body(compute={"profile_id": "sunny", "accelerator_id": "cpu"})
    job = h.wait(h.client.post(f"{API}/jobs", json=body).json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "KAGGLE_KERNEL_ERROR"
    logs = h.logs(job["job_id"])
    assert any("AAS_KAGGLE_TEST_FAILURE=kernel_error is on" in line for line in logs)
    assert any("ERROR entrypoint failed: RuntimeError: Deliberate test failure" in line for line in logs)
    error_at = next(i for i, line in enumerate(logs) if "ERROR entrypoint failed" in line)
    noted_at = next(i for i, line in enumerate(logs) if line.startswith("Kaggle reported:"))
    assert noted_at > error_at  # the local note comes after the remote lines
    kernel = next(iter(h.fake.kernels.values()))
    assert wait_for(lambda: h.fake.deleted_kernels == [kernel.metadata["id"]])  # §14.7: failed jobs too
    assert any("Remote run cleaned up" in line for line in h.logs(job["job_id"]))


def test_deliberately_failing_notebook_ends_with_kernel_error_and_readable_logs(kaggle_factory):
    h = kaggle_factory(break_entry=True)
    body = request_body(compute={"profile_id": "sunny", "accelerator_id": "cpu"})
    job = h.wait(h.client.post(f"{API}/jobs", json=body).json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "KAGGLE_KERNEL_ERROR" and job["error"]["retryable"] is False
    logs = h.logs(job["job_id"])
    assert any("ERROR entrypoint failed: RuntimeError: Deliberate failure" in line for line in logs)
    assert any(line.startswith("Kaggle reported:") for line in logs)


def test_failed_push_is_never_resubmitted_and_frees_the_dataset(kaggle_factory):
    h = kaggle_factory(fail_push="Notebook not found")
    job = h.wait(h.client.post(f"{API}/jobs", json=i3d_single(h.upload_front())).json()["job_id"])
    assert job["status"] == "failed"
    assert job["error"]["code"] == "KAGGLE_SUBMIT_FAILED" and job["error"]["retryable"] is True
    assert [c[:2] for c in h.fake.calls].count(["kernels", "push"]) == 1
    assert len(h.fake.deleted_datasets) == 1 and not h.fake.datasets


def test_transient_status_errors_are_retried_and_counted(kaggle_factory):
    h = kaggle_factory(status_errors=2)
    body = request_body(compute={"profile_id": "sunny", "accelerator_id": "cpu"})
    job = h.wait(h.client.post(f"{API}/jobs", json=body).json()["job_id"])
    assert job["status"] == "completed", job["error"]
    assert job["execution"]["transient_retries"] == 2


def test_snapshot_reports_real_auth_and_quota(kaggle_factory):
    h = kaggle_factory()
    snap = h.client.get(f"{API}/compute/profiles/sunny/snapshot").json()
    assert snap["authentication_status"] == "authenticated"
    assert (snap["gpu_quota_total_hours"], snap["gpu_quota_remaining_hours"]) == (30.0, 4.87)
    assert snap["tpu_quota_total_hours"] == 20.0
    assert snap["quota_reset_at"] == "2026-11-07T00:00:00Z"
    assert snap["source"]["quota"] == "kaggle_cli_quota" and snap["freshness_status"]["quota"] == "fresh"
    assert snap["session_status"] == "none"
    profiles_view = h.client.get(f"{API}/compute/profiles").json()["profiles"]
    assert [(p["profile_id"], p["enabled"], p["mode"]) for p in profiles_view] == [
        ("sunny", True, "kaggle"),
        ("atume", False, "kaggle"),
    ]
    assert {a["accelerator_id"] for a in profiles_view[0]["accelerators"]} == {"cpu", "gpu_t4x2"}
    assert h.client.get(f"{API}/compute/profiles/atume/snapshot").status_code == 404


def test_old_cli_without_quota_reports_unknown(kaggle_factory):
    h = kaggle_factory(quota=None)
    snap = h.client.get(f"{API}/compute/profiles/sunny/snapshot").json()
    assert snap["authentication_status"] == "authenticated"
    assert snap["gpu_quota_remaining_hours"] is None and snap["freshness_status"]["quota"] == "unavailable"
    assert "COMPUTE_QUOTA_UNKNOWN" in [e["code"] for e in snap["error"]]


def test_token_of_another_account_is_rejected(kaggle_factory):
    h = kaggle_factory(username="someone-else")
    snap = h.client.get(f"{API}/compute/profiles/sunny/snapshot").json()
    assert snap["authentication_status"] == "invalid_credentials"
    message = next(e["message"] for e in snap["error"] if e["code"] == "KAGGLE_AUTH_FAILED")
    assert "different account" in message and OWNER not in message and "someone-else" not in message
    report = h.client.post(
        f"{API}/validate", json=request_body(compute={"profile_id": "sunny", "accelerator_id": "cpu"})
    ).json()
    assert "COMPUTE_PROFILE_UNAUTHENTICATED" in [e["code"] for e in report["errors"]]
    assert not any(c[:2] == ["kernels", "push"] for c in h.fake.calls)


def test_live_telemetry_reaches_the_snapshot_with_gpus_separate(kaggle_factory):
    h = kaggle_factory(denied_status_calls=0, queued_status_calls=0)
    body = request_body(compute={"profile_id": "sunny", "accelerator_id": "gpu_t4x2"})
    job = h.wait(h.client.post(f"{API}/jobs", json=body).json()["job_id"])
    assert job["status"] == "completed", job["error"]
    snap = h.compute.snapshot("sunny")
    assert snap.session_status == "finished" and snap.accelerator_type == "gpu_t4x2"
    # After the run the session is not running, so host/gpu are not_applicable (never shown as live).
    assert snap.freshness_status.gpu == "not_applicable"
    assert h.compute._accounts["sunny"].monitor.telemetry is not None
    assert [g.index for g in h.compute._accounts["sunny"].monitor.telemetry.gpus] == [0, 1]


def test_resumed_run_after_restart_is_identified_by_its_reference(kaggle_factory, tmp_path):
    h = kaggle_factory(denied_status_calls=0, queued_status_calls=0)
    body = request_body(compute={"profile_id": "sunny", "accelerator_id": "cpu"})
    job = h.wait(h.client.post(f"{API}/jobs", json=body).json()["job_id"])
    ref = job["execution"]["remote_ref"]
    fresh = KaggleCliClient(
        profiles(), cli_factory=lambda c, r: h.fake, work_root=tmp_path / "w2", background_refresh=False
    )
    fresh.refresh("sunny")
    assert fresh.status(ref) == "complete"
    lines, offset = fresh.logs(ref, 0)
    assert offset == len(lines) and any("AAS_PROGRESS" in line for line in lines)
    fresh.close()


def test_no_secret_leaks_into_data_responses_or_packages(kaggle_factory):
    """CONTRACTS §10: a known fake token (and the account name) never appear in data/, API responses or packages."""
    h = kaggle_factory(secret_echo=f"KAGGLE_API_TOKEN={TOKEN} user={OWNER}")
    response = h.client.post(f"{API}/jobs", json=i3d_single(h.upload_front()))
    job = h.wait(response.json()["job_id"])
    assert job["status"] == "completed", job["error"]
    bodies = [
        response.text,
        h.client.get(f"{API}/jobs/{job['job_id']}").text,
        h.client.get(f"{API}/jobs/{job['job_id']}/logs").text,
        h.client.get(f"{API}/jobs").text,
        h.client.get(f"{API}/compute/profiles").text,
        h.client.get(f"{API}/compute/profiles/sunny/snapshot?refresh=1").text,
    ]
    stored = [p.read_bytes().decode("utf-8", "replace") for p in h.data_dir.rglob("*") if p.is_file()]
    for text in bodies + stored:
        assert TOKEN not in text and "KGAT_" not in text
        assert OWNER not in text.lower()
    assert any("[REDACTED]" in text for text in stored)  # the echoed line was kept, redacted
    for source in h.fake.pushed_sources:
        assert TOKEN not in source and "KGAT_" not in source


# --- real Text→2D models (D-034): validation and kernel set-up, never a real run -------------------------------


def real_body(model_id: str, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "model_id": model_id,
        "asset_category": "character",
        "prompt": "1girl, silver hair, full body",
        "options": {"seed": 1, "width": 832, "height": 1216},
        "compute": {"profile_id": "sunny", "accelerator_id": "gpu_t4x2"},
    }
    return request_body(**{**values, **overrides})


@pytest.mark.parametrize(
    ("model_id", "seconds"), [("animagine-xl-4", 25), ("flux2-klein-4b", 9), ("moss-image-sft", 354)]
)
def test_real_model_plans_on_t4_with_its_measured_time(kaggle_factory, model_id, seconds):
    h = kaggle_factory(registry=full_registry())
    report = h.client.post(f"{API}/validate", json=real_body(model_id)).json()
    assert report["valid"], report["errors"]
    plan = report["resource_plan"]
    assert plan["accelerator_id"] == "gpu_t4x2" and plan["fit"] == "ok"
    assert plan["estimate_basis"]["estimated_runtime_seconds"] == seconds


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"compute": {"profile_id": "sunny", "accelerator_id": "cpu"}},
            [("MODEL_ACCELERATOR_INCOMPATIBLE", "compute.accelerator_id")],
        ),
        ({"asset_category": "weapon"}, [("MODEL_CATEGORY_INCOMPATIBLE", "asset_category")]),
        ({"options": {"negative_prompt": "text"}}, [("MODEL_OPTION_UNSUPPORTED", "options.negative_prompt")]),
        ({"options": {"width": 900}}, [("MODEL_OPTION_INVALID", "options.width")]),
        ({"options": {"width": 832, "height": 832}}, [("MODEL_OPTION_INVALID", "options.height")]),
        ({"prompt": None}, [("MODEL_PROMPT_REQUIRED", "prompt")]),
    ],
)
def test_real_model_requests_are_validated_before_any_kernel(kaggle_factory, overrides, expected):
    h = kaggle_factory(registry=full_registry())
    body = real_body("flux2-klein-4b", **overrides)
    report = h.client.post(f"{API}/validate", json=body).json()
    assert [(e["code"], e["field"]) for e in report["errors"]] == expected
    assert h.client.post(f"{API}/jobs", json=body).status_code == 422
    assert h.fake.kernels == {}


def test_real_model_kernel_has_internet_one_t4_and_the_pinned_recipe(kaggle_factory):
    """The entry is replaced by a failing stub (no install, no download); the pushed package is what is checked."""
    h = kaggle_factory(registry=full_registry(), break_entry=True)
    response = h.client.post(f"{API}/jobs", json=real_body("animagine-xl-4"))
    assert response.status_code == 201, response.text
    job = h.wait(response.json()["job_id"])
    assert job["status"] == "failed"
    kernel = next(iter(h.fake.kernels.values()))
    assert kernel.metadata["enable_internet"] is True and kernel.metadata["enable_gpu"] is True
    assert kernel.metadata["dataset_sources"] == []  # text-only: no input dataset
    assert kernel.accelerator == "NvidiaTeslaT4"
    arguments = json.loads((kernel.sandbox / "pkg" / "job.json").read_text(encoding="utf-8"))["arguments"]
    assert arguments["recipe"]["repo"] == "cagliostrolab/animagine-xl-4.0"
    assert arguments["pins"] == ["diffusers==0.42.1", "transformers==5.22.1", "accelerate==1.15.0"]
    assert arguments["prompt"].endswith("absurdres") and arguments["seed"] == 1


# --- run groups through the real client (CONTRACTS §14.4, D-042 (9)) ---------------------------------------------


def style_group_registry() -> ModelRegistry:
    from models.contracts import ModelCapabilities
    from models.registry import MOCK_CAPABILITIES

    base = next(c for c in MOCK_CAPABILITIES if c.model_id == "mock-t2d-styleref").model_dump()
    record = {
        **base,
        "model_id": "mock-t2d-style-group",
        "runtime": {**base["runtime"], "minimum_gpu_vram_bytes": 8 * 2**30},
        "unknown_requirements": [],
    }
    return ModelRegistry([*MOCK_CAPABILITIES, ModelCapabilities.model_validate(record)])


def test_a_run_group_with_style_images_attaches_both_datasets_and_cleans_up(kaggle_factory):
    h = kaggle_factory(registry=style_group_registry(), denied_status_calls=0, queued_status_calls=0)
    ids = []
    for color in ((200, 40, 40), (40, 40, 200)):
        files = {"file": ("style.png", image_bytes(512, 512, color=color), "image/png")}
        upload = h.client.post(f"{API}/uploads", files=files).json()["upload_id"]
        body = request_body(
            model_id="mock-t2d-style-group",
            inputs=[{"upload_id": upload, "role": "style_reference"}],
            options={"seed": 1},
            compute={"profile_id": "sunny", "accelerator_id": "gpu_t4x2"},
            auto_run=False,
        )
        response = h.client.post(f"{API}/jobs", json=body)
        assert response.status_code == 201, response.text
        ids.append(response.json()["job_id"])
    group = h.client.post(f"{API}/jobs/groups", json={"job_ids": ids})
    assert group.status_code == 201, group.text
    jobs = [h.wait(job_id) for job_id in ids]
    assert [j["status"] for j in jobs] == ["completed", "completed"], [j["error"] for j in jobs]
    assert len(h.fake.kernels) == 1  # one kernel, one session
    kernel = next(iter(h.fake.kernels.values()))
    assert kernel.slug == "aas-" + group.json()["group_id"].replace("_", "-")
    assert kernel.accelerator == "NvidiaTeslaT4" and kernel.metadata["is_private"] is True
    assert len(kernel.metadata["dataset_sources"]) == 2  # each job keeps its own input dataset
    assert all(j["execution"]["remote_ref"] == f"sunny/{kernel.slug}" for j in jobs)
    assert wait_for(lambda: h.fake.deleted_kernels == [kernel.metadata["id"]])
    assert wait_for(lambda: sorted(h.fake.deleted_datasets) == sorted(kernel.metadata["dataset_sources"]))
    for job in jobs:
        assert statuses(job) == ["created", "uploading", "queued", "running", "downloading", "completed"]
        assert not any(OWNER in line for line in h.logs(job["job_id"]))
