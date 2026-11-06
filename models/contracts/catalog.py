"""Catalog (docs/CONTRACTS.md §5.1)."""

from __future__ import annotations

from .common import (
    AssetCategory,
    Availability,
    ContractModel,
    ContractVersion,
    ImageRole,
    OutputFormat,
    PipelineType,
)


class PipelineInfo(ContractModel):
    pipeline_type: PipelineType
    display_name: str
    availability: Availability
    output_formats: list[OutputFormat]


class CatalogLimits(ContractModel):
    max_upload_bytes: int
    max_images_per_request: int
    prompt_max_length: int
    supported_upload_mime_types: list[str]


class Catalog(ContractModel):
    contract_version: ContractVersion
    pipelines: list[PipelineInfo]
    asset_categories: list[AssetCategory]
    image_roles: list[ImageRole]
    limits: CatalogLimits
