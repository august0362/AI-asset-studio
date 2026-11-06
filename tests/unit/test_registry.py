"""Capability registry (CONTRACTS §2.1 rules, §2.2 table)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.contracts import ModelCapabilities
from models.registry import MOCK_CAPABILITIES, ModelRegistry, default_registry

GIB = 1024**3
TABLE = {  # model_id: (pipeline, categories, prompt, (min, max), required roles, accelerators, vram, runtime, avail)
    "mock-t2d-basic": ("text_to_2d", 4, "required", (0, 0), [], ["cpu", "gpu_cuda"], None, 30, "available"),
    "mock-t2d-styleref": ("text_to_2d", 4, "required", (0, 1), [], ["gpu_cuda"], None, 60, "experimental"),
    "mock-i3d-single": (
        "image_to_3d",
        3,
        "unsupported",
        (1, 1),
        ["front"],
        ["gpu_cuda"],
        None,
        120,
        "available",
    ),
    "mock-i3d-multiview": (
        "image_to_3d",
        2,
        "unsupported",
        (2, 4),
        ["front", "side"],
        ["gpu_cuda"],
        12 * GIB,
        900,
        "available",
    ),
    "mock-t3d-basic": ("text_to_3d", 4, "required", (0, 0), [], ["gpu_cuda"], None, None, "planned"),
}


def test_registry_has_exactly_the_five_documented_mocks():
    assert [m.model_id for m in default_registry().list()] == list(TABLE)


@pytest.mark.parametrize("model_id", list(TABLE))
def test_mock_records_match_the_contract_table(model_id):
    caps = default_registry().get(model_id)
    pipeline, n_categories, prompt, (lo, hi), required, accels, vram, runtime, availability = TABLE[model_id]
    assert caps.is_mock
    assert caps.supported_pipeline_types == [pipeline]
    assert len(caps.supported_asset_categories) == n_categories
    assert caps.inputs.prompt_supported is (prompt != "unsupported")
    if prompt == "required":
        assert caps.inputs.prompt_required and caps.inputs.prompt_max_length == 1000
    assert (caps.inputs.min_images, caps.inputs.max_images) == (lo, hi)
    assert caps.inputs.required_image_roles == required
    assert caps.runtime.supported_accelerators == accels
    assert caps.runtime.minimum_gpu_vram_bytes == vram
    assert caps.runtime.estimated_runtime_seconds == runtime
    assert caps.availability == availability


def test_mock_options_match_the_contract():
    registry = default_registry()
    assert list(registry.get("mock-t2d-basic").options_schema) == [
        "seed",
        "width",
        "height",
        "negative_prompt",
    ]
    assert registry.get("mock-t2d-basic").options_schema["width"].enum == [512, 768, 1024]
    assert list(registry.get("mock-i3d-multiview").options_schema) == ["seed", "texture_resolution"]
    for model_id in ("mock-t2d-styleref", "mock-i3d-single", "mock-t3d-basic"):
        assert list(registry.get(model_id).options_schema) == ["seed"]


def _not_applicable(caps: ModelCapabilities, path: str) -> bool:
    inputs = caps.inputs
    if path == "inputs.prompt_max_length":
        return not inputs.prompt_supported
    if path.startswith("inputs.") and inputs.max_images == 0:
        return True
    if path.startswith("inputs.m") and "image_" in path:  # dimension fields: null means "no constraint"
        return True
    if path == "runtime.minimum_gpu_vram_bytes":
        return "cpu" in caps.runtime.supported_accelerators  # a CPU-capable model has no VRAM minimum
    return False


@pytest.mark.parametrize("caps", MOCK_CAPABILITIES, ids=lambda c: c.model_id)
def test_null_requirements_are_listed_as_unknown_or_not_applicable(caps):
    """§2.1: a requirement may be null only when listed in unknown_requirements or not applicable."""
    data = caps.model_dump()
    for section in ("inputs", "runtime"):
        for key, value in data[section].items():
            path = f"{section}.{key}"
            if value is None:
                assert path in caps.unknown_requirements or _not_applicable(caps, path), path
    for path in caps.unknown_requirements:
        section, key = path.split(".")
        assert data[section][key] is None, f"{path} is listed as unknown but has a value"


def test_job_accepting_models_have_adapters_and_planned_ones_may_not():
    registry = default_registry()
    for caps in registry.list():
        if caps.accepts_jobs:
            assert registry.adapter(caps.model_id).capabilities() is caps


def test_filtering_by_pipeline_and_category():
    registry = default_registry()
    assert [m.model_id for m in registry.list("image_to_3d", "weapon")] == ["mock-i3d-single"]
    assert {m.model_id for m in registry.list(asset_category="skill_effect")} == {
        "mock-t2d-basic",
        "mock-t2d-styleref",
        "mock-t3d-basic",
    }


def test_duplicate_ids_and_missing_adapters_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        ModelRegistry([MOCK_CAPABILITIES[0], MOCK_CAPABILITIES[0]])
    with pytest.raises(ValueError, match="adapter"):
        ModelRegistry([MOCK_CAPABILITIES[0]], adapters={})


@pytest.mark.parametrize(
    "patch",
    [
        {"prompt_supported": False, "prompt_required": True, "prompt_max_length": None},
        {"min_images": 3, "max_images": 2},
        {"max_images": 9},
        {"required_image_roles": ["three_quarter"]},
    ],
)
def test_capability_rules_are_enforced(patch):
    data = default_registry().get("mock-i3d-multiview").model_dump()
    data["inputs"].update(patch)
    with pytest.raises(ValidationError):
        ModelCapabilities.model_validate(data)


def test_unknown_fields_in_capabilities_are_rejected():
    data = default_registry().get("mock-i3d-single").model_dump()
    data["gpu_name"] = "Tesla T4"  # a model never names Kaggle hardware
    with pytest.raises(ValidationError):
        ModelCapabilities.model_validate(data)
