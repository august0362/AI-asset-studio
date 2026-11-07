"""Real Text→2D models (D-034): capability records, adapter arguments, size rule, remote entry set-up."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from models.adapters.diffusers_text_to_2d import (
    ANIMAGINE_NEGATIVE,
    ANIMAGINE_QUALITY_TAGS,
    PINS,
    RECIPES,
    SIZES,
    DiffusersTextTo2DAdapter,
    remote_entry,
)
from models.contracts import CreateJobRequest, GenerationRequest, utc_now
from models.registry import (
    MOCK_CAPABILITIES,
    REAL_CAPABILITIES,
    default_registry,
    full_registry,
    registry_for,
)
from tests.conftest import request_body

GIB = 2**30
JOB = "job_20261106T101500Z_a1b2c3"
MEASURED = {  # model_id: (display name, seconds per image, VRAM GiB, negative prompt) — D-034 benchmark
    "animagine-xl-4": ("Animagine XL 4.0", 25, 14, True),
    "flux2-klein-4b": ("FLUX.2 [klein] 4B", 9, 14, False),
    "moss-image-sft": ("MOSS-Image-SFT", 354, 13, True),
}
PROMPT_LIMIT = {"animagine-xl-4": 10_000, "flux2-klein-4b": 8_192, "moss-image-sft": 10_000}
STYLE_MAX = {"animagine-xl-4": 4, "flux2-klein-4b": 4, "moss-image-sft": 0}


def adapter(model_id: str) -> DiffusersTextTo2DAdapter:
    return full_registry().adapter(model_id)


def generation(model_id: str, prompt: str = "1girl, silver hair", **options) -> GenerationRequest:
    return GenerationRequest(
        contract_version="1.0",
        job_id=JOB,
        pipeline_type="text_to_2d",
        asset_category="character",
        model_id=model_id,
        prompt=prompt,
        inputs=[],
        options=options,
        output_format="png",
        created_at=utc_now(),
    )


def create(model_id: str, **options) -> CreateJobRequest:
    body = request_body(model_id=model_id, asset_category="character", options=options)
    return CreateJobRequest.model_validate(body)


# --- records ---------------------------------------------------------------------------------------------------


def test_records_are_the_three_chosen_models_with_measured_values():
    assert [c.model_id for c in REAL_CAPABILITIES] == list(MEASURED)
    for caps in REAL_CAPABILITIES:
        name, seconds, vram, negative = MEASURED[caps.model_id]
        assert caps.display_name == name and not caps.is_mock and caps.availability == "available"
        assert caps.adapter == "diffusers_text_to_2d"
        assert caps.supported_pipeline_types == ["text_to_2d"]
        assert caps.supported_asset_categories == ["character"]  # one category at a time (M4 scope)
        assert caps.supported_output_formats == ["png"]
        assert caps.runtime.supported_accelerators == ["gpu_cuda"]
        assert caps.runtime.multi_gpu == "unsupported"
        assert caps.runtime.estimated_runtime_seconds == seconds
        assert caps.runtime.minimum_gpu_vram_bytes == vram * GIB
        assert caps.inputs.prompt_required
        assert caps.inputs.prompt_max_length == PROMPT_LIMIT[caps.model_id]  # D-041 (7), G.0
        assert caps.inputs.max_images == STYLE_MAX[caps.model_id]  # D-042 (7), G.0
        if caps.inputs.max_images:
            assert caps.inputs.min_images == 0 and caps.inputs.supported_image_roles == ["style_reference"]
            assert caps.inputs.required_image_roles == []
            assert caps.inputs.supported_mime_types == ["image/png", "image/jpeg", "image/webp"]
            assert (caps.inputs.min_image_width, caps.inputs.max_image_width) == (256, 4096)
        assert ("style_strength" in caps.options_schema) is (caps.model_id == "animagine-xl-4")
        assert ("negative_prompt" in caps.options_schema) is negative
        assert caps.options_schema["width"].enum == caps.options_schema["height"].enum == [832, 1024, 1216]
        assert caps.unknown_requirements == []


def test_vram_fits_one_t4_and_no_null_requirement_is_hidden():
    for caps in REAL_CAPABILITIES:
        assert caps.runtime.minimum_gpu_vram_bytes <= 15 * GIB  # one Kaggle T4 (D-033)
        for key, value in caps.model_dump()["runtime"].items():
            assert value is not None, key


def test_real_models_appear_only_in_kaggle_mode():
    assert [c.model_id for c in registry_for("mock").list()] == [c.model_id for c in MOCK_CAPABILITIES]
    assert registry_for("mock").get("flux2-klein-4b") is None
    kaggle = registry_for("kaggle")
    assert {c.model_id for c in kaggle.list("text_to_2d", "character")} >= set(MEASURED)
    assert kaggle.list("text_to_2d", "weapon") == default_registry().list("text_to_2d", "weapon")


def test_every_recipe_pins_a_full_commit_and_the_benchmark_settings():
    for model_id, recipe in RECIPES.items():
        assert len(recipe["revision"]) == 40 and int(recipe["revision"], 16) >= 0, model_id
        assert "model_index.json" in recipe["allow_patterns"]
    assert (RECIPES["animagine-xl-4"]["steps"], RECIPES["animagine-xl-4"]["guidance"]) == (28, 5.0)
    assert (RECIPES["flux2-klein-4b"]["steps"], RECIPES["flux2-klein-4b"]["guidance"]) == (4, 1.0)
    assert (RECIPES["moss-image-sft"]["steps"], RECIPES["moss-image-sft"]["guidance"]) == (50, 3.0)
    assert RECIPES["moss-image-sft"]["extra"] == {"uncond_skip_layers": [22]}
    assert PINS == ["diffusers==0.42.1", "transformers==5.22.1", "accelerate==1.15.0"]
    assert set(RECIPES) == set(MEASURED)


# --- adapter ---------------------------------------------------------------------------------------------------


def test_adapter_needs_the_internet_and_writes_one_png():
    for model_id in MEASURED:
        a = adapter(model_id)
        assert a.requires_internet is True
        assert (Path(__file__).parents[2] / a.entrypoint).is_file()
        outputs = a.expected_outputs(generation(model_id))
        assert [(o.name, o.kind, o.format, o.required) for o in outputs] == [
            ("image.png", "image", "png", True)
        ]


def test_animagine_appends_quality_tags_and_merges_its_negative_list_without_duplicates():
    args = adapter("animagine-xl-4").build_arguments(
        generation("animagine-xl-4", "1girl, masterpiece, silver hair", negative_prompt="blurry, extra arms")
    )
    assert args["prompt"] == "1girl, masterpiece, silver hair, high score, great score, absurdres"
    assert args["negative_prompt"].startswith(ANIMAGINE_NEGATIVE)
    assert args["negative_prompt"].endswith(", extra arms")
    assert args["negative_prompt"].lower().count("blurry") == 1
    assert ANIMAGINE_QUALITY_TAGS.split(", ")[-1] in args["prompt"]


def test_klein_and_moss_send_the_prompt_unchanged():
    klein = adapter("flux2-klein-4b").build_arguments(generation("flux2-klein-4b", "  A knight in red  "))
    assert klein["prompt"] == "A knight in red" and klein["negative_prompt"] is None
    moss = adapter("moss-image-sft").build_arguments(
        generation("moss-image-sft", "A knight", negative_prompt="text")
    )
    assert moss["prompt"] == "A knight" and moss["negative_prompt"] == "text"


def test_arguments_carry_size_seed_recipe_and_pins():
    args = adapter("moss-image-sft").build_arguments(
        generation("moss-image-sft", seed=7, width=832, height=1216)
    )
    assert (args["width"], args["height"], args["seed"]) == (832, 1216, 7)
    assert args["recipe"] is RECIPES["moss-image-sft"] and args["pins"] == PINS
    assert (args["model_id"], args["asset_category"]) == ("moss-image-sft", "character")
    defaults = adapter("flux2-klein-4b").build_arguments(generation("flux2-klein-4b"))
    assert (defaults["width"], defaults["height"], defaults["seed"]) == (1024, 1024, None)


@pytest.mark.parametrize("size", sorted(SIZES))
def test_measured_sizes_pass_the_size_rule(size):
    width, height = size
    assert (
        adapter("flux2-klein-4b").validate_model_specific(
            create("flux2-klein-4b", width=width, height=height)
        )
        == []
    )


@pytest.mark.parametrize("size", [(832, 832), (1216, 1216), (1024, 1216), (832, None)])
def test_other_size_pairs_are_rejected_with_the_allowed_list(size):
    width, height = size
    options = {"width": width} if height is None else {"width": width, "height": height}
    errors = adapter("animagine-xl-4").validate_model_specific(create("animagine-xl-4", **options))
    assert [(e.code, e.field) for e in errors] == [("MODEL_OPTION_INVALID", "options.height")]
    assert errors[0].details["allowed"] == ["832x1216", "1024x1024", "1216x832"]


def test_size_rule_leaves_type_errors_to_the_option_checks():
    errors = adapter("animagine-xl-4").validate_model_specific(create("animagine-xl-4", width="wide"))
    assert errors == []


# --- remote entry (set-up only; rendering needs torch and a GPU) ------------------------------------------------


class _StopBeforeRender(Exception):
    pass


def test_remote_entry_imports_no_third_party_library_at_module_level():
    source = Path(remote_entry.__file__).read_text(encoding="utf-8")
    top_level = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    allowed = {
        "gc",
        "json",
        "math",
        "os",
        "random",
        "shutil",
        "subprocess",
        "sys",
        "time",
        "__future__",
        "pathlib",
    }
    assert {line.split()[1].split(".")[0] for line in top_level} <= allowed


def test_remote_entry_draws_a_seed_drops_tokens_and_pins_one_gpu(monkeypatch, tmp_path, capsys):
    seen: dict = {}
    monkeypatch.setenv("HF_TOKEN", "hf_should_never_reach_the_run")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    for name in ("HF_HUB_DISABLE_PROGRESS_BARS", "HF_HUB_DISABLE_TELEMETRY", "TOKENIZERS_PARALLELISM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(remote_entry, "_install", lambda pins, progress: seen.setdefault("pins", pins))
    monkeypatch.setattr(remote_entry, "_download", lambda recipe, progress: tmp_path)

    class FakeTorch:
        def __init__(self, key):
            seen["family"] = key
            self.device, self.dtype = "cuda:0", "torch.float16"

    def render(batch, folder, rt, progress):
        seen["args"], seen["folder"] = batch.items[0], folder
        raise _StopBeforeRender

    monkeypatch.setattr(remote_entry, "_Torch", FakeTorch)
    monkeypatch.setitem(remote_entry.FAMILIES, "flux2_klein", render)
    arguments = adapter("flux2-klein-4b").build_arguments(generation("flux2-klein-4b", "A knight"))
    with pytest.raises(_StopBeforeRender):
        remote_entry.main(arguments, tmp_path, tmp_path / "out", lambda *a: None)

    assert "HF_TOKEN" not in os.environ and os.environ["CUDA_VISIBLE_DEVICES"] == "0"
    assert seen["pins"] == PINS and seen["family"] == "flux2_klein" and seen["folder"] == tmp_path
    assert 0 <= seen["args"]["seed"] < 2**32 and arguments["seed"] is None  # drawn, caller's dict untouched
    log = capsys.readouterr().out
    assert f"seed {seen['args']['seed']}" in log and "Prompt sent to the model: A knight" in log
    assert "hf_should_never_reach_the_run" not in log


def test_remote_entry_keeps_an_explicit_seed(monkeypatch, tmp_path):
    seen: dict = {}
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(remote_entry, "_install", lambda pins, progress: None)
    monkeypatch.setattr(remote_entry, "_download", lambda recipe, progress: tmp_path)
    monkeypatch.setattr(
        remote_entry, "_Torch", lambda key: type("T", (), {"device": "cuda:0", "dtype": "f16"})()
    )

    def render(batch, folder, rt, progress):
        seen.update(batch.items[0])
        raise _StopBeforeRender

    monkeypatch.setitem(remote_entry.FAMILIES, "sdxl", render)
    arguments = adapter("animagine-xl-4").build_arguments(generation("animagine-xl-4", seed=1234))
    with pytest.raises(_StopBeforeRender):
        remote_entry.main(arguments, tmp_path, tmp_path / "out", lambda *a: None)
    assert seen["seed"] == 1234


def test_every_recipe_family_has_a_renderer():
    assert {r["family"] for r in RECIPES.values()} == set(remote_entry.FAMILIES)


def test_renderers_that_free_the_text_encoder_hold_no_closure_over_it():
    """Smoke run 2026-11-06: a nested ``encode(text, encoder=encoder)`` kept MOSS's 15.6 GiB encoder alive after
    ``del encoder``, and loading the image model ran out of GPU memory. Encoders are passed to module-level helpers."""
    import ast

    tree = ast.parse(Path(remote_entry.__file__).read_text(encoding="utf-8"))
    for function in (
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_klein", "_moss")
    ):
        nested = [
            n for n in ast.walk(function) if isinstance(n, ast.FunctionDef | ast.Lambda) and n is not function
        ]
        assert nested == [], function.name
        assert any(isinstance(n, ast.Delete) for n in ast.walk(function)), function.name
