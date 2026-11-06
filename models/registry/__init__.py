"""Capability registry, catalog and validation stages 1-6."""

from .catalog import PIPELINES, PIPELINES_BY_TYPE, build_catalog
from .mocks import MOCK_CAPABILITIES
from .registry import ModelRegistry, default_registry
from .validation import (
    ModelValidation,
    UploadLookup,
    check_option,
    normalize_options,
    normalize_prompt,
    parse_create_job_request,
    validate_model_request,
)

__all__ = [
    "MOCK_CAPABILITIES",
    "PIPELINES",
    "PIPELINES_BY_TYPE",
    "ModelRegistry",
    "ModelValidation",
    "UploadLookup",
    "build_catalog",
    "check_option",
    "default_registry",
    "normalize_options",
    "normalize_prompt",
    "parse_create_job_request",
    "validate_model_request",
]
