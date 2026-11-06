"""The five mock capability records (docs/CONTRACTS.md §2.2). Test fixtures, not a model selection.

Values the table does not state are marked ``# gap`` and reported to the owner.
"""

from __future__ import annotations

from ..contracts import ModelCapabilities

ALL_CATEGORIES = ["character", "skill_effect", "weapon", "companion"]
_SEED = {"type": "integer", "minimum": 0, "maximum": 4294967295, "default": None}
_SIZE = {"type": "integer", "enum": [512, 768, 1024], "default": 1024}
_NO_IMAGES = {
    "min_images": 0,
    "max_images": 0,
    "supported_image_roles": [],
    "required_image_roles": [],
    "supported_mime_types": None,
    "maximum_file_size_bytes": None,
    "min_image_width": None,
    "min_image_height": None,
    "max_image_width": None,
    "max_image_height": None,
}
_PROMPT_REQUIRED = {"prompt_supported": True, "prompt_required": True, "prompt_max_length": 1000}
_NO_PROMPT = {"prompt_supported": False, "prompt_required": False, "prompt_max_length": None}
_I3D_IMAGE_LIMITS = {  # §2.1 example values; reused for mock-i3d-single (gap)
    "supported_mime_types": ["image/png", "image/jpeg"],
    "maximum_file_size_bytes": 20971520,
    "min_image_width": 512,
    "min_image_height": 512,
    "max_image_width": 4096,
    "max_image_height": 4096,
}

MOCK_CAPABILITIES: list[ModelCapabilities] = [
    ModelCapabilities.model_validate(record)
    for record in [
        {
            "contract_version": "1.0",
            "model_id": "mock-t2d-basic",
            "display_name": "Mock Text→2D",
            "adapter": "mock_text_to_2d",
            "is_mock": True,
            "availability": "available",
            "supported_pipeline_types": ["text_to_2d"],
            "supported_asset_categories": ALL_CATEGORIES,
            "inputs": {**_PROMPT_REQUIRED, **_NO_IMAGES},
            "supported_output_formats": ["png"],
            # VRAM is n/a: the model runs on CPU, so no GPU memory minimum applies.
            "runtime": {
                "supported_accelerators": ["cpu", "gpu_cuda"],
                "multi_gpu": "unsupported",
                "minimum_gpu_vram_bytes": None,
                "estimated_runtime_seconds": 30,
            },
            "options_schema": {
                "seed": _SEED,
                "width": _SIZE,
                "height": _SIZE,
                "negative_prompt": {"type": "string", "max_length": 1000, "default": None},
            },
            "unknown_requirements": [],
        },
        {
            "contract_version": "1.0",
            "model_id": "mock-t2d-styleref",
            "display_name": "Mock Text→2D with style reference",
            "adapter": "mock_text_to_2d",
            "is_mock": True,
            "availability": "experimental",
            "supported_pipeline_types": ["text_to_2d"],
            "supported_asset_categories": ALL_CATEGORIES,
            "inputs": {
                **_PROMPT_REQUIRED,
                "min_images": 0,
                "max_images": 1,
                "supported_image_roles": ["style_reference"],
                "required_image_roles": [],
                "supported_mime_types": ["image/png", "image/jpeg", "image/webp"],  # gap
                "maximum_file_size_bytes": 20971520,  # gap
                "min_image_width": 256,  # gap
                "min_image_height": 256,  # gap
                "max_image_width": 4096,  # gap
                "max_image_height": 4096,  # gap
            },
            "supported_output_formats": ["png"],
            "runtime": {
                "supported_accelerators": ["gpu_cuda"],
                "multi_gpu": "unsupported",  # gap
                "minimum_gpu_vram_bytes": None,
                "estimated_runtime_seconds": 60,
            },
            "options_schema": {"seed": _SEED},
            "unknown_requirements": ["runtime.minimum_gpu_vram_bytes"],
        },
        {
            "contract_version": "1.0",
            "model_id": "mock-i3d-single",
            "display_name": "Mock Single-view Image→3D",
            "adapter": "mock_image_to_3d",
            "is_mock": True,
            "availability": "available",
            "supported_pipeline_types": ["image_to_3d"],
            "supported_asset_categories": ["character", "weapon", "companion"],
            "inputs": {
                **_NO_PROMPT,
                "min_images": 1,
                "max_images": 1,
                "supported_image_roles": ["front"],
                "required_image_roles": ["front"],
                **_I3D_IMAGE_LIMITS,
            },
            "supported_output_formats": ["glb"],
            "runtime": {
                "supported_accelerators": ["gpu_cuda"],
                "multi_gpu": "unsupported",  # gap
                "minimum_gpu_vram_bytes": None,
                "estimated_runtime_seconds": 120,
            },
            "options_schema": {"seed": _SEED},
            "unknown_requirements": ["runtime.minimum_gpu_vram_bytes"],
        },
        {  # identical to the §2.1 example (a contract test compares them)
            "contract_version": "1.0",
            "model_id": "mock-i3d-multiview",
            "display_name": "Mock Multiview Image→3D",
            "adapter": "mock_image_to_3d",
            "is_mock": True,
            "availability": "available",
            "supported_pipeline_types": ["image_to_3d"],
            "supported_asset_categories": ["character", "companion"],
            "inputs": {
                **_NO_PROMPT,
                "min_images": 2,
                "max_images": 4,
                "supported_image_roles": ["front", "side", "back", "detail"],
                "required_image_roles": ["front", "side"],
                **_I3D_IMAGE_LIMITS,
            },
            "supported_output_formats": ["glb"],
            "runtime": {
                "supported_accelerators": ["gpu_cuda"],
                "multi_gpu": "optional",
                "minimum_gpu_vram_bytes": 12884901888,
                "estimated_runtime_seconds": 900,
            },
            "options_schema": {
                "seed": _SEED,
                "texture_resolution": {"type": "integer", "enum": [1024, 2048], "default": 1024},
            },
            "unknown_requirements": [],
        },
        {
            "contract_version": "1.0",
            "model_id": "mock-t3d-basic",
            "display_name": "Mock Text→3D",
            "adapter": "mock_text_to_3d",  # no adapter until M6; the model is `planned` and never invoked
            "is_mock": True,
            "availability": "planned",
            "supported_pipeline_types": ["text_to_3d"],
            "supported_asset_categories": ALL_CATEGORIES,
            "inputs": {**_PROMPT_REQUIRED, **_NO_IMAGES},
            "supported_output_formats": ["glb"],
            "runtime": {
                "supported_accelerators": ["gpu_cuda"],
                "multi_gpu": "unsupported",  # gap
                "minimum_gpu_vram_bytes": None,
                "estimated_runtime_seconds": None,
            },
            "options_schema": {"seed": _SEED},
            "unknown_requirements": ["runtime.minimum_gpu_vram_bytes", "runtime.estimated_runtime_seconds"],
        },
    ]
]
