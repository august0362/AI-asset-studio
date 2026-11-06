"""Adapter interface (docs/CONTRACTS.md §2.4).

``capabilities``, ``validate_model_specific`` and ``build_invocation`` are pure. ``collect_outputs`` only reads
``output_dir``.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..contracts import (
    CONTRACT_VERSION,
    FORMAT_MIME_TYPES,
    Artifact,
    CreateJobRequest,
    ErrorItem,
    ExpectedOutput,
    GenerationRequest,
    ModelCapabilities,
    ModelInvocation,
    ResourceRequirements,
)
from .validation import validate_glb, validate_png

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # the directory that contains ``models/``


class ArtifactInvalidError(Exception):
    """Raised by ``collect_outputs``; maps to the job error ``ARTIFACT_INVALID``."""

    code = "ARTIFACT_INVALID"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


def requirements_from(capabilities: ModelCapabilities) -> ResourceRequirements:
    runtime = capabilities.runtime
    return ResourceRequirements(
        accelerator_kinds=list(runtime.supported_accelerators),
        multi_gpu=runtime.multi_gpu,
        minimum_gpu_vram_bytes=runtime.minimum_gpu_vram_bytes,
        estimated_runtime_seconds=runtime.estimated_runtime_seconds,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ModelAdapter(ABC):
    #: Repo-relative POSIX path of the remote entrypoint (stdlib + Pillow only, self-contained).
    entrypoint: str

    def __init__(self, capabilities: ModelCapabilities) -> None:
        self._capabilities = capabilities

    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def validate_model_specific(self, request: CreateJobRequest) -> list[ErrorItem]:
        """Checks the schema cannot express. The mocks have none."""
        return []

    @abstractmethod
    def expected_outputs(self, request: GenerationRequest) -> list[ExpectedOutput]: ...

    @abstractmethod
    def build_arguments(self, request: GenerationRequest) -> dict[str, Any]: ...

    def build_invocation(self, request: GenerationRequest) -> ModelInvocation:
        return ModelInvocation(
            contract_version=CONTRACT_VERSION,
            job_id=request.job_id,
            model_id=request.model_id,
            entrypoint=self.entrypoint,
            arguments=self.build_arguments(request),
            input_files=[item.path for item in request.inputs],
            expected_outputs=self.expected_outputs(request),
            resource_requirements=requirements_from(self._capabilities),
        )

    def collect_outputs(self, request: GenerationRequest, output_dir: Path) -> list[Artifact]:
        artifacts: list[Artifact] = []
        primary_seen = False
        for expected in self.expected_outputs(request):
            path = output_dir / expected.name
            if not path.is_file() or path.is_symlink():
                if expected.required:
                    raise ArtifactInvalidError(
                        f"The required output '{expected.name}' is missing.", {"output": expected.name}
                    )
                continue
            width = height = None
            try:
                if expected.format == "png":
                    width, height = validate_png(path)
                else:
                    validate_glb(path)
            except ValueError as exc:
                if expected.required:
                    raise ArtifactInvalidError(
                        f"The output '{expected.name}' is not a valid {expected.format.upper()} file.",
                        {"output": expected.name, "reason": str(exc)},
                    ) from exc
                continue  # an invalid optional output is skipped, never reported as an artifact
            is_primary = expected.required and expected.format == request.output_format and not primary_seen
            primary_seen = primary_seen or is_primary
            artifacts.append(
                Artifact(
                    artifact_id=f"art_{len(artifacts) + 1:02d}",
                    kind=expected.kind,
                    format=expected.format,
                    mime_type=FORMAT_MIME_TYPES[expected.format],
                    size_bytes=path.stat().st_size,
                    sha256=_sha256(path),
                    width=width,
                    height=height,
                    is_primary=is_primary,
                    path=expected.name,
                )
            )
        if not primary_seen:
            raise ArtifactInvalidError(
                f"No primary {request.output_format.upper()} output was produced.",
                {"output_format": request.output_format},
            )
        return artifacts
