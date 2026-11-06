"""Mock adapters: real PNG/GLB outputs, invocation shape, and output validation."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

import pytest

from models.adapters import ArtifactInvalidError
from models.adapters.mock_image_to_3d import remote_entry as i3d_entry
from models.adapters.mock_text_to_2d import remote_entry as t2d_entry
from models.adapters.validation import validate_glb, validate_glb_bytes, validate_png
from models.contracts import GenerationInput, GenerationRequest, utc_now
from models.registry import default_registry
from tests.conftest import image_bytes

JOB = "job_20261106T101500Z_a1b2c3"


def noop(*_):
    return None


def t2d_args(seed=42, **extra):
    return {
        "prompt": "Frost greatsword",
        "asset_category": "weapon",
        "model_id": "mock-t2d-basic",
        "width": 256,
        "height": 256,
        "seed": seed,
        "negative_prompt": None,
        "style_reference": None,
        **extra,
    }


def run_t2d(tmp_path: Path, name: str, **args) -> bytes:
    out = tmp_path / name
    t2d_entry.main(t2d_args(**args), tmp_path, out, noop)
    return (out / "image.png").read_bytes()


def test_mock_png_is_real_and_deterministic_for_a_seed(tmp_path):
    first, second = run_t2d(tmp_path, "a"), run_t2d(tmp_path, "b")
    assert first == second
    assert run_t2d(tmp_path, "c", seed=7) != first
    assert validate_png(tmp_path / "a" / "image.png") == (256, 256)


def test_mock_png_uses_the_style_reference(tmp_path):
    (tmp_path / "in_01_style_reference.png").write_bytes(image_bytes(64, 64, color=(0, 255, 0)))
    with_style = run_t2d(tmp_path, "s", style_reference="in_01_style_reference.png")
    assert with_style != run_t2d(tmp_path, "n")


def make_views(directory: Path, roles=("front", "side", "back")) -> dict[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    views = {}
    for i, role in enumerate(roles):
        name = f"in_{i + 1:02d}_{role}.png"
        (directory / name).write_bytes(image_bytes(512, 768, color=(60 * i, 100, 200)))
        views[role] = name
    return views


def test_mock_glb_is_valid_gltf2_with_embedded_texture(tmp_path):
    views = make_views(tmp_path / "in")
    i3d_entry.main(
        {
            "views": views,
            "details": [],
            "asset_category": "character",
            "texture_resolution": 1024,
            "seed": None,
        },
        tmp_path / "in",
        tmp_path / "out",
        noop,
    )
    document = validate_glb(tmp_path / "out" / "model.glb")
    assert document["asset"]["version"] == "2.0"
    assert document["images"][0]["mimeType"] == "image/png" and "uri" not in document["images"][0]
    assert document["accessors"][0]["count"] == 24 and document["accessors"][3]["count"] == 36
    assert validate_png(tmp_path / "out" / "preview.png") == (512, 512)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b"GLTF" + b[4:],
        lambda b: b[:4] + struct.pack("<I", 1) + b[8:],
        lambda b: b[:-8],
        lambda b: b[:30],
    ],
    ids=["magic", "version", "truncated", "header-only"],
)
def test_invalid_glb_is_rejected(tmp_path, mutate):
    views = make_views(tmp_path / "in", ("front",))
    i3d_entry.main(
        {"views": views, "details": [], "texture_resolution": 1024}, tmp_path / "in", tmp_path, noop
    )
    with pytest.raises(ValueError):
        validate_glb_bytes(mutate((tmp_path / "model.glb").read_bytes()))


def gen_request(model_id: str, inputs=(), options=None, output_format="glb") -> GenerationRequest:
    caps = default_registry().get(model_id)
    return GenerationRequest(
        contract_version="1.0",
        job_id=JOB,
        pipeline_type=caps.supported_pipeline_types[0],
        asset_category="character",
        model_id=model_id,
        prompt=None,
        inputs=list(inputs),
        options=options or {"seed": None},
        output_format=output_format,
        created_at=utc_now(),
    )


def gen_input(index: int, role: str) -> GenerationInput:
    return GenerationInput(
        input_id=f"in_{index:02d}",
        role=role,
        path=f"inputs/{JOB}/in_{index:02d}_{role}.png",
        mime_type="image/png",
        width=1024,
        height=1536,
        size_bytes=1,
        sha256="0" * 64,
    )


def test_build_invocation_matches_section_2_4():
    request = gen_request(
        "mock-i3d-multiview",
        [gen_input(1, "front"), gen_input(2, "side")],
        {"seed": None, "texture_resolution": 2048},
    )
    invocation = default_registry().adapter("mock-i3d-multiview").build_invocation(request)
    data = invocation.model_dump()
    assert data["entrypoint"] == "models/adapters/mock_image_to_3d/remote_entry.py"
    assert data["arguments"]["views"] == {"front": "in_01_front.png", "side": "in_02_side.png"}
    assert data["arguments"]["texture_resolution"] == 2048 and data["arguments"]["seed"] is None
    assert data["input_files"] == [f"inputs/{JOB}/in_01_front.png", f"inputs/{JOB}/in_02_side.png"]
    assert [(o["name"], o["required"]) for o in data["expected_outputs"]] == [
        ("model.glb", True),
        ("preview.png", False),
    ]
    assert data["resource_requirements"] == {
        "accelerator_kinds": ["gpu_cuda"],
        "multi_gpu": "optional",
        "minimum_gpu_vram_bytes": 12884901888,
        "estimated_runtime_seconds": 900,
    }


def test_collect_outputs_validates_and_numbers_artifacts(tmp_path):
    views = make_views(tmp_path / "in", ("front",))
    i3d_entry.main(
        {"views": views, "details": [], "texture_resolution": 1024}, tmp_path / "in", tmp_path / "o", noop
    )
    artifacts = (
        default_registry()
        .adapter("mock-i3d-single")
        .collect_outputs(gen_request("mock-i3d-single"), tmp_path / "o")
    )
    assert [(a.artifact_id, a.kind, a.is_primary) for a in artifacts] == [
        ("art_01", "model_3d", True),
        ("art_02", "preview", False),
    ]
    glb = artifacts[0]
    assert glb.mime_type == "model/gltf-binary" and glb.width is None
    assert glb.sha256 == hashlib.sha256((tmp_path / "o" / "model.glb").read_bytes()).hexdigest()


def test_collect_outputs_rejects_missing_or_corrupt_primary(tmp_path):
    adapter = default_registry().adapter("mock-i3d-single")
    (tmp_path / "o").mkdir()
    with pytest.raises(ArtifactInvalidError, match="missing"):
        adapter.collect_outputs(gen_request("mock-i3d-single"), tmp_path / "o")
    (tmp_path / "o" / "model.glb").write_bytes(b"glTF garbage")
    with pytest.raises(ArtifactInvalidError, match="not a valid GLB"):
        adapter.collect_outputs(gen_request("mock-i3d-single"), tmp_path / "o")


def test_invalid_optional_preview_is_skipped(tmp_path):
    views = make_views(tmp_path / "in", ("front",))
    i3d_entry.main(
        {"views": views, "details": [], "texture_resolution": 1024}, tmp_path / "in", tmp_path / "o", noop
    )
    (tmp_path / "o" / "preview.png").write_bytes(b"not a png")
    artifacts = (
        default_registry()
        .adapter("mock-i3d-single")
        .collect_outputs(gen_request("mock-i3d-single"), tmp_path / "o")
    )
    assert [a.kind for a in artifacts] == ["model_3d"]


def test_png_validator_rejects_other_formats(tmp_path):
    (tmp_path / "x.png").write_bytes(image_bytes(8, 8, "JPEG"))
    with pytest.raises(ValueError):
        validate_png(tmp_path / "x.png")
    (tmp_path / "y.png").write_text(json.dumps({"not": "png"}))
    with pytest.raises(ValueError):
        validate_png(tmp_path / "y.png")
