"""The generated Kaggle kernel script runs end to end (with its filesystem root re-pointed to a temp folder)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from kaggle_connector.client import KaggleGroupSpec, KaggleJobSpec, OutputSpec
from kaggle_connector.jobs.kaggle_package import (
    KERNEL_FILE,
    dataset_slug_for,
    slug_for,
    write_dataset_package,
    write_group_kernel_package,
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


# --- run groups (CONTRACTS §14.4) and coded errors (§14.8) -----------------------------------------------------------

GROUP_ID = "grp_0123456789ab"
JOB_B = "job_20261106T101501Z_d4e5f6"
REPORT_ENTRY = (
    "import json, os\n"
    "from pathlib import Path\n"
    "def main(arguments, input_dir, output_dir, progress):\n"
    "    progress('inference', 50, 'working')\n"
    "    print('plain line from ' + arguments['name'], flush=True)\n"
    "    if arguments.get('fail'):\n"
    "        raise RuntimeError('member failed on purpose')\n"
    "    files = sorted(p.name for p in Path(input_dir).iterdir()) if Path(input_dir).is_dir() else []\n"
    "    Path(output_dir).mkdir(parents=True, exist_ok=True)\n"
    "    (Path(output_dir) / 'seen.json').write_text(json.dumps({\n"
    "        'gpu': os.environ.get('CUDA_VISIBLE_DEVICES'), 'aas_gpu': os.environ.get('AAS_GPU_INDEX'),\n"
    "        'inputs': files}))\n"
)


def member(
    tmp_path: Path, job_id: str, name: str, *, fail: bool = False, with_input: bool = True
) -> KaggleJobSpec:
    entry = tmp_path / f"entry_{name}.py"
    entry.write_text(REPORT_ENTRY, encoding="utf-8")
    inputs = []
    if with_input:
        image = tmp_path / f"{name}_in_01_style_reference.png"
        image.write_bytes(image_bytes(256, 256))
        inputs = [image]
    return KaggleJobSpec(
        job_id=job_id,
        profile_id="sunny",
        accelerator_id="gpu_t4x2",
        timeout_seconds=600,
        entrypoint_file=entry,
        arguments={"name": name, "fail": fail},
        input_files=inputs,
        expected_outputs=[OutputSpec("seen.json", "image", "png", True)],
    )


def run_group_kernel(tmp_path: Path, group: KaggleGroupSpec) -> tuple[subprocess.CompletedProcess, Path]:
    root = tmp_path / "root"
    refs = []
    for job in group.members:
        if job.input_files:
            dataset = dataset_slug_for(job.job_id)
            write_dataset_package(
                job, root / "kaggle" / "input" / "datasets" / OWNER / dataset, owner=OWNER, slug=dataset
            )
            refs.append(f"{OWNER}/{dataset}")
    folder = write_group_kernel_package(
        group, tmp_path / "kernel", owner=OWNER, slug=slug_for(GROUP_ID), dataset_refs=refs, gpu=True
    )
    meta = json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))
    assert (
        meta["dataset_sources"] == refs
        and meta["is_private"] is True
        and meta["id"].endswith("aas-grp-0123456789ab")
    )
    source = (folder / KERNEL_FILE).read_text(encoding="utf-8")
    script = tmp_path / "run_group.py"
    script.write_text(source.replace('ROOT = Path("/")', f"ROOT = Path({str(root)!r})"), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("KAGGLE", "AAS_PROFILE"))}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    done = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=120, env=env
    )
    return done, root / "kaggle" / "working" / "aas_output"


def group_of(a: KaggleJobSpec, b: KaggleJobSpec) -> KaggleGroupSpec:
    return KaggleGroupSpec(GROUP_ID, "sunny", "gpu_t4x2", 600, (a, b))


def test_group_kernel_runs_one_process_per_gpu_with_its_own_inputs_and_manifest(tmp_path: Path):
    a = member(tmp_path, JOB_ID, "alpha")
    b = member(tmp_path, JOB_B, "beta", with_input=False)
    done, output = run_group_kernel(tmp_path, group_of(a, b))
    assert done.returncode == 0, done.stdout + done.stderr
    seen_a = json.loads((output / JOB_ID / "seen.json").read_text(encoding="utf-8"))
    seen_b = json.loads((output / JOB_B / "seen.json").read_text(encoding="utf-8"))
    assert (seen_a["gpu"], seen_a["aas_gpu"], seen_b["gpu"], seen_b["aas_gpu"]) == ("0", "0", "1", "1")
    assert "alpha_in_01_style_reference.png" in seen_a["inputs"] and seen_b["inputs"] == []
    for job_id in (JOB_ID, JOB_B):
        manifest = json.loads((output / job_id / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["job_id"] == job_id and manifest["status"] == "ok"
    assert (
        f"[{JOB_ID}] plain line from alpha" in done.stdout
        and f"[{JOB_B}] plain line from beta" in done.stdout
    )
    progress = [
        json.loads(line.split(" ", 1)[1])
        for line in done.stdout.splitlines()
        if line.startswith("AAS_PROGRESS ")
    ]
    assert {p["job_id"] for p in progress} == {JOB_ID, JOB_B}  # protocol lines keep their own job_id
    assert done.stdout.count("AAS_TELEMETRY ") >= 1  # one reporter for the session


def test_group_kernel_fails_only_when_both_jobs_fail(tmp_path: Path):
    a = member(tmp_path, JOB_ID, "alpha")
    b = member(tmp_path, JOB_B, "beta", fail=True)
    done, output = run_group_kernel(tmp_path, group_of(a, b))
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads((output / JOB_B / "manifest.json").read_text(encoding="utf-8"))["status"] == "error"
    both = tmp_path / "both"
    both.mkdir()
    done, _ = run_group_kernel(
        both, group_of(member(both, JOB_ID, "a", fail=True), member(both, JOB_B, "b", fail=True))
    )
    assert done.returncode != 0 and "both jobs failed" in done.stderr


def test_a_coded_entry_error_reaches_the_manifest_with_its_details(tmp_path: Path):
    coded = tmp_path / "coded_entry.py"
    coded.write_text(
        "class PromptTooLong(Exception):\n"
        "    aas_code = 'MODEL_PROMPT_TOO_LONG'\n"
        "    aas_details = {'tokens': 2300, 'max_tokens': 2048, 'path': object()}\n"
        "def main(arguments, input_dir, output_dir, progress):\n"
        "    raise PromptTooLong('too long')\n",
        encoding="utf-8",
    )
    done, output = run_kernel(tmp_path, spec(tmp_path, coded))
    assert done.returncode != 0
    error = json.loads((output / "manifest.json").read_text(encoding="utf-8"))["error"]
    assert error["code"] == "MODEL_PROMPT_TOO_LONG" and error["details"] == {
        "tokens": 2300,
        "max_tokens": 2048,
    }
