"""Pipeline catalog (docs/CONTRACTS.md §5.1)."""

from __future__ import annotations

from ..contracts import (
    ASSET_CATEGORIES,
    CONTRACT_VERSION,
    IMAGE_ROLES,
    MAX_IMAGES_PER_REQUEST,
    MAX_UPLOAD_BYTES,
    PROMPT_MAX_LENGTH,
    SUPPORTED_UPLOAD_MIME_TYPES,
    Catalog,
    CatalogLimits,
    PipelineInfo,
)

PIPELINES: list[PipelineInfo] = [
    PipelineInfo(
        pipeline_type="text_to_2d", display_name="Text → 2D", availability="available", output_formats=["png"]
    ),
    PipelineInfo(
        pipeline_type="image_to_3d",
        display_name="Image → 3D",
        availability="available",
        output_formats=["glb"],
    ),
    PipelineInfo(
        pipeline_type="text_to_3d", display_name="Text → 3D", availability="planned", output_formats=["glb"]
    ),
]
PIPELINES_BY_TYPE = {p.pipeline_type: p for p in PIPELINES}


def build_catalog() -> Catalog:
    return Catalog(
        contract_version=CONTRACT_VERSION,
        pipelines=PIPELINES,
        asset_categories=list(ASSET_CATEGORIES),
        image_roles=list(IMAGE_ROLES),
        limits=CatalogLimits(
            max_upload_bytes=MAX_UPLOAD_BYTES,
            max_images_per_request=MAX_IMAGES_PER_REQUEST,
            prompt_max_length=PROMPT_MAX_LENGTH,
            supported_upload_mime_types=list(SUPPORTED_UPLOAD_MIME_TYPES),
        ),
    )
