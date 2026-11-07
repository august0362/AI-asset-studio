"""Browser-facing response contracts composed from Models and Kaggle contracts (docs/CONTRACTS.md §3, §5).

They never contain filesystem paths or credentials.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, StrictBool, StrictStr, model_serializer

from kaggle_connector.resources.contracts import ComputeProfile, ResourcePlan
from models.contracts import (
    ArtifactKind,
    AssetCategory,
    ContractModel,
    ErrorItem,
    ImageRole,
    JobStatus,
    ModelCapabilities,
    OutputFormat,
    PipelineType,
    UtcDatetime,
)
from models.contracts.common import ContractVersion


class Health(ContractModel):
    status: Literal["ok"]
    contract_version: ContractVersion
    compute_mode: Literal["mock", "kaggle"]


class ModelList(ContractModel):
    contract_version: ContractVersion
    models: list[ModelCapabilities]


class ProfileList(ContractModel):
    contract_version: ContractVersion
    profiles: list[ComputeProfile]


class ValidationReport(ContractModel):
    contract_version: ContractVersion
    valid: bool
    errors: list[ErrorItem]
    warnings: list[ErrorItem]
    resource_plan: ResourcePlan | None


class ErrorResponse(ContractModel):
    contract_version: Literal["1.0", "1.1"]  # 1.1 on Character Production routes (§13.1)
    warnings: list[ErrorItem]
    errors: list[ErrorItem]


class ArtifactView(ContractModel):
    artifact_id: str
    kind: ArtifactKind
    format: OutputFormat
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    is_primary: bool
    content_url: str
    task_id: str | None = None  # v1.1: the batch task this image belongs to (§13.9)


class ArtifactList(ContractModel):
    contract_version: ContractVersion
    artifacts: list[ArtifactView]


class InputView(ContractModel):
    input_id: str
    role: ImageRole
    mime_type: str
    width: int
    height: int
    size_bytes: int
    content_url: str


class BatchRef(ContractModel):
    """v1.1 (§13.9): the character batch a job belongs to. ``null`` for every other job."""

    character_id: str
    manifest_id: str
    group_id: str
    attempt: int
    task_ids: list[str]


class RequestView(ContractModel):
    pipeline_type: PipelineType
    asset_category: AssetCategory
    model_id: str
    prompt: str | None
    output_format: OutputFormat
    options: dict[str, Any]
    inputs: list[InputView]
    batch: BatchRef | None = None


class ComputeView(ContractModel):
    profile_id: str
    accelerator_id: str | None
    # The full §7.3 ResourcePlan from job creation. The §3.4 example abbreviates it to fit/selection/required_seconds.
    resource_plan: ResourcePlan


class StatusEntry(ContractModel):
    status: JobStatus
    at: UtcDatetime


class PreviewRef(ContractModel):
    artifact_id: str


class Execution(ContractModel):
    backend: Literal["mock", "kaggle"]
    remote_ref: str | None = None
    submitted_at: UtcDatetime | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    duration_seconds: int | None = None
    transient_retries: int = 0
    retry_of: str | None = None


GROUP_ID_PATTERN = r"^grp_[0-9a-f]{12}$"


class Scheduling(ContractModel):
    """v1.2 (§14.1): run control of a job. ``queue_state`` is set only while the job is ``created``."""

    auto_run: bool
    queue_state: Literal["held", "waiting", "starting"] | None
    queue_position: int | None = Field(ge=1)
    run_requested_at: UtcDatetime | None
    group_id: str | None = Field(pattern=GROUP_ID_PATTERN)
    group_job_ids: list[str]
    gpu_index: Literal[0, 1] | None


class RunGroup(ContractModel):
    """v1.2 (§14.4): ``201`` response of ``POST /jobs/groups``."""

    contract_version: ContractVersion
    group_id: str = Field(pattern=GROUP_ID_PATTERN)
    job_ids: list[str]
    run_requested_at: UtcDatetime


class RefusedDelete(ContractModel):
    job_id: str
    code: Literal["JOB_NOT_FOUND", "JOB_NOT_TERMINAL"]


class BulkDeleteResult(ContractModel):
    """v1.2 (§14.5): ``200`` response of ``POST /jobs/delete``."""

    contract_version: ContractVersion
    deleted: list[str]
    refused: list[RefusedDelete]


class AutoRunBody(ContractModel):
    """Body of ``PATCH /jobs/{job_id}`` (§14.5)."""

    auto_run: StrictBool


class JobIdsBody(ContractModel):
    """Body of ``POST /jobs/groups`` and ``POST /jobs/delete`` (§14.5)."""

    job_ids: list[StrictStr]


class GenerationResult(ContractModel):
    contract_version: ContractVersion
    job_id: str
    status: JobStatus
    status_history: list[StatusEntry]
    request: RequestView
    compute: ComputeView
    artifacts: list[ArtifactView]
    preview: PreviewRef | None
    warnings: list[ErrorItem]
    error: ErrorItem | None
    execution: Execution
    created_at: UtcDatetime
    updated_at: UtcDatetime
    scheduling: Scheduling | None = None  # v1.2 (§14.1): always set by this backend; absent in v1.0 payloads

    @model_serializer(mode="wrap")
    def _omit_absent_scheduling(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if data.get("scheduling") is None:
            data.pop("scheduling", None)  # a v1.0 payload stays exactly v1.0
        return data


class JobSummary(ContractModel):
    job_id: str
    status: JobStatus
    pipeline_type: PipelineType
    asset_category: AssetCategory
    model_id: str
    created_at: UtcDatetime
    updated_at: UtcDatetime
    primary_artifact: ArtifactView | None
    error_code: str | None
    scheduling: Scheduling | None = None  # v1.2 (§14.1): always set by this backend; absent in v1.0 payloads

    @model_serializer(mode="wrap")
    def _omit_absent_scheduling(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data = handler(self)
        if data.get("scheduling") is None:
            data.pop("scheduling", None)  # a v1.0 payload stays exactly v1.0
        return data


class JobList(ContractModel):
    contract_version: ContractVersion
    jobs: list[JobSummary]
    next_cursor: str | None


class Progress(ContractModel):
    stage: str
    percent: float | None
    message: str | None


class JobStatusView(ContractModel):
    contract_version: ContractVersion
    job_id: str
    status: JobStatus
    updated_at: UtcDatetime
    progress: Progress | None


class LogLine(ContractModel):
    n: int
    at: UtcDatetime
    source: Literal["backend", "remote"]
    text: str


class LogPage(ContractModel):
    contract_version: ContractVersion
    lines: list[LogLine]
    next_offset: int
    complete: bool
