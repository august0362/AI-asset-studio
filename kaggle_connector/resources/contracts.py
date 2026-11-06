"""Kaggle resource contracts (docs/CONTRACTS.md §6, §7).

``ErrorItem`` and ``ResourceRequirements`` are deliberately re-declared here with the exact contract shape:
this module may not import ``models`` (and vice versa). The backend converts between the two.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer

CONTRACT_VERSION = "1.0"


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDatetime = Annotated[
    AwareDatetime,
    AfterValidator(lambda v: v.astimezone(UTC)),
    PlainSerializer(_fmt, return_type=str, when_used="json"),
]


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


AcceleratorKind = Literal["cpu", "gpu_cuda", "tpu"]
Freshness = Literal["fresh", "stale", "unavailable", "unsupported", "not_applicable"]
Source = Literal[
    "kaggle_cli_quota", "kaggle_cli_status", "notebook_telemetry", "local_observation", "mock", "none"
]
Fit = Literal["ok", "unknown", "insufficient"]


class ErrorItem(_Contract):
    code: str
    severity: Literal["error", "warning"]
    field: str | None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


def issue(
    code: str,
    severity: Literal["error", "warning"],
    field: str | None,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> ErrorItem:
    return ErrorItem(
        code=code, severity=severity, field=field, message=message, details=details or {}, retryable=retryable
    )


class ResourceRequirements(_Contract):
    accelerator_kinds: list[AcceleratorKind] = Field(min_length=1)
    multi_gpu: Literal["unsupported", "optional", "required"]
    minimum_gpu_vram_bytes: int | None
    estimated_runtime_seconds: int | None


# --- §6.1 ComputeProfile ---------------------------------------------------------------------------------


class AcceleratorSpec(_Contract):
    accelerator_id: str = Field(pattern=r"^[a-z0-9_]{2,32}$")
    kind: AcceleratorKind
    device_count: int = Field(ge=0)
    vram_bytes_per_device: int | None
    max_session_seconds: int = Field(ge=1)


class ComputeProfile(_Contract):
    contract_version: Literal["1.0"]
    profile_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,31}$")
    display_name: str
    owner_label: str
    mode: Literal["mock", "kaggle"]
    enabled: bool
    authorization_confirmed: bool
    accelerators: list[AcceleratorSpec]


# --- §6.2 KaggleResourceSnapshot -------------------------------------------------------------------------


class AcceleratorAvailability(_Contract):
    accelerator_id: str
    status: Literal["available", "quota_exhausted", "unknown", "not_in_profile"]


class GpuDevice(_Contract):
    index: int = Field(ge=0)
    name: str | None
    utilization_percent: float | None
    vram_used_bytes: int | None
    vram_total_bytes: int | None
    temperature_c: float | None
    status: Literal["available", "unavailable", "unsupported"]


class ObservedAt(_Contract):
    snapshot: UtcDatetime
    quota: UtcDatetime | None
    session: UtcDatetime | None
    host: UtcDatetime | None
    gpu: UtcDatetime | None


class GroupSources(_Contract):
    quota: Source
    session: Source
    host: Source
    gpu: Source


class GroupFreshness(_Contract):
    quota: Freshness
    session: Freshness
    host: Freshness
    gpu: Freshness


class KaggleResourceSnapshot(_Contract):
    contract_version: Literal["1.0"]
    compute_profile_id: str
    authentication_status: Literal["authenticated", "unauthenticated", "invalid_credentials", "unknown"]
    accelerator_type: str | None
    accelerator_availability: list[AcceleratorAvailability]
    gpu_quota_total_hours: float | None
    gpu_quota_used_hours: float | None
    gpu_quota_remaining_hours: float | None
    tpu_quota_total_hours: float | None
    tpu_quota_used_hours: float | None
    tpu_quota_remaining_hours: float | None
    quota_reset_at: UtcDatetime | None
    session_started_at: UtcDatetime | None
    estimated_session_remaining_seconds: int | None
    session_status: Literal["none", "queued", "running", "finished", "failed", "unknown"]
    cpu_utilization_percent: float | None
    ram_used_bytes: int | None
    ram_total_bytes: int | None
    gpu_devices: list[GpuDevice]
    observed_at: ObservedAt
    source: GroupSources
    freshness_status: GroupFreshness
    error: list[ErrorItem]


# --- §7.3 ResourcePlan -----------------------------------------------------------------------------------


class EstimateBasis(_Contract):
    estimated_runtime_seconds: int | None
    safety_factor: float
    overhead_seconds: int


class CandidateFit(_Contract):
    accelerator_id: str
    fit: Fit
    reasons: list[ErrorItem]


class ResourcePlan(_Contract):
    contract_version: Literal["1.0"]
    profile_id: str
    accelerator_id: str | None
    selection: Literal["user_selected", "recommended"]
    fit: Fit
    required_seconds: int | None
    estimate_basis: EstimateBasis
    session_limit_seconds: int | None
    quota_remaining_seconds: int | None
    candidates: list[CandidateFit]
    warnings: list[ErrorItem]
    errors: list[ErrorItem]


# --- §6.4 Notebook output protocol -----------------------------------------------------------------------


class ProgressEvent(_Contract):
    v: Literal[1]
    job_id: str
    at: UtcDatetime
    stage: str
    percent: float | None = Field(default=None, ge=0, le=100)
    message: str | None = None


class TelemetryGpu(_Contract):
    index: int = Field(ge=0)
    name: str | None = None
    utilization_percent: float | None = None
    vram_used_bytes: int | None = None
    vram_total_bytes: int | None = None
    temperature_c: float | None = None


class TelemetrySample(_Contract):
    v: Literal[1]
    job_id: str
    at: UtcDatetime
    cpu_percent: float | None = None
    ram_used_bytes: int | None = None
    ram_total_bytes: int | None = None
    gpu_source: Literal["nvml", "nvidia_smi", "none"] = "none"
    gpus: list[TelemetryGpu] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class OutputEntry(_Contract):
    name: str
    kind: str
    format: str
    size_bytes: int = Field(ge=0)
    sha256: str


class ManifestError(_Contract):
    code: str
    message: str


class OutputManifest(_Contract):
    v: Literal[1]
    job_id: str
    status: Literal["ok", "error"]
    error: ManifestError | None
    outputs: list[OutputEntry]
