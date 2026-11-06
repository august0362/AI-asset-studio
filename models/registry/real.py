"""Capability records of the real Text→2D models chosen by the owner (DECISIONS D-034).

Every number comes from the M4 benchmark on one Kaggle T4 in fp16 (2026-11-06):
``estimated_runtime_seconds`` is the measured mean time for one ~1 MP image, excluding package installs, weight
download and loading (the planner's overhead covers those); ``minimum_gpu_vram_bytes`` is the measured peak that
PyTorch reserved, rounded up to a whole GiB. Only ``character`` is enabled for now (MILESTONES M4 scope).
"""

from __future__ import annotations

from ..contracts import ModelCapabilities

GIB = 2**30
_SEED = {"type": "integer", "minimum": 0, "maximum": 4294967295, "default": None}
_SIZE = {"type": "integer", "enum": [832, 1024, 1216], "default": 1024}
_NEGATIVE = {"type": "string", "max_length": 1000, "default": None}
_PROMPT = {"prompt_supported": True, "prompt_required": True, "prompt_max_length": 2000}
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


def _record(model_id: str, name: str, seconds: int, vram_gib: int, negative: bool) -> dict:
    options = {"seed": _SEED, "width": _SIZE, "height": _SIZE}
    if negative:
        options["negative_prompt"] = _NEGATIVE
    return {
        "contract_version": "1.0",
        "model_id": model_id,
        "display_name": name,
        "adapter": "diffusers_text_to_2d",
        "is_mock": False,
        "availability": "available",
        "supported_pipeline_types": ["text_to_2d"],
        "supported_asset_categories": ["character"],
        "inputs": {**_PROMPT, **_NO_IMAGES},
        "supported_output_formats": ["png"],
        "runtime": {
            "supported_accelerators": ["gpu_cuda"],
            "multi_gpu": "unsupported",  # one model uses one T4; the second GPU stays idle
            "minimum_gpu_vram_bytes": vram_gib * GIB,
            "estimated_runtime_seconds": seconds,
        },
        "options_schema": options,
        "unknown_requirements": [],
    }


REAL_CAPABILITIES: list[ModelCapabilities] = [
    ModelCapabilities.model_validate(record)
    for record in [
        # Measured: 25.0 s per image (22.9-26.2), 13.0 GiB peak reserved.
        _record("animagine-xl-4", "Animagine XL 4.0", 25, 14, negative=True),
        # Measured: 8.6 s per image (8.3-9.0), 13.7 GiB peak reserved. Guidance-distilled: no negative prompt.
        _record("flux2-klein-4b", "FLUX.2 [klein] 4B", 9, 14, negative=False),
        # Measured: 354 s per image (342-363), 12.4 GiB peak reserved; the 9B text encoder also uses host RAM.
        _record("moss-image-sft", "MOSS-Image-SFT", 354, 13, negative=True),
    ]
]
