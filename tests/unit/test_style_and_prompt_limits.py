"""D-041 (7) and D-042: prompt limits, the remote token check and style images, offline.

The remote entry runs with fake ``transformers``/``diffusers`` modules and a fake torch runtime: no weights, no GPU.
"""

from __future__ import annotations

import contextlib
import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from models.adapters.diffusers_text_to_2d import DEFAULT_STYLE_STRENGTH, IP_ADAPTER, remote_entry
from models.contracts import CreateJobRequest, GenerationInput, GenerationRequest, utc_now
from models.registry import full_registry, validate_model_request
from tests.conftest import request_body

JOB = "job_20261106T101500Z_a1b2c3"


def caps(model_id):
    return full_registry().get(model_id)


def style_input(index: int = 1, width: int = 1024, height: int = 1024) -> GenerationInput:
    return GenerationInput(
        input_id=f"in_{index:02d}",
        role="style_reference",
        path=f"inputs/{JOB}/in_{index:02d}_style_reference.png",
        mime_type="image/png",
        width=width,
        height=height,
        size_bytes=1000,
        sha256="0" * 64,
    )


def generation(model_id: str, prompt: str = "1girl, knight", inputs=(), **options) -> GenerationRequest:
    return GenerationRequest(
        contract_version="1.0",
        job_id=JOB,
        pipeline_type="text_to_2d",
        asset_category="character",
        model_id=model_id,
        prompt=prompt,
        inputs=list(inputs),
        options=options,
        output_format="png",
        created_at=utc_now(),
    )


def create(model_id: str, *, inputs=(), prompt="1girl, knight", **options) -> CreateJobRequest:
    body = request_body(
        model_id=model_id,
        asset_category="character",
        prompt=prompt,
        inputs=list(inputs),
        options=options,
        compute={"profile_id": "default", "accelerator_id": "gpu_t4x2"},
    )
    return CreateJobRequest.model_validate(body)


# --- registry and validation ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_id,limit", [("animagine-xl-4", 10_000), ("moss-image-sft", 10_000), ("flux2-klein-4b", 8_192)]
)
def test_prompt_limits_per_model(model_id, limit):
    registry = full_registry()
    accepted = validate_model_request(create(model_id, prompt="a" * limit), registry, lambda _: None)
    assert "MODEL_PROMPT_TOO_LONG" not in [e.code for e in accepted.errors]
    rejected = validate_model_request(create(model_id, prompt="a" * (limit + 1)), registry, lambda _: None)
    assert "MODEL_PROMPT_TOO_LONG" in [e.code for e in rejected.errors]


def test_style_strength_without_a_style_image_is_refused():
    adapter = full_registry().adapter("animagine-xl-4")
    problems = adapter.validate_model_specific(create("animagine-xl-4", style_strength=0.5))
    assert [(p.code, p.field, p.details["reason"]) for p in problems] == [
        ("MODEL_OPTION_INVALID", "options.style_strength", "requires_style_reference")
    ]
    with_image = create(
        "animagine-xl-4", inputs=[{"upload_id": "upl_" + "0" * 32, "role": "style_reference"}]
    )
    assert (
        adapter.validate_model_specific(with_image.model_copy(update={"options": {"style_strength": 0.5}}))
        == []
    )


@pytest.mark.parametrize("images,measured,measured_with", [(1, 23, 1), (2, 43, 2), (3, 92, 4), (4, 92, 4)])
def test_klein_with_style_images_warns_with_a_measured_runtime(images, measured, measured_with):
    refs = [{"upload_id": "upl_" + f"{i}" * 32, "role": "style_reference"} for i in range(images)]
    items = (
        full_registry()
        .adapter("flux2-klein-4b")
        .validate_model_specific(create("flux2-klein-4b", inputs=refs))
    )
    assert [(i.code, i.severity) for i in items] == [("MODEL_RUNTIME_EXCEEDS_ESTIMATE", "warning")]
    assert items[0].details == {"estimated_seconds": 9, "measured_seconds": measured, "images": images}
    assert f"with {measured_with} image(s)" in items[0].message
    assert full_registry().adapter("flux2-klein-4b").validate_model_specific(create("flux2-klein-4b")) == []


def test_moss_stays_prompt_only():
    record = caps("moss-image-sft")
    assert record.inputs.max_images == 0 and record.inputs.supported_image_roles == []


# --- adapter arguments ------------------------------------------------------------------------------------------


def test_style_images_reach_the_run_only_when_present():
    adapter = full_registry().adapter("animagine-xl-4")
    plain = adapter.build_arguments(generation("animagine-xl-4"))
    assert not {"style_images", "style_strength", "ip_adapter"} & set(plain)  # prompt-only: exactly as before
    styled = adapter.build_arguments(generation("animagine-xl-4", inputs=[style_input(1), style_input(2)]))
    assert [s["file"] for s in styled["style_images"]] == [
        "in_01_style_reference.png",
        "in_02_style_reference.png",
    ]
    assert styled["style_strength"] == DEFAULT_STYLE_STRENGTH == 0.6
    assert styled["ip_adapter"] == IP_ADAPTER
    assert IP_ADAPTER["revision"] == "018e402774aeeddd60609b4ecdb7e298259dc729"
    assert all(p.endswith((".safetensors", "config.json")) for p in IP_ADAPTER["allow_patterns"])
    explicit = adapter.build_arguments(
        generation("animagine-xl-4", inputs=[style_input()], style_strength=0.3)
    )
    assert explicit["style_strength"] == 0.3
    klein = (
        full_registry()
        .adapter("flux2-klein-4b")
        .build_arguments(generation("flux2-klein-4b", inputs=[style_input()]))
    )
    assert klein["style_images"] and "ip_adapter" not in klein and "style_strength" not in klein
    invocation = adapter.build_invocation(generation("animagine-xl-4", inputs=[style_input()]))
    assert invocation.input_files == [f"inputs/{JOB}/in_01_style_reference.png"]  # via the job's dataset


# --- remote entry: token check, windows, references -----------------------------------------------------------


class FakeTokenizer:
    """One token per word; the chat template is the text itself."""

    def apply_chat_template(self, messages, **_):
        return messages[0]["content"]

    def __call__(self, text, **_):
        return types.SimpleNamespace(input_ids=text.split())


class FakeRuntime:
    def __init__(self):
        self.torch = types.SimpleNamespace(no_grad=contextlib.nullcontext, device=lambda name: name)
        self.device, self.dtype, self.cpu_test = "cuda:0", "float16", False

    def free(self):
        pass

    def generator(self, seed):
        return seed


@pytest.fixture
def fake_libs(monkeypatch, tmp_path):
    seen: dict = {"windows": [], "calls": [], "encoder_loads": 0}

    class Embeds:
        def to(self, device):
            return self

        def float(self):
            return self

        def isfinite(self):
            return types.SimpleNamespace(all=lambda: True)

    class Pipe:
        def to(self, device):
            return self

        def set_progress_bar_config(self, **_):
            pass

        def __call__(self, **kwargs):
            seen["calls"].append(kwargs)
            return types.SimpleNamespace(images=["pixels"])

    class Flux2KleinPipeline:
        @staticmethod
        def _get_qwen3_prompt_embeds(encoder, tokenizer, prompt, **kwargs):
            seen["windows"].append(kwargs["max_sequence_length"])
            return Embeds()

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            seen["pipe_loaded"] = True
            return Pipe()

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        types.SimpleNamespace(
            AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a, **k: FakeTokenizer())
        ),
    )
    monkeypatch.setitem(
        sys.modules, "diffusers", types.SimpleNamespace(Flux2KleinPipeline=Flux2KleinPipeline)
    )

    def text_encoder(folder, rt, max_gpu_gib=13):
        seen["encoder_loads"] += 1
        return object(), FakeTokenizer()

    monkeypatch.setattr(remote_entry, "_text_encoder", text_encoder)
    monkeypatch.setattr(remote_entry, "_check", lambda image: None)
    monkeypatch.setattr(remote_entry, "_save_png", lambda image, path: path.write_bytes(b"png"))
    return seen


def klein_batch(tmp_path, arguments):
    batch = remote_entry._Batch(arguments, tmp_path / "out", lambda *a: None)
    batch.input_dir = tmp_path
    return batch


def klein_arguments(prompt: str, inputs=()) -> dict:
    return (
        full_registry()
        .adapter("flux2-klein-4b")
        .build_arguments(generation("flux2-klein-4b", prompt, inputs))
    )


def test_klein_refuses_a_prompt_longer_than_its_window_before_any_model_loads(fake_libs, tmp_path):
    batch = klein_batch(tmp_path, klein_arguments("word " * 2049))
    remote_entry._klein(batch, tmp_path, FakeRuntime(), lambda *a: None)
    assert fake_libs["encoder_loads"] == 0 and "pipe_loaded" not in fake_libs
    with pytest.raises(remote_entry.PromptTooLong) as caught:
        batch.finish()
    assert caught.value.aas_code == "MODEL_PROMPT_TOO_LONG"
    assert caught.value.aas_details == {"tokens": 2049, "max_tokens": 2048}


@pytest.mark.parametrize("words,window", [(10, 512), (512, 512), (600, 1024), (1500, 2048), (2048, 2048)])
def test_klein_uses_the_smallest_measured_window_that_holds_the_prompt(fake_libs, tmp_path, words, window):
    batch = klein_batch(tmp_path, klein_arguments("word " * words))
    remote_entry._klein(batch, tmp_path, FakeRuntime(), lambda *a: None)
    batch.finish()
    assert fake_libs["windows"] == [window]


def test_klein_passes_reference_images_resized_as_flux2_does(fake_libs, tmp_path, capsys):
    Image.new("RGB", (2000, 1000), "red").save(tmp_path / "in_01_style_reference.png")
    Image.new("RGB", (512, 512), "blue").save(tmp_path / "in_02_style_reference.png")
    arguments = klein_arguments("a knight", [style_input(1, 2000, 1000), style_input(2, 512, 512)])
    batch = klein_batch(tmp_path, arguments)
    remote_entry._klein(batch, tmp_path, FakeRuntime(), lambda *a: None)
    batch.finish()
    images = fake_libs["calls"][0]["image"]
    assert [i.size for i in images] == [(1440, 720), (512, 512)]
    assert all(w % 16 == 0 and h % 16 == 0 and w * h <= 1024 * 1024 for w, h in (i.size for i in images))
    log = capsys.readouterr().out
    assert "Style image in_01: 2000x1000 -> 1440x720 (FLUX.2 reference)" in log


def test_klein_without_style_images_calls_the_pipeline_exactly_as_before(fake_libs, tmp_path):
    batch = klein_batch(tmp_path, klein_arguments("a knight"))
    remote_entry._klein(batch, tmp_path, FakeRuntime(), lambda *a: None)
    assert "image" not in fake_libs["calls"][0]


def test_a_batch_task_with_a_too_long_prompt_fails_alone_with_its_reason(fake_libs, tmp_path):
    adapter = full_registry().adapter("flux2-klein-4b")
    base = generation("flux2-klein-4b").model_dump()
    size = {"width": 1024, "height": 1024}
    base.update(
        prompt=None,
        time_budget_seconds=3600,
        tasks=[
            {"task_id": "front_01", "prompt": "word " * 3000, "options": {"seed": 1, **size}},
            {"task_id": "side_01", "prompt": "a knight", "options": {"seed": 2, **size}},
        ],
    )
    request = GenerationRequest.model_validate(base)
    batch = klein_batch(tmp_path, adapter.build_batch_arguments(request))
    remote_entry._klein(batch, tmp_path, FakeRuntime(), lambda *a: None)
    batch.finish()
    rows = json.loads((tmp_path / "out" / remote_entry.TASK_RESULTS_FILE).read_text(encoding="utf-8"))[
        "tasks"
    ]
    by_id = {row["task_id"]: row for row in rows}
    assert (
        by_id["front_01"]["status"] == "failed" and by_id["front_01"]["error"]["reason"] == "prompt_too_long"
    )
    assert by_id["side_01"]["status"] == "succeeded"
    report = adapter.task_report(request, tmp_path / "out")
    assert report["front_01"]["reason"] == "prompt_too_long"


def test_moss_refuses_a_prompt_longer_than_4096_tokens_before_its_encoder_loads(
    fake_libs, tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "diffusers", types.SimpleNamespace(AutoencoderKLFlux2=object))
    arguments = (
        full_registry()
        .adapter("moss-image-sft")
        .build_arguments(generation("moss-image-sft", "word " * 4097))
    )
    batch = klein_batch(tmp_path, arguments)
    remote_entry._moss(batch, tmp_path, FakeRuntime(), lambda *a: None)
    assert fake_libs["encoder_loads"] == 0
    with pytest.raises(remote_entry.PromptTooLong) as caught:
        batch.finish()
    assert caught.value.aas_details["max_tokens"] == 4096


def test_no_path_truncates_a_prompt_silently():
    source = Path(remote_entry.__file__).read_text(encoding="utf-8")
    assert "truncation=True" not in source
    assert "max_sequence_length=512" not in source


def test_a_group_member_uses_the_gpu_its_runner_names(monkeypatch, tmp_path):
    monkeypatch.setenv("AAS_GPU_INDEX", "1")
    monkeypatch.setattr(remote_entry, "_install", lambda pins, progress: None)
    monkeypatch.setattr(remote_entry, "_download", lambda recipe, progress: tmp_path)

    class Stop(Exception):
        pass

    def render(*args):
        raise Stop

    monkeypatch.setattr(remote_entry, "_Torch", lambda key: FakeRuntime())
    monkeypatch.setitem(remote_entry.FAMILIES, "flux2_klein", render)
    with pytest.raises(Stop):
        remote_entry.main(klein_arguments("a knight"), tmp_path, tmp_path / "out", lambda *a: None)
    import os

    assert os.environ["CUDA_VISIBLE_DEVICES"] == "1"


def test_animagine_style_uses_the_style_block_and_moves_the_encoder_off_the_gpu(
    monkeypatch, tmp_path, capsys
):
    Image.new("RGB", (800, 600), "green").save(tmp_path / "in_01_style_reference.png")
    seen: dict = {}

    class Encoder:
        def to(self, device):
            seen["encoder_device"] = device

    class Pipe:
        image_encoder = Encoder()
        feature_extractor = types.SimpleNamespace(crop_size={"height": 224, "width": 224})

        def load_ip_adapter(self, folder, **kwargs):
            seen["load"] = kwargs

        def set_ip_adapter_scale(self, scale):
            seen["scale"] = scale

        def prepare_ip_adapter_image_embeds(self, images, embeds, device, count, cfg):
            seen["images"] = [[i.size for i in group] for group in images]
            return ["embeds"]

    monkeypatch.setattr(remote_entry, "_download", lambda recipe, progress: tmp_path / recipe["key"])
    arguments = (
        full_registry()
        .adapter("animagine-xl-4")
        .build_arguments(generation("animagine-xl-4", inputs=[style_input(1, 800, 600)], style_strength=0.4))
    )
    batch = klein_batch(tmp_path, arguments)
    extra = remote_entry._sdxl_style(Pipe(), batch, FakeRuntime(), lambda *a: None)
    assert extra == {"ip_adapter_image_embeds": ["embeds"]}
    assert seen["scale"] == {"up": {"block_0": [0.0, 0.4, 0.0]}}  # InstantStyle: style block only
    assert seen["load"] == {
        "subfolder": "sdxl_models",
        "weight_name": "ip-adapter_sdxl.safetensors",
        "image_encoder_folder": "image_encoder",
    }
    assert seen["images"] == [[(800, 600)]] and seen["encoder_device"] == "cpu"
    assert "Style image in_01: 800x600 -> 224x224" in capsys.readouterr().out


def test_group_processes_install_their_pins_one_after_the_other(monkeypatch, tmp_path):
    """Live run 2026-11-07: two concurrent pip installs in one session collided; a file lock serializes them."""
    events = []
    fake = types.SimpleNamespace(
        LOCK_EX=2, LOCK_UN=8, flock=lambda handle, op: events.append("lock" if op == 2 else "unlock")
    )
    monkeypatch.setitem(sys.modules, "fcntl", fake)
    monkeypatch.setattr(remote_entry, "INSTALL_LOCK", tmp_path / "pip.lock")

    def run(args, **kwargs):
        events.append("pip")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(remote_entry.subprocess, "run", run)
    remote_entry._install(["diffusers==0.42.1"], lambda *a: None)
    assert events == ["lock", "pip", "unlock"]
