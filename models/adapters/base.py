"""Adapter interface (docs/CONTRACTS.md §2.4) and batch jobs (§13.9).

``capabilities``, ``validate_model_specific`` and ``build_invocation`` are pure. ``collect_outputs`` and
``task_report`` only read ``output_dir``.

Batch protocol (an adapter with ``supports_batch``): the arguments carry ``tasks`` (in render order) and
``deadline_seconds``. The remote entry loads the model once, writes ``task_<task_id>.png`` after each task and keeps
``task_results.json`` up to date: ``{"v": 1, "tasks": [{"task_id", "status": "succeeded" | "failed" | "not_run",
"seed", "seconds", "error": {"message", "reason"} | null}]}``.
"""

from __future__ import annotations

import hashlib
import json
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
TASK_RESULTS_FILE = "task_results.json"
TASK_STATUSES = ("succeeded", "failed", "not_run")
DEADLINE_MARGIN_SECONDS = 120  # time left after the last task for writing outputs and the runner's manifest


def task_output_name(task_id: str) -> str:
    return f"task_{task_id}.png"


def deadline_seconds(request: GenerationRequest) -> int | None:
    """The remote entry starts no task after this many seconds: the run timeout minus a margin."""
    budget = request.time_budget_seconds
    if budget is None:
        return None
    return max(budget - max(DEADLINE_MARGIN_SECONDS, budget // 10), budget // 2, 1)


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
    #: Repo-relative POSIX path of the remote entrypoint (self-contained; see ARCHITECTURE §1.1 for its imports).
    entrypoint: str
    #: The remote run downloads weights or packages, so its kernel needs the internet (D-032). Mocks do not.
    requires_internet: bool = False
    #: The adapter and its remote entry accept ``GenerationRequest.tasks`` (§13.9).
    supports_batch: bool = False

    def __init__(self, capabilities: ModelCapabilities) -> None:
        self._capabilities = capabilities

    def capabilities(self) -> ModelCapabilities:
        return self._capabilities

    def model_revision(self) -> str | None:
        """The pinned weights revision recorded in provenance; ``None`` when there is none (mocks)."""
        return None

    def validate_model_specific(self, request: CreateJobRequest) -> list[ErrorItem]:
        """Checks the schema cannot express. The mocks have none."""
        return []

    @abstractmethod
    def expected_outputs(self, request: GenerationRequest) -> list[ExpectedOutput]: ...

    @abstractmethod
    def build_arguments(self, request: GenerationRequest) -> dict[str, Any]: ...

    def build_batch_arguments(self, request: GenerationRequest) -> dict[str, Any]:
        raise NotImplementedError(f"{type(self).__name__} does not support batch jobs")

    def _outputs(self, request: GenerationRequest) -> list[ExpectedOutput]:
        if request.tasks is None:
            return self.expected_outputs(request)
        return [
            ExpectedOutput(name=task_output_name(t.task_id), kind="image", format="png", required=False)
            for t in request.tasks
        ]

    def build_invocation(self, request: GenerationRequest) -> ModelInvocation:
        if request.tasks is not None:
            if not self.supports_batch or not request.tasks:
                raise ValueError(f"{type(self).__name__} cannot run this batch request")
            arguments = self.build_batch_arguments(request)
        else:
            arguments = self.build_arguments(request)
        return ModelInvocation(
            contract_version=CONTRACT_VERSION,
            job_id=request.job_id,
            model_id=request.model_id,
            entrypoint=self.entrypoint,
            arguments=arguments,
            input_files=[item.path for item in request.inputs],
            expected_outputs=self._outputs(request),
            resource_requirements=requirements_from(self._capabilities),
        )

    def task_report(self, request: GenerationRequest, output_dir: Path) -> dict[str, dict[str, Any]]:
        """Per-task results of a batch run: ``{task_id: {"status", "message", "reason"}}`` for known tasks only.

        A missing or malformed ``task_results.json`` gives ``{}``; the backend then reports those tasks as failed.
        """
        known = {t.task_id for t in request.tasks or []}
        path = output_dir / TASK_RESULTS_FILE
        try:
            document = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, UnicodeDecodeError, ValueError):
            return {}
        entries = document.get("tasks", []) if isinstance(document, dict) else []
        report: dict[str, dict[str, Any]] = {}
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or entry.get("task_id") not in known:
                continue
            if entry.get("status") not in TASK_STATUSES:
                continue
            problem = entry.get("error") if isinstance(entry.get("error"), dict) else {}
            report[entry["task_id"]] = {
                "status": entry["status"],
                "message": str(problem["message"])[:500] if problem.get("message") else None,
                "reason": str(problem["reason"])[:40] if problem.get("reason") else None,
            }
        return report

    def _collect_batch(self, request: GenerationRequest, output_dir: Path) -> list[Artifact]:
        """One ``image`` artifact per succeeded task, in task order; the first one is primary (§13.9)."""
        report = self.task_report(request, output_dir)
        artifacts: list[Artifact] = []
        for task in request.tasks or []:
            if report.get(task.task_id, {}).get("status") != "succeeded":
                continue
            path = output_dir / task_output_name(task.task_id)
            if not path.is_file() or path.is_symlink():
                continue
            try:
                width, height = validate_png(path)
            except ValueError:
                continue  # the backend reports this task as failed, never as an artifact
            artifacts.append(
                Artifact(
                    artifact_id=f"art_{len(artifacts) + 1:02d}",
                    kind="image",
                    format="png",
                    mime_type=FORMAT_MIME_TYPES["png"],
                    size_bytes=path.stat().st_size,
                    sha256=_sha256(path),
                    width=width,
                    height=height,
                    is_primary=not artifacts,
                    path=path.name,
                    task_id=task.task_id,
                )
            )
        if not artifacts:
            raise ArtifactInvalidError(
                "No task of this batch produced a valid PNG.", {"tasks": len(request.tasks or [])}
            )
        return artifacts

    def collect_outputs(self, request: GenerationRequest, output_dir: Path) -> list[Artifact]:
        if request.tasks is not None:
            return self._collect_batch(request, output_dir)
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
