"""Request-side contracts: UploadRecord (§3.1), CreateJobRequest (§3.2), GenerationRequest (§2.3)."""

from __future__ import annotations

from typing import Any

from pydantic import UUID4, Field, StrictStr

from .common import (
    INPUT_ID_PATTERN,
    JOB_ID_PATTERN,
    UPLOAD_ID_PATTERN,
    AssetCategory,
    ContractModel,
    ContractVersion,
    ImageRole,
    OutputFormat,
    PipelineType,
    UtcDatetime,
)


class UploadRecord(ContractModel):
    contract_version: ContractVersion
    upload_id: str = Field(pattern=UPLOAD_ID_PATTERN)
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    sha256: str
    created_at: UtcDatetime
    expires_at: UtcDatetime


class InputRef(ContractModel):
    # Plain strings on purpose: unknown roles and malformed upload IDs are reported by stage 4
    # (MODEL_IMAGE_ROLE_UNSUPPORTED / UPLOAD_NOT_FOUND), not as schema errors.
    upload_id: StrictStr
    role: StrictStr


class ComputeSelection(ContractModel):
    profile_id: StrictStr
    accelerator_id: StrictStr | None = None


class CreateJobRequest(ContractModel):
    """Body of ``POST /validate`` and ``POST /jobs``.

    Enum-valued fields are plain strings so that stage 2-5 report their specific codes
    (PIPELINE_UNKNOWN, ASSET_CATEGORY_UNKNOWN, MODEL_NOT_FOUND, MODEL_OUTPUT_FORMAT_UNSUPPORTED).
    """

    contract_version: StrictStr
    client_request_id: UUID4
    pipeline_type: StrictStr
    asset_category: StrictStr
    model_id: StrictStr
    prompt: StrictStr | None = None
    inputs: list[InputRef] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    output_format: StrictStr
    compute: ComputeSelection


class RetryRequest(ContractModel):
    client_request_id: UUID4


class GenerationInput(ContractModel):
    input_id: str = Field(pattern=INPUT_ID_PATTERN)
    role: ImageRole
    path: str
    mime_type: str
    width: int
    height: int
    size_bytes: int
    sha256: str


class GenerationRequest(ContractModel):
    """Normalized, model- and compute-independent request. The adapter's only input."""

    contract_version: ContractVersion
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    pipeline_type: PipelineType
    asset_category: AssetCategory
    model_id: str
    prompt: str | None
    inputs: list[GenerationInput]
    options: dict[str, Any]
    output_format: OutputFormat
    created_at: UtcDatetime
