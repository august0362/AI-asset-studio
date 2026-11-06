"""Internal job record: ``data/jobs/<job_id>.json`` = GenerationResult + paths + internal state (§3.4)."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from models.contracts import (
    Artifact,
    AssetCategory,
    ContractModel,
    ErrorItem,
    GenerationTask,
    ImageRole,
    JobStatus,
    OutputFormat,
    PipelineType,
    UtcDatetime,
)
from models.contracts.common import ContractVersion

from ..schemas import (
    ArtifactView,
    BatchRef,
    ComputeView,
    Execution,
    GenerationResult,
    InputView,
    JobSummary,
    PreviewRef,
    Progress,
    RequestView,
    StatusEntry,
)

API = "/api/v1"


class InputRecord(ContractModel):
    input_id: str
    role: ImageRole
    mime_type: str
    width: int
    height: int
    size_bytes: int
    sha256: str
    path: str
    upload_id: str
    filename: str


class RequestRecord(ContractModel):
    pipeline_type: PipelineType
    asset_category: AssetCategory
    model_id: str
    prompt: str | None
    output_format: OutputFormat
    options: dict[str, Any]
    inputs: list[InputRecord]
    tasks: list[GenerationTask] | None = None  # batch jobs only (§13.9); internal, not in the API view
    batch: BatchRef | None = None


class InternalState(ContractModel):
    client_request_id: str
    original_request: dict[str, Any]
    timeout_seconds: int
    deadline_seconds: float
    created_ns: int = 0  # precise creation order (timestamps are second-precision)
    progress: Progress | None = None
    remote_log_offset: int = 0
    telemetry_samples: int = 0
    telemetry_malformed: int = 0


class JobRecord(ContractModel):
    contract_version: ContractVersion
    job_id: str
    status: JobStatus
    status_history: list[StatusEntry]
    request: RequestRecord
    compute: ComputeView
    artifacts: list[Artifact] = Field(default_factory=list)
    preview: PreviewRef | None = None
    warnings: list[ErrorItem] = Field(default_factory=list)
    error: ErrorItem | None = None
    execution: Execution
    created_at: UtcDatetime
    updated_at: UtcDatetime
    internal: InternalState


def artifact_view(job_id: str, artifact: Artifact) -> ArtifactView:
    data = artifact.model_dump(exclude={"path"})
    return ArtifactView(**data, content_url=f"{API}/jobs/{job_id}/artifacts/{artifact.artifact_id}/content")


def to_result(record: JobRecord) -> GenerationResult:
    """Public view: strips paths and internal state."""
    req = record.request
    return GenerationResult(
        contract_version=record.contract_version,
        job_id=record.job_id,
        status=record.status,
        status_history=record.status_history,
        request=RequestView(
            pipeline_type=req.pipeline_type,
            asset_category=req.asset_category,
            model_id=req.model_id,
            prompt=req.prompt,
            output_format=req.output_format,
            options=req.options,
            inputs=[
                InputView(
                    input_id=i.input_id,
                    role=i.role,
                    mime_type=i.mime_type,
                    width=i.width,
                    height=i.height,
                    size_bytes=i.size_bytes,
                    content_url=f"{API}/jobs/{record.job_id}/inputs/{i.input_id}/content",
                )
                for i in req.inputs
            ],
            batch=req.batch,
        ),
        compute=record.compute,
        artifacts=[artifact_view(record.job_id, a) for a in record.artifacts],
        preview=record.preview,
        warnings=record.warnings,
        error=record.error,
        execution=record.execution,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def to_summary(record: JobRecord) -> JobSummary:
    primary = next((a for a in record.artifacts if a.is_primary), None)
    return JobSummary(
        job_id=record.job_id,
        status=record.status,
        pipeline_type=record.request.pipeline_type,
        asset_category=record.request.asset_category,
        model_id=record.request.model_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        primary_artifact=artifact_view(record.job_id, primary) if primary else None,
        error_code=record.error.code if record.error else None,
    )
