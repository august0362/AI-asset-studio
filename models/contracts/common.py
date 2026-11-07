"""Shared primitives for contract v1.0 (docs/CONTRACTS.md §1)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer

CONTRACT_VERSION = "1.0"
ContractVersion = Literal["1.0"]


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def format_timestamp(value: datetime) -> str:
    """RFC 3339 UTC with ``Z`` and second precision."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


UtcDatetime = Annotated[
    AwareDatetime,
    AfterValidator(_to_utc),
    PlainSerializer(format_timestamp, return_type=str, when_used="json"),
]


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields are rejected, nothing is dropped."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)


# --- Enumerations (§1.1) ---------------------------------------------------------------------------------

PIPELINE_TYPES = ("text_to_2d", "image_to_3d", "text_to_3d")
ASSET_CATEGORIES = ("character", "skill_effect", "weapon", "companion")
IMAGE_ROLES = ("front", "side", "back", "three_quarter", "detail", "style_reference")
VIEW_ROLES = frozenset({"front", "side", "back", "three_quarter"})
OUTPUT_FORMATS = ("png", "glb")
ACCELERATOR_KINDS = ("cpu", "gpu_cuda", "tpu")
JOB_STATUSES = ("created", "uploading", "queued", "running", "downloading", "completed", "failed")
TERMINAL_STATUSES = frozenset({"completed", "failed"})

PipelineType = Literal["text_to_2d", "image_to_3d", "text_to_3d"]
AssetCategory = Literal["character", "skill_effect", "weapon", "companion"]
ImageRole = Literal["front", "side", "back", "three_quarter", "detail", "style_reference"]
OutputFormat = Literal["png", "glb"]
AcceleratorKind = Literal["cpu", "gpu_cuda", "tpu"]
JobStatus = Literal["created", "uploading", "queued", "running", "downloading", "completed", "failed"]
Availability = Literal["available", "experimental", "planned", "unavailable"]
ArtifactKind = Literal["image", "model_3d", "texture", "preview"]
Severity = Literal["error", "warning"]
MultiGpu = Literal["unsupported", "optional", "required"]

# --- Identifiers (§1.2) ----------------------------------------------------------------------------------

JOB_ID_PATTERN = r"^job_\d{8}T\d{6}Z_[0-9a-f]{6}$"
UPLOAD_ID_PATTERN = r"^upl_[0-9a-f]{32}$"
INPUT_ID_PATTERN = r"^in_\d{2}$"
ARTIFACT_ID_PATTERN = r"^art_\d{2}$"
MODEL_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,63}$"
PROFILE_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{1,31}$"

# --- Global limits (§1.3) --------------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 52_428_800
MAX_IMAGES_PER_REQUEST = 8
PROMPT_MAX_LENGTH = 10_000  # v1.2 (D-041); it was 4 000
SUPPORTED_UPLOAD_MIME_TYPES = ("image/png", "image/jpeg", "image/webp")

FORMAT_MIME_TYPES = {"png": "image/png", "glb": "model/gltf-binary"}


# --- Errors (§5.2) ---------------------------------------------------------------------------------------


class ErrorItem(ContractModel):
    code: str
    severity: Severity
    field: str | None
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


def error(
    code: str, field: str | None, message: str, details: dict[str, Any] | None = None, retryable: bool = False
) -> ErrorItem:
    return ErrorItem(
        code=code, severity="error", field=field, message=message, details=details or {}, retryable=retryable
    )


def warning(code: str, field: str | None, message: str, details: dict[str, Any] | None = None) -> ErrorItem:
    return ErrorItem(code=code, severity="warning", field=field, message=message, details=details or {})
