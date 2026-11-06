"""Live Kaggle tests. Opt-in only: ``pytest -m kaggle`` (the default run excludes them).

They use the active profile from ``.env`` (``AAS_ACTIVE_PROFILE``, default ``sunny`` per D-025). Only read-only
commands and **CPU** kernels run here; nothing uses GPU quota. GPU runs need the owner's approval and are done by
hand (DECISIONS, M3 acceptance log).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from aas_backend.profiles import environment, load_profiles
from aas_backend.settings import Settings
from kaggle_connector.client import KaggleCliClient, KaggleJobSpec, OutputSpec

pytestmark = pytest.mark.kaggle
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    env = environment(REPO / ".env")
    settings = Settings(
        _env_file=None,
        compute_mode="kaggle",
        compute_profiles=env.get("AAS_COMPUTE_PROFILES", "sunny"),
        active_profile=env.get("AAS_ACTIVE_PROFILE") or "sunny",
    )
    compute = KaggleCliClient(load_profiles(settings, env), background_refresh=False)
    yield compute
    compute.close()


def active(client: KaggleCliClient) -> str:
    return next(p.profile_id for p in client.profiles() if p.enabled)


def test_live_auth_and_quota(client):
    snapshot = client.snapshot(active(client), refresh=True)
    assert snapshot.authentication_status == "authenticated", [e.message for e in snapshot.error]
    assert snapshot.source.quota == "kaggle_cli_quota"
    assert snapshot.gpu_quota_total_hours is not None and snapshot.gpu_quota_remaining_hours is not None


def wait_terminal(client: KaggleCliClient, ref: str, limit: float = 900) -> str:
    deadline = time.monotonic() + limit
    state = "queued"
    while time.monotonic() < deadline:
        state = client.status(ref)
        if state in ("complete", "error"):
            return state
        time.sleep(10)
    return state


def test_live_cpu_round_trip_with_input_dataset(client, tmp_path: Path):
    """Dataset upload → mount → run → output download → manifest check, on CPU (the mock i3d entry needs no GPU)."""
    from kaggle_connector.jobs.manifest import read_manifest, verify_outputs
    from kaggle_connector.jobs.packaging import OUTPUT_DIR_NAME
    from models.adapters.base import PACKAGE_ROOT
    from tests.conftest import image_bytes

    front = tmp_path / "in_01_front.png"
    front.write_bytes(image_bytes(256, 384, color=(30, 120, 200)))
    job_id = f"job_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_live02"
    spec = KaggleJobSpec(
        job_id=job_id,
        profile_id=active(client),
        accelerator_id="cpu",
        timeout_seconds=900,
        entrypoint_file=PACKAGE_ROOT / "models/adapters/mock_image_to_3d/remote_entry.py",
        arguments={
            "views": {"front": front.name},
            "details": [],
            "asset_category": "character",
            "model_id": "mock-i3d-single",
            "texture_resolution": 512,
            "seed": None,
        },
        input_files=[front],
        expected_outputs=[
            OutputSpec("model.glb", "model_3d", "glb", True),
            OutputSpec("preview.png", "preview", "png", False),
        ],
    )
    client.refresh(spec.profile_id, force=True)
    started = time.monotonic()
    client.upload_inputs(spec)
    uploaded = time.monotonic()
    ref = client.submit(spec)
    state = wait_terminal(client, ref)
    finished = time.monotonic()
    dest = tmp_path / "remote_raw"
    if state == "complete":
        client.download(ref, dest)
    lines, _ = client.logs(ref, 0)
    report = {
        "ref": ref,
        "state": state,
        "upload_seconds": round(uploaded - started),
        "run_seconds": round(finished - uploaded),
        "files": sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
        if dest.exists()
        else [],
        "lines": [line for line in lines if not line.startswith("AAS_TELEMETRY")][-12:],
    }
    print(json.dumps(report, indent=2))
    client.release(ref, succeeded=state == "complete")
    assert state == "complete", report
    manifest = read_manifest(dest / OUTPUT_DIR_NAME)
    verify_outputs(manifest, dest / OUTPUT_DIR_NAME, job_id)
    assert {o.name for o in manifest.outputs} == {"model.glb", "preview.png"}


def test_live_failing_cpu_kernel_reports_error_with_readable_logs(client, tmp_path: Path):
    entry = tmp_path / "entry.py"
    entry.write_text(
        "def main(arguments, input_dir, output_dir, progress):\n"
        "    progress('inference', 10, 'about to fail on purpose')\n"
        "    raise RuntimeError('Deliberate failure (M3 acceptance)')\n",
        encoding="utf-8",
    )
    job_id = f"job_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_live01"
    spec = KaggleJobSpec(
        job_id=job_id,
        profile_id=active(client),
        accelerator_id="cpu",
        timeout_seconds=600,
        entrypoint_file=entry,
        arguments={},
        expected_outputs=[OutputSpec("image.png", "image", "png", True)],
    )
    client.refresh(spec.profile_id, force=True)
    ref = client.submit(spec)
    deadline = time.monotonic() + 900
    state = "queued"
    while time.monotonic() < deadline:
        state = client.status(ref)
        if state in ("complete", "error"):
            break
        time.sleep(10)
    lines, _ = client.logs(ref, 0)
    report = {"ref": ref, "state": state, "lines": lines[-15:]}
    (tmp_path / "live_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    assert state == "error"
    assert any("ERROR entrypoint failed: RuntimeError: Deliberate failure" in line for line in lines)
    client.release(ref, succeeded=True)  # test cleanup: also delete this deliberately failed kernel
