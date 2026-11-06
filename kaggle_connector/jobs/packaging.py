"""Job package layout shared by the mock and (M3) the real notebook: ``runner.py`` + ``entry.py`` + ``job.json``.

The package never contains credentials (CONTRACTS §10).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..client.base import KaggleJobSpec

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
