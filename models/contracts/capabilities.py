"""ModelCapabilities (docs/CONTRACTS.md §2.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from .common import (
    MAX_IMAGES_PER_REQUEST,
    MODEL_ID_PATTERN,
    AcceleratorKind,
    AssetCategory,
    Availability,
    ContractModel,
    ContractVersion,
    ImageRole,
    MultiGpu,
    OutputFormat,
    PipelineType,
)

_OPTIONAL_OPTION_KEYS = ("enum", "minimum", "maximum", "max_length", "description")


class OptionSpec(ContractModel):
    """One entry of ``options_schema``. Absent constraint keys are omitted from JSON; ``default`` is always present."""

    type: Literal["integer", "number", "string", "boolean"]
    enum: list[Any] | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    max_length: int | None = Field(default=None, ge=0)
    default: Any
    description: str | None = None

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> dict[str, Any]:
        data = handler(self)
        for key in _OPTIONAL_OPTION_KEYS:
            if data.get(key) is None:
                data.pop(key, None)
        return data


class ModelInputs(ContractModel):
    prompt_supported: bool
    prompt_required: bool
    prompt_max_length: int | None = Field(ge=1)
    min_images: int = Field(ge=0, le=MAX_IMAGES_PER_REQUEST)
    max_images: int = Field(ge=0, le=MAX_IMAGES_PER_REQUEST)
    supported_image_roles: list[ImageRole]
    required_image_roles: list[ImageRole]
    supported_mime_types: list[str] | None
    maximum_file_size_bytes: int | None = Field(ge=1)
    min_image_width: int | None = Field(ge=1)
    min_image_height: int | None = Field(ge=1)
    max_image_width: int | None = Field(ge=1)
    max_image_height: int | None = Field(ge=1)

    @model_validator(mode="after")
    def _rules(self) -> ModelInputs:
        if not self.prompt_supported and (self.prompt_required or self.prompt_max_length is not None):
            raise ValueError(
                "prompt_supported=false requires prompt_required=false and prompt_max_length=null"
            )
        if self.min_images > self.max_images:
            raise ValueError("min_images must be <= max_images")
        if self.max_images == 0:
            image_fields = (
                self.supported_mime_types,
                self.maximum_file_size_bytes,
                self.min_image_width,
                self.min_image_height,
                self.max_image_width,
                self.max_image_height,
            )
            if (
                self.supported_image_roles
                or self.required_image_roles
                or any(v is not None for v in image_fields)
            ):
                raise ValueError("max_images=0 requires empty roles and null image fields")
        if not set(self.required_image_roles) <= set(self.supported_image_roles):
            raise ValueError("required_image_roles must be a subset of supported_image_roles")
        return self


class ModelRuntime(ContractModel):
    supported_accelerators: list[AcceleratorKind] = Field(min_length=1)
    multi_gpu: MultiGpu
    minimum_gpu_vram_bytes: int | None = Field(ge=1)
    estimated_runtime_seconds: int | None = Field(ge=1)


class ModelCapabilities(ContractModel):
    contract_version: ContractVersion
    model_id: str = Field(pattern=MODEL_ID_PATTERN)
    display_name: str
    adapter: str
    is_mock: bool
    availability: Availability
    supported_pipeline_types: list[PipelineType] = Field(min_length=1)
    supported_asset_categories: list[AssetCategory] = Field(min_length=1)
    inputs: ModelInputs
    supported_output_formats: list[OutputFormat] = Field(min_length=1)
    runtime: ModelRuntime
    options_schema: dict[str, OptionSpec]
    unknown_requirements: list[str]

    @property
    def accepts_jobs(self) -> bool:
        return self.availability in ("available", "experimental")
