"""The generated Kaggle kernel script runs end to end (with its filesystem root re-pointed to a temp folder)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from kaggle_connector.client import KaggleJobSpec, OutputSpec
from kaggle_connector.jobs.kaggle_package import (
    KERNEL_FILE,
    dataset_slug_for,
    slug_for,
    write_dataset_package,
    write_kernel_package,
)
from models.adapters.base import PACKAGE_ROOT
from tests.conftest import image_bytes

JOB_ID = "job_20261106T101500Z_a1b2c3"
OWNER = "aas-test-user"


def spec(tmp_path: Path, entry: Path | None = None) -> KaggleJobSpec:
    front = tmp_path / "in_01_front.png"
    front.write_bytes(image_bytes(256, 384))
    return KaggleJobSpec(
        job_id=JOB_ID,
        profile_id="sunny",
        accelerator_id="gpu_t4x2",
        timeout_seconds=780,
        entrypoint_file=entry or PACKAGE_ROOT / "models/adapters/mock_image_to_3d/remote_entry.py",
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


def run_kernel(tmp_path: Path, job: KaggleJobSpec) -> tuple[subprocess.CompletedProcess, Path]:
    root = tmp_path / "root"
    dataset = dataset_slug_for(JOB_ID)
    # Mounted somewhere other than /kaggle/input/<slug>: the marker search must find it.
    write_dataset_package(
        job, root / "kaggle" / "input" / "datasets" / OWNER / dataset, owner=OWNER, slug=dataset
    )
    folder = write_kernel_package(
        job,
        tmp_path / "kernel",
        owner=OWNER,
        slug=slug_for(JOB_ID),
        dataset_ref=f"{OWNER}/{dataset}",
        gpu=True,
    )
    source = (folder / KERNEL_FILE).read_text(encoding="utf-8")
    assert source.count('ROOT = Path("/")') == 1
    script = tmp_path / "run_kernel.py"
    script.write_text(source.replace('ROOT = Path("/")', f"ROOT = Path({str(root)!r})"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("KAGGLE", "AAS_PROFILE"))}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    done = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=120, env=env
    )
    return done, root / "kaggle" / "working" / "aas_output"


def test_metadata_is_private_without_internet(tmp_path: Path):
    job = spec(tmp_path)
    folder = write_kernel_package(
        job, tmp_path / "k", owner=OWNER, slug=slug_for(JOB_ID), dataset_ref=None, gpu=False
    )
    meta = json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))
    assert meta["is_private"] is True and meta["enable_internet"] is False and meta["enable_gpu"] is False
    assert (
        meta["code_file"] == KERNEL_FILE
        and meta["kernel_type"] == "script"
        and meta["title"] == meta["id"].split("/")[1]
    )
    assert sorted(p.name for p in folder.iterdir()) == [KERNEL_FILE, "kernel-metadata.json"]


def test_generated_kernel_runs_the_job_and_writes_the_manifest(tmp_path: Path):
    done, output = run_kernel(tmp_path, spec(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "ok" and manifest["job_id"] == JOB_ID
    assert {o["name"] for o in manifest["outputs"]} == {"model.glb", "preview.png"}
    assert (output / "model.glb").read_bytes()[:4] == b"glTF"
    assert '"stage":"finished"' in done.stdout and "AAS_TELEMETRY " in done.stdout


def test_generated_kernel_fails_loudly_when_the_entrypoint_raises(tmp_path: Path):
    broken = tmp_path / "broken_entry.py"
    broken.write_text(
        "def main(arguments, input_dir, output_dir, progress):\n    raise ValueError('boom')\n",
        encoding="utf-8",
    )
    done, output = run_kernel(tmp_path, spec(tmp_path, broken))
    assert done.returncode != 0
    assert "ERROR entrypoint failed: ValueError: boom" in done.stdout
    assert "AI Asset Studio job failed" in done.stderr  # an exception, so Kaggle reports ERROR
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "error" and manifest["error"]["code"] == "KAGGLE_KERNEL_ERROR"
