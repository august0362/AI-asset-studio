"""Adapter for the real Text→2D models chosen in D-034: Animagine XL 4.0, FLUX.2 [klein] 4B, MOSS-Image-SFT.

One adapter, one remote entrypoint, one recipe per model. Recipes hold what the M4 benchmark measured: pinned
repository revisions and libraries, steps, guidance, scheduler and prompt handling. Weights are ungated and are
downloaded inside the Kaggle run, so jobs need the internet (D-032).

Style images (D-042, CONTRACTS §14.9): ``style_reference`` inputs give the style, the prompt gives the content.
Animagine uses the pinned IP-Adapter, downloaded inside the run only when the job has style images; nothing is
downloaded on the local machine.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from ...contracts import CreateJobRequest, ErrorItem, ExpectedOutput, GenerationRequest
from ...contracts.common import error, warning
from ..base import ModelAdapter, deadline_seconds, task_output_name

PINS = ["diffusers==0.42.1", "transformers==5.22.1", "accelerate==1.15.0"]

# Width × height pairs measured in the benchmark (about 1 MP). MOSS-Image's fp16 margin shrinks as the pixel count
# grows (D-034), and the T4's 15 GiB leaves little room above 1 MP, so other pairs are rejected.
SIZES = {(832, 1216), (1024, 1024), (1216, 832)}

ANIMAGINE_QUALITY_TAGS = "masterpiece, high score, great score, absurdres"
ANIMAGINE_NEGATIVE = (
    "lowres, bad anatomy, bad hands, text, error, missing finger, extra digits, fewer digits, cropped, "
    "worst quality, low quality, low score, bad score, average score, signature, watermark, username, blurry"
)

# D-042 (5): IP-Adapter for SDXL, Apache-2.0, not gated. Only the safetensors weights are fetched (the repository
# also holds .bin copies). InstantStyle: the adapter acts on the style block only (``up.block_0``, attention 1).
IP_ADAPTER = {
    "key": "ip_adapter_sdxl",
    "repo": "h94/IP-Adapter",
    "revision": "018e402774aeeddd60609b4ecdb7e298259dc729",
    "allow_patterns": [
        "sdxl_models/ip-adapter_sdxl.safetensors",
        "sdxl_models/image_encoder/config.json",
        "sdxl_models/image_encoder/model.safetensors",
    ],
    "subfolder": "sdxl_models",
    "weight_name": "ip-adapter_sdxl.safetensors",
    "image_encoder_folder": "image_encoder",
    "style_block": {"up": {"block_0": [0.0, 1.0, 0.0]}},
}
DEFAULT_STYLE_STRENGTH = 0.6
# Seconds per image of FLUX.2 [klein] with N reference images, measured in G.0 (CONTRACTS §14.9); 9 s without.
KLEIN_STYLE_SECONDS = {1: 23, 2: 43, 4: 92}

RECIPES: dict[str, dict[str, Any]] = {
    "animagine-xl-4": {
        "key": "animagine_xl_4",
        "family": "sdxl",
        "repo": "cagliostrolab/animagine-xl-4.0",
        "revision": "2b7c1b397761bf5bd3cc42e5b39ec99314a75a96",
        "allow_patterns": [
            "model_index.json",
            "scheduler/*",
            "tokenizer/*",
            "tokenizer_2/*",
            "text_encoder/*",
            "text_encoder_2/*",
            "unet/*",
            "vae/*",
        ],
        "scheduler": "euler_ancestral",
        "steps": 28,
        "guidance": 5.0,
    },
    "flux2-klein-4b": {
        "key": "flux2_klein_4b",
        "family": "flux2_klein",
        "repo": "black-forest-labs/FLUX.2-klein-4B",
        "revision": "e7b7dc27f91deacad38e78976d1f2b499d76a294",
        "allow_patterns": [
            "model_index.json",
            "scheduler/*",
            "tokenizer/*",
            "text_encoder/*",
            "transformer/*",
            "vae/*",
        ],
        "scheduler": "flow_match_euler",
        "steps": 4,
        "guidance": 1.0,
    },
    "moss-image-sft": {
        "key": "moss_image_sft",
        "family": "moss",
        "repo": "OpenMOSS-Team/MOSS-Image-SFT",
        "revision": "f972bd4b4b9e3852133cc5da954d87bc32cd8fb9",
        "allow_patterns": [
            "model_index.json",
            "pipeline_moss_image.py",
            "scheduler/*",
            "tokenizer/*",
            "text_encoder/*",
            "transformer/*",
            "vae/*",
        ],
        "scheduler": "moss_flow_match_euler",
        "steps": 50,
        "guidance": 3.0,
        "extra": {"uncond_skip_layers": [22]},
    },
}


def _merge_terms(*parts: str | None) -> str:
    seen: list[str] = []
    for part in parts:
        for term in (t.strip() for t in (part or "").split(",")):
            if term and term.lower() not in (s.lower() for s in seen):
                seen.append(term)
    return ", ".join(seen)


class DiffusersTextTo2DAdapter(ModelAdapter):
    entrypoint = "models/adapters/diffusers_text_to_2d/remote_entry.py"
    requires_internet = True
    supports_batch = True

    def _recipe(self) -> dict[str, Any]:
        return RECIPES[self._capabilities.model_id]

    def model_revision(self) -> str | None:
        return self._recipe()["revision"]

    def _prompts(self, prompt: str | None, negative: str | None) -> tuple[str, str | None]:
        prompt = (prompt or "").strip()
        if (
            self._recipe()["family"] == "sdxl"
        ):  # Animagine's model card: quality tags last, its own negative list
            return _merge_terms(prompt, ANIMAGINE_QUALITY_TAGS), _merge_terms(ANIMAGINE_NEGATIVE, negative)
        return prompt, negative

    def validate_model_specific(self, request: CreateJobRequest) -> list[ErrorItem]:
        options = request.options or {}
        problems: list[ErrorItem] = []
        if options.get("style_strength") is not None and not any(
            i.role == "style_reference" for i in request.inputs
        ):  # §14.9: never silently ignored
            problems.append(
                error(
                    "MODEL_OPTION_INVALID",
                    "options.style_strength",
                    "Style strength needs at least one style image.",
                    {"value": options["style_strength"], "reason": "requires_style_reference"},
                )
            )
        images = sum(1 for i in request.inputs if i.role == "style_reference")
        if images and self._recipe()["family"] == "flux2_klein":
            measured_with = min(k for k in KLEIN_STYLE_SECONDS if k >= images)  # never an unmeasured value
            measured = KLEIN_STYLE_SECONDS[measured_with]
            problems.append(
                warning(
                    "MODEL_RUNTIME_EXCEEDS_ESTIMATE",
                    "inputs",
                    f"Style images make this model slower: about {measured} s per image was measured with "
                    f"{measured_with} image(s), against the "
                    f"{self._capabilities.runtime.estimated_runtime_seconds} s estimate.",
                    {
                        "estimated_seconds": self._capabilities.runtime.estimated_runtime_seconds,
                        "measured_seconds": measured,
                        "images": images,
                    },
                )
            )
        return problems + self._size_problems(options)

    def _size_problems(self, options: dict[str, Any]) -> list[ErrorItem]:
        width, height = options.get("width", 1024), options.get("height", 1024)
        if (width, height) in SIZES or not isinstance(width, int) or not isinstance(height, int):
            return []  # type and enum problems are reported by the option checks
        allowed = [f"{w}x{h}" for w, h in sorted(SIZES)]
        return [
            error(
                "MODEL_OPTION_INVALID",
                "options.height",
                f"Size {width}x{height} is not supported; use one of {', '.join(allowed)}.",
                {"value": f"{width}x{height}", "allowed": allowed},
            )
        ]

    def expected_outputs(self, request: GenerationRequest) -> list[ExpectedOutput]:
        return [ExpectedOutput(name="image.png", kind="image", format="png", required=True)]

    def build_arguments(self, request: GenerationRequest) -> dict[str, Any]:
        recipe = self._recipe()
        options = request.options
        prompt, negative = self._prompts(request.prompt, options.get("negative_prompt"))
        style = [
            {
                "input_id": i.input_id,
                "file": PurePosixPath(i.path).name,
                "width": i.width,
                "height": i.height,
            }
            for i in request.inputs
            if i.role == "style_reference"
        ]
        extra: dict[str, Any] = {}
        if style:
            extra["style_images"] = style
            if recipe["family"] == "sdxl":
                strength = options.get("style_strength")
                extra["style_strength"] = DEFAULT_STYLE_STRENGTH if strength is None else strength
                extra["ip_adapter"] = IP_ADAPTER
        return {
            **extra,
            "model_id": request.model_id,
            "asset_category": request.asset_category,
            "prompt": prompt,
            "negative_prompt": negative,
            "width": options.get("width", 1024),
            "height": options.get("height", 1024),
            "seed": options.get("seed"),
            "recipe": recipe,
            "pins": PINS,
        }

    def build_batch_arguments(self, request: GenerationRequest) -> dict[str, Any]:
        tasks = []
        for task in request.tasks or []:
            prompt, negative = self._prompts(task.prompt, task.options.get("negative_prompt"))
            tasks.append(
                {
                    "task_id": task.task_id,
                    "output": task_output_name(task.task_id),
                    "prompt": prompt,
                    "negative_prompt": negative,
                    "width": task.options.get("width", 1024),
                    "height": task.options.get("height", 1024),
                    "seed": task.options.get("seed"),
                }
            )
        return {
            "model_id": request.model_id,
            "asset_category": request.asset_category,
            "tasks": tasks,
            "deadline_seconds": deadline_seconds(request),
            "recipe": self._recipe(),
            "pins": PINS,
        }
