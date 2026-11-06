"""Export JSON Schema for every canonical contract model.

Usage: ``python -m aas_backend.export_schemas [OUT_DIR]`` (default ``data/schemas``, gitignored).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from kaggle_connector.resources.contracts import (
    ComputeProfile,
    KaggleResourceSnapshot,
    OutputManifest,
    ResourcePlan,
    ResourceRequirements,
    TelemetrySample,
)
from models.contracts import (
    Artifact,
    Catalog,
    CreateJobRequest,
    ErrorItem,
    GenerationRequest,
    ModelCapabilities,
    ModelInvocation,
    UploadRecord,
)

from .schemas import (
    ErrorResponse,
    GenerationResult,
    Health,
    JobList,
    JobStatusView,
    JobSummary,
    LogPage,
    ValidationReport,
)

SCHEMAS: dict[str, type[BaseModel]] = {
    "ModelCapabilities": ModelCapabilities,
    "GenerationRequest": GenerationRequest,
    "ModelInvocation": ModelInvocation,
    "Artifact": Artifact,
    "UploadRecord": UploadRecord,
    "CreateJobRequest": CreateJobRequest,
    "ValidationReport": ValidationReport,
    "GenerationResult": GenerationResult,
    "JobSummary": JobSummary,
    "JobList": JobList,
    "JobStatus": JobStatusView,
    "LogPage": LogPage,
    "Catalog": Catalog,
    "Health": Health,
    "ErrorItem": ErrorItem,
    "ErrorResponse": ErrorResponse,
    "ResourceRequirements": ResourceRequirements,
    "ResourcePlan": ResourcePlan,
    "ComputeProfile": ComputeProfile,
    "KaggleResourceSnapshot": KaggleResourceSnapshot,
    "TelemetrySample": TelemetrySample,
    "OutputManifest": OutputManifest,
}


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in SCHEMAS.items():
        schema = model.model_json_schema(mode="serialization")
        schema["$id"] = f"aas/contracts/1.0/{name}.json"
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("data/schemas")
    paths = export(out_dir)
    print(f"wrote {len(paths)} schemas to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
