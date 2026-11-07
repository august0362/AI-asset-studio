"""Job package layout shared by the mock and (M3) the real notebook: ``runner.py`` + ``entry.py`` + ``job.json``.

The package never contains credentials (CONTRACTS §10).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..client.base import KaggleGroupSpec, KaggleJobSpec

RUNNER_SOURCE = Path(__file__).resolve().parents[1] / "runtime" / "runner.py"
OUTPUT_DIR_NAME = "aas_output"


def build_job_document(
    spec: KaggleJobSpec, *, input_dir: str, output_dir: str, telemetry: dict[str, Any]
) -> dict[str, Any]:
    return {
        "v": 1,
        "job_id": spec.job_id,
        "entrypoint": "entry.py",
        "arguments": spec.arguments,
        "input_dir": input_dir,
        "output_dir": output_dir,
        "expected_outputs": [
            {"name": o.name, "kind": o.kind, "format": o.format, "required": o.required}
            for o in spec.expected_outputs
        ],
        "telemetry": telemetry,
    }


def build_group_document(
    spec: KaggleGroupSpec, *, input_dirs: list[str], output_dir: str, telemetry: dict[str, Any]
) -> dict[str, Any]:
    """``job.json`` of a run group (CONTRACTS §14.4): both jobs, each with its own entry file, input folder and GPU."""
    jobs = []
    for index, (member, input_dir) in enumerate(zip(spec.members, input_dirs, strict=True)):
        document = build_job_document(
            member, input_dir=input_dir, output_dir=output_dir, telemetry={"mode": "off"}
        )
        document.pop("telemetry")
        jobs.append({**document, "entrypoint": f"entry_{index}.py", "gpu_index": index})
    return {"v": 1, "group_id": spec.group_id, "jobs": jobs, "output_dir": output_dir, "telemetry": telemetry}


def write_group_package(
    spec: KaggleGroupSpec,
    package_dir: Path,
    *,
    input_dirs: list[str],
    output_dir: str,
    telemetry: dict[str, Any],
) -> Path:
    package_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNNER_SOURCE, package_dir / "runner.py")
    for index, member in enumerate(spec.members):
        shutil.copyfile(member.entrypoint_file, package_dir / f"entry_{index}.py")
    document = build_group_document(spec, input_dirs=input_dirs, output_dir=output_dir, telemetry=telemetry)
    job_path = package_dir / "job.json"
    job_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return job_path


def write_package(
    spec: KaggleJobSpec, package_dir: Path, *, input_dir: str, output_dir: str, telemetry: dict[str, Any]
) -> Path:
    package_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNNER_SOURCE, package_dir / "runner.py")
    shutil.copyfile(spec.entrypoint_file, package_dir / "entry.py")
    document = build_job_document(spec, input_dir=input_dir, output_dir=output_dir, telemetry=telemetry)
    job_path = package_dir / "job.json"
    job_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return job_path
