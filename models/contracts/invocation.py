"""ModelInvocation (docs/CONTRACTS.md §2.4) and artifacts (§3.5)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .common import (
    ARTIFACT_ID_PATTERN,
    AcceleratorKind,
    ArtifactKind,
    ContractModel,
    ContractVersion,
    MultiGpu,
    OutputFormat,
)


class ExpectedOutput(ContractModel):
    name: str = Field(pattern=r"^[a-z0-9_-]+\.(png|glb)$")
    kind: ArtifactKind
    format: OutputFormat
    required: bool


class ResourceRequirements(ContractModel):
    accelerator_kinds: list[AcceleratorKind] = Field(min_length=1)
    multi_gpu: MultiGpu
    minimum_gpu_vram_bytes: int | None
    estimated_runtime_seconds: int | None


class ModelInvocation(ContractModel):
    contract_version: ContractVersion
    job_id: str
    model_id: str
    entrypoint: str
    arguments: dict[str, Any]
    input_files: list[str]
    expected_outputs: list[ExpectedOutput]
    resource_requirements: ResourceRequirements


class Artifact(ContractModel):
    """Artifact metadata. ``path`` is internal (relative POSIX path); the API replaces it with ``content_url``."""

    artifact_id: str = Field(pattern=ARTIFACT_ID_PATTERN)
    kind: ArtifactKind
    format: OutputFormat
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    width: int | None
    height: int | None
    is_primary: bool
    path: str
    task_id: str | None = None  # v1.1: set for each image of a batch job (§13.9)
