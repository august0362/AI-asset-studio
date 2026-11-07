"""Validation stages 1-6 (docs/CONTRACTS.md §8.1). Pure functions: no storage, HTTP or Kaggle.

Stage 7 (compute) lives in the backend, which combines the Kaggle planner with these results.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from ..contracts import (
    ASSET_CATEGORIES,
    MAX_IMAGES_PER_REQUEST,
    PIPELINE_TYPES,
    PROMPT_MAX_LENGTH,
    VIEW_ROLES,
    CreateJobRequest,
    ErrorItem,
    ModelCapabilities,
    OptionSpec,
    UploadRecord,
    error,
    warning,
)
from .catalog import PIPELINES_BY_TYPE
from .registry import ModelRegistry

UploadLookup = Callable[[str], UploadRecord | None]
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


# --- Stage 1: schema -------------------------------------------------------------------------------------


def _field_path(loc: tuple[Any, ...]) -> str | None:
    path = ""
    for part in loc:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += ("." if path else "") + str(part)
    return path or None


def _schema_message(item: dict[str, Any]) -> str:
    kind = item.get("type")
    if kind == "extra_forbidden":
        return "Unknown field. Remove it; unknown fields are rejected."
    if kind == "missing":
        return "This field is required."
    return f"Invalid value: {item.get('msg', 'type error')}."


def parse_create_job_request(raw: Any) -> tuple[CreateJobRequest | None, list[ErrorItem]]:
    """Stage 1. Short-circuits: returns ``(None, errors)`` on any schema problem."""
    if not isinstance(raw, dict):
        return None, [error("REQUEST_FIELD_INVALID", None, "The request body must be a JSON object.")]
    version = raw.get("contract_version")
    if isinstance(version, str):
        match = _VERSION_RE.match(version)
        if match and match.group(1) != "1":
            return None, [
                error(
                    "CONTRACT_VERSION_UNSUPPORTED",
                    "contract_version",
                    f"Contract version {version} is not supported. This server implements 1.x.",
                    {"supported_major": 1, "provided": version},
                )
            ]
        if not match:
            return None, [
                error(
                    "REQUEST_FIELD_INVALID",
                    "contract_version",
                    "contract_version must look like '1.0'.",
                    {"provided": version},
                )
            ]
    try:
        return CreateJobRequest.model_validate(raw), []
    except ValidationError as exc:
        return None, [
            error(
                "REQUEST_FIELD_INVALID",
                _field_path(item["loc"]),
                _schema_message(item),
                {"type": item["type"]},
            )
            for item in exc.errors(include_url=False)
        ]


# --- Stages 2-6 ------------------------------------------------------------------------------------------


@dataclass
class ModelValidation:
    errors: list[ErrorItem] = field(default_factory=list)
    warnings: list[ErrorItem] = field(default_factory=list)
    capabilities: ModelCapabilities | None = None  # set once stage 3 passed
    prompt: str | None = None  # trimmed; blank -> None


def normalize_prompt(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    trimmed = prompt.strip()
    return trimmed or None


def _stage_catalog(req: CreateJobRequest, result: ModelValidation) -> None:
    if req.pipeline_type not in PIPELINE_TYPES:
        result.errors.append(
            error(
                "PIPELINE_UNKNOWN",
                "pipeline_type",
                f"Unknown pipeline '{req.pipeline_type}'.",
                {"supported": list(PIPELINE_TYPES)},
            )
        )
    else:
        pipeline = PIPELINES_BY_TYPE[req.pipeline_type]
        if pipeline.availability not in ("available", "experimental"):
            result.errors.append(
                error(
                    "PIPELINE_NOT_AVAILABLE",
                    "pipeline_type",
                    f"The {pipeline.display_name} pipeline is not available yet ({pipeline.availability}).",
                    {"availability": pipeline.availability},
                )
            )
    if req.asset_category not in ASSET_CATEGORIES:
        result.errors.append(
            error(
                "ASSET_CATEGORY_UNKNOWN",
                "asset_category",
                f"Unknown asset category '{req.asset_category}'.",
                {"supported": list(ASSET_CATEGORIES)},
            )
        )


def _stage_model(req: CreateJobRequest, registry: ModelRegistry, result: ModelValidation) -> None:
    caps = registry.get(req.model_id)
    if caps is None:
        result.errors.append(error("MODEL_NOT_FOUND", "model_id", f"Model '{req.model_id}' does not exist."))
        return
    if not caps.accepts_jobs:
        result.errors.append(
            error(
                "MODEL_UNAVAILABLE",
                "model_id",
                f"{caps.display_name} is not available ({caps.availability}).",
                {"availability": caps.availability},
            )
        )
    if req.pipeline_type not in caps.supported_pipeline_types:
        result.errors.append(
            error(
                "MODEL_PIPELINE_INCOMPATIBLE",
                "model_id",
                f"{caps.display_name} does not support the {req.pipeline_type} pipeline.",
                {"supported_pipeline_types": caps.supported_pipeline_types},
            )
        )
    if req.asset_category not in caps.supported_asset_categories:
        result.errors.append(
            error(
                "MODEL_CATEGORY_INCOMPATIBLE",
                "asset_category",
                f"{caps.display_name} does not support the '{req.asset_category}' category.",
                {"supported_asset_categories": caps.supported_asset_categories},
            )
        )
    if not result.errors:
        result.capabilities = caps
        if caps.availability == "experimental":
            result.warnings.append(
                warning(
                    "MODEL_EXPERIMENTAL",
                    "model_id",
                    f"{caps.display_name} is experimental. Results may vary.",
                )
            )


def _stage_prompt(req: CreateJobRequest, caps: ModelCapabilities, result: ModelValidation) -> None:
    prompt = normalize_prompt(req.prompt)
    result.prompt = prompt
    spec = caps.inputs
    if not spec.prompt_supported:
        if prompt is not None:
            result.errors.append(
                error(
                    "MODEL_PROMPT_NOT_SUPPORTED",
                    "prompt",
                    f"{caps.display_name} does not accept a text prompt. Remove the prompt.",
                )
            )
        return
    if prompt is None:
        if spec.prompt_required:
            result.errors.append(error("MODEL_PROMPT_REQUIRED", "prompt", "This model requires a prompt."))
        return
    limit = min(spec.prompt_max_length or PROMPT_MAX_LENGTH, PROMPT_MAX_LENGTH)
    if len(prompt) > limit:
        result.errors.append(
            error(
                "MODEL_PROMPT_TOO_LONG",
                "prompt",
                f"The prompt has {len(prompt)} characters; the limit is {limit}.",
                {"max_length": limit, "length": len(prompt)},
            )
        )


def _stage_images(
    req: CreateJobRequest, caps: ModelCapabilities, lookup: UploadLookup, result: ModelValidation
) -> None:
    spec = caps.inputs
    inputs = req.inputs
    if spec.max_images == 0:
        if inputs:
            result.errors.append(
                error(
                    "MODEL_IMAGE_INPUT_NOT_SUPPORTED",
                    "inputs",
                    f"{caps.display_name} does not accept images. Remove the {len(inputs)} image(s).",
                    {"provided": len(inputs)},
                )
            )
        return

    max_images = min(spec.max_images, MAX_IMAGES_PER_REQUEST)
    if len(inputs) > max_images:
        result.errors.append(
            error(
                "MODEL_INPUT_COUNT_EXCEEDED",
                "inputs",
                f"This model accepts at most {max_images} image{'s' if max_images != 1 else ''}; "
                f"{len(inputs)} were provided.",
                {"max_images": max_images, "provided": len(inputs)},
            )
        )
    elif len(inputs) < spec.min_images:
        result.errors.append(
            error(
                "MODEL_INPUT_COUNT_INSUFFICIENT",
                "inputs",
                f"This model needs at least {spec.min_images} image(s); {len(inputs)} were provided.",
                {"min_images": spec.min_images, "provided": len(inputs)},
            )
        )

    seen_views: set[str] = set()
    for index, item in enumerate(inputs):
        role_field = f"inputs[{index}].role"
        if item.role not in spec.supported_image_roles:
            result.errors.append(
                error(
                    "MODEL_IMAGE_ROLE_UNSUPPORTED",
                    role_field,
                    f"{caps.display_name} does not accept an image with the role '{item.role}'.",
                    {"role": item.role, "supported_roles": spec.supported_image_roles},
                )
            )
        if item.role in VIEW_ROLES:
            if item.role in seen_views:
                result.errors.append(
                    error(
                        "MODEL_IMAGE_ROLE_DUPLICATE",
                        role_field,
                        f"The '{item.role}' view is used more than once. Each view may appear only once.",
                        {"role": item.role},
                    )
                )
            seen_views.add(item.role)
        _check_upload(index, item.upload_id, caps, lookup, result)

    present = {item.role for item in inputs}
    missing = [role for role in spec.required_image_roles if role not in present]
    if missing:
        names = ", ".join(missing)
        result.errors.append(
            error(
                "MODEL_REQUIRED_VIEW_MISSING",
                "inputs",
                f"This model requires a {names} view. Add an image with the role "
                + " and ".join(f"'{m}'" for m in missing)
                + ".",
                {"missing_roles": missing},
            )
        )


def _check_upload(
    index: int, upload_id: str, caps: ModelCapabilities, lookup: UploadLookup, result: ModelValidation
) -> None:
    field_name = f"inputs[{index}].upload_id"
    record = lookup(upload_id)
    if record is None:
        result.errors.append(
            error(
                "UPLOAD_NOT_FOUND",
                field_name,
                "This upload does not exist or has expired. Upload the image again.",
                {"upload_id": upload_id},
            )
        )
        return
    spec = caps.inputs
    if spec.supported_mime_types is not None and record.mime_type not in spec.supported_mime_types:
        result.errors.append(
            error(
                "MODEL_UNSUPPORTED_FILE_FORMAT",
                field_name,
                f"{caps.display_name} does not accept {record.mime_type} images.",
                {"mime_type": record.mime_type, "supported_mime_types": spec.supported_mime_types},
            )
        )
    if spec.maximum_file_size_bytes is not None and record.size_bytes > spec.maximum_file_size_bytes:
        result.errors.append(
            error(
                "MODEL_FILE_TOO_LARGE",
                field_name,
                f"The image is {record.size_bytes} bytes; this model accepts at most "
                f"{spec.maximum_file_size_bytes} bytes.",
                {"size_bytes": record.size_bytes, "maximum_file_size_bytes": spec.maximum_file_size_bytes},
            )
        )
    limits = {
        "min_width": spec.min_image_width,
        "min_height": spec.min_image_height,
        "max_width": spec.max_image_width,
        "max_height": spec.max_image_height,
    }
    too_small = (limits["min_width"] is not None and record.width < limits["min_width"]) or (
        limits["min_height"] is not None and record.height < limits["min_height"]
    )
    too_big = (limits["max_width"] is not None and record.width > limits["max_width"]) or (
        limits["max_height"] is not None and record.height > limits["max_height"]
    )
    if too_small or too_big:
        result.errors.append(
            error(
                "MODEL_IMAGE_DIMENSIONS_INVALID",
                field_name,
                f"The image is {record.width}×{record.height}; this model accepts "
                f"{limits['min_width'] or 1}×{limits['min_height'] or 1} to "
                f"{limits['max_width'] or '∞'}×{limits['max_height'] or '∞'}.",
                {"width": record.width, "height": record.height, "allowed": limits},
            )
        )


def _stage_output(req: CreateJobRequest, caps: ModelCapabilities, result: ModelValidation) -> None:
    pipeline = PIPELINES_BY_TYPE.get(req.pipeline_type)
    allowed = [f for f in caps.supported_output_formats if pipeline is None or f in pipeline.output_formats]
    if req.output_format not in allowed:
        result.errors.append(
            error(
                "MODEL_OUTPUT_FORMAT_UNSUPPORTED",
                "output_format",
                f"{caps.display_name} cannot produce '{req.output_format}'. Supported: {', '.join(allowed)}.",
                {"output_format": req.output_format, "supported_output_formats": allowed},
            )
        )


def check_option(name: str, spec: OptionSpec, value: Any) -> ErrorItem | None:
    field_name = f"options.{name}"

    def invalid(reason: str, **details: Any) -> ErrorItem:
        return error(
            "MODEL_OPTION_INVALID", field_name, f"Option '{name}' {reason}.", {"value": value, **details}
        )

    if value is None:
        return None if spec.default is None else invalid("must not be null")
    if spec.type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        return invalid("must be an integer", expected_type="integer")
    if spec.type == "number" and (
        isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
    ):
        return invalid("must be a number", expected_type="number")
    if spec.type == "string" and not isinstance(value, str):
        return invalid("must be a string", expected_type="string")
    if spec.type == "boolean" and not isinstance(value, bool):
        return invalid("must be true or false", expected_type="boolean")
    if spec.enum is not None and value not in spec.enum:
        return invalid(f"must be one of {spec.enum}", allowed=spec.enum)
    if spec.minimum is not None and value < spec.minimum:
        return invalid(f"must be at least {spec.minimum}", minimum=spec.minimum)
    if spec.maximum is not None and value > spec.maximum:
        return invalid(f"must be at most {spec.maximum}", maximum=spec.maximum)
    if spec.max_length is not None and isinstance(value, str) and len(value) > spec.max_length:
        return invalid(f"must be at most {spec.max_length} characters", max_length=spec.max_length)
    return None


def _stage_options(req: CreateJobRequest, caps: ModelCapabilities, result: ModelValidation) -> None:
    for name, value in req.options.items():
        spec = caps.options_schema.get(name)
        if spec is None:
            result.errors.append(
                error(
                    "MODEL_OPTION_UNSUPPORTED",
                    f"options.{name}",
                    f"{caps.display_name} does not support the option '{name}'.",
                    {"option": name, "supported_options": list(caps.options_schema)},
                )
            )
            continue
        problem = check_option(name, spec, value)
        if problem is not None:
            result.errors.append(problem)


def normalize_options(caps: ModelCapabilities, options: dict[str, Any]) -> dict[str, Any]:
    """Every schema option, with defaults filled in (GenerationRequest.options)."""
    return {
        name: options[name] if options.get(name) is not None else spec.default
        for name, spec in caps.options_schema.items()
    }


def validate_model_request(
    req: CreateJobRequest, registry: ModelRegistry, lookup: UploadLookup
) -> ModelValidation:
    """Stages 2-6. Stages 2 and 3 short-circuit; stages 4-6 report every error."""
    result = ModelValidation()
    _stage_catalog(req, result)
    if result.errors:
        return result
    _stage_model(req, registry, result)
    caps = result.capabilities
    if caps is None:
        return result
    _stage_prompt(req, caps, result)
    _stage_images(req, caps, lookup, result)
    _stage_output(req, caps, result)
    _stage_options(req, caps, result)
    if not result.errors:
        for item in registry.adapter(caps.model_id).validate_model_specific(req):
            (result.warnings if item.severity == "warning" else result.errors).append(item)
    return result
