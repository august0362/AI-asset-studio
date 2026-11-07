"""Capability records of the real Text→2D models chosen by the owner (DECISIONS D-034).

Every number comes from the M4 benchmark on one Kaggle T4 in fp16 (2026-11-06):
``estimated_runtime_seconds`` is the measured mean time for one ~1 MP image, excluding package installs, weight
download and loading (the planner's overhead covers those); ``minimum_gpu_vram_bytes`` is the measured peak that
PyTorch reserved, rounded up to a whole GiB. Only ``character`` is enabled for now (MILESTONES M4 scope).

D-041/D-042 (step G.0, 2026-11-07, T4 fp16, 1024x1024): prompt limits follow each text encoder
(CONTRACTS §14.8), and style images (``style_reference``, §14.9) are offered where they were measured:
Animagine XL 4.0 + IP-Adapter (style block only, image encoder moved off the GPU after encoding) peaked at
12.26 GiB with 1, 2 and 4 images and took 30-32 s per image, against 29.6 s without. FLUX.2 [klein] with reference
images peaked at 10.86-11.22 GiB but slowed down a lot (see ``KLEIN_STYLE_SECONDS``); its estimate stays the one
measured without images, and validation warns instead (owner, D-042 (10)).
"""

from __future__ import annotations

from ..contracts import ModelCapabilities

GIB = 2**30
_SEED = {"type": "integer", "minimum": 0, "maximum": 4294967295, "default": None}
_SIZE = {"type": "integer", "enum": [832, 1024, 1216], "default": 1024}
_NEGATIVE = {"type": "string", "max_length": 1000, "default": None}
# FLUX.2 [klein] reads at most 2 048 Qwen3 tokens: a 1 493-token prompt was read in full with a 2 048-token window
# (its last sentence showed in the image) and cut at 512 or 1 024. About 4 characters per token gives 8 192; the
# remote token check enforces the window itself. Animagine reads in 75-token CLIP chunks (no limit); MOSS-Image's
# encoder takes 4 096 tokens, beyond what 10 000 characters produce (D-041 (7)).
PROMPT_LIMITS = {"animagine-xl-4": 10_000, "flux2-klein-4b": 8_192, "moss-image-sft": 10_000}
# Style images per model, measured in G.0: the largest count whose peak stayed within 14 GiB (D-042 (7)).
STYLE_IMAGES = {"animagine-xl-4": 4, "flux2-klein-4b": 4, "moss-image-sft": 0}
STYLE_STRENGTH = {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.6}
_STYLE_INPUTS = {
    "min_images": 0,
    "supported_image_roles": ["style_reference"],
    "required_image_roles": [],
    "supported_mime_types": ["image/png", "image/jpeg", "image/webp"],
    "maximum_file_size_bytes": 52_428_800,
    "min_image_width": 256,
    "min_image_height": 256,
    "max_image_width": 4096,
    "max_image_height": 4096,
}
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
    images = STYLE_IMAGES[model_id]
    if images and model_id == "animagine-xl-4":
        options["style_strength"] = STYLE_STRENGTH  # the IP-Adapter scale (CONTRACTS §14.9)
    prompt = {"prompt_supported": True, "prompt_required": True, "prompt_max_length": PROMPT_LIMITS[model_id]}
    inputs = {**prompt, **_STYLE_INPUTS, "max_images": images} if images else {**prompt, **_NO_IMAGES}
    return {
        "contract_version": "1.0",
        "model_id": model_id,
        "display_name": name,
        "adapter": "diffusers_text_to_2d",
        "is_mock": False,
        "availability": "available",
        "supported_pipeline_types": ["text_to_2d"],
        "supported_asset_categories": ["character"],
        "inputs": inputs,
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
