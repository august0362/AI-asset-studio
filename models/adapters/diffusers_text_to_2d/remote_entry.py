"""Remote entrypoint for the real Text→2D models (DECISIONS D-034). Runs only inside the Kaggle notebook.

The runner calls ``main(arguments, input_dir, output_dir, progress)``. Output: ``image.png`` for a normal job; for a
batch job (``arguments["tasks"]``, CONTRACTS §13.9) one ``task_<task_id>.png`` per task plus ``task_results.json``.

Each job installs the pinned libraries, downloads the pinned, ungated weights (internet on, D-032), **loads the model
once**, renders every image on one T4 in fp16 and frees everything. A batch encodes all its prompts first, then
renders the tasks in order; a task that fails is recorded and the next one starts; no task starts once the deadline
is near. One ``MODEL_LOAD <model_id> <revision>`` line is printed per load. The settings are the ones measured in the
M4 benchmark:

* ``sdxl`` (Animagine XL 4.0): prompts longer than CLIP's 77 tokens are encoded in 75-token chunks that are
  concatenated, so nothing after token 75 is dropped.
* ``flux2_klein`` and ``moss``: the text encoder runs first and is freed before the image model loads, so one 15 GiB
  T4 is enough. MOSS's 9B encoder does not fit one T4 and is split between the GPU and host RAM.

Prompts are never truncated (CONTRACTS §14.8): before any model loads, each prompt is tokenized with the model's own
tokenizer. A prompt longer than the encoder window (klein 2 048 Qwen3 tokens, MOSS 4 096) fails that image with
``MODEL_PROMPT_TOO_LONG`` (a batch task with reason ``prompt_too_long``). klein uses the smallest measured window
(512, 1 024 or 2 048) that holds the prompt, so short prompts render exactly as benchmarked.

Style images (CONTRACTS §14.9) come from the job's input folder. Animagine: the pinned IP-Adapter, acting on the style
block only (InstantStyle); the images are encoded once, then the image encoder leaves the GPU (measured in G.0: 12.3
GiB peak instead of 14.3). klein: the images are passed as reference images. The size each image was resized to is
logged. In a run group the runner sets ``AAS_GPU_INDEX`` so each process uses its own T4.

Third-party imports happen inside functions: this file is imported locally only by tests, which never call them.
``AAS_ENTRY_DEVICE=cpu`` (test hook) runs the same code on the CPU in fp32 (bf16 for MOSS) for code checks.
"""

from __future__ import annotations

import gc
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

MODEL_ROOT = Path("/tmp/aas_models")  # noqa: S108 - scratch disk of the ephemeral notebook
TASK_RESULTS_FILE = "task_results.json"
KLEIN_WINDOWS = (
    512,
    1024,
    2048,
)  # Qwen3 token windows that ran in G.0; 2 048 read a 1 493-token prompt in full
MOSS_MAX_TOKENS = 4096
KLEIN_REFERENCE_AREA = 1024 * 1024  # FLUX.2 resizes larger reference images to this area


class PromptTooLong(Exception):
    """Reported by the runner as ``MODEL_PROMPT_TOO_LONG`` with ``{tokens, max_tokens}`` (CONTRACTS §14.8)."""

    aas_code = "MODEL_PROMPT_TOO_LONG"
    aas_reason = "prompt_too_long"

    def __init__(self, tokens: int, max_tokens: int) -> None:
        super().__init__(f"The prompt has {tokens} tokens; this model reads at most {max_tokens}.")
        self.aas_details = {"tokens": tokens, "max_tokens": max_tokens}


def _log(message: str) -> None:
    print(message, flush=True)


INSTALL_LOCK = Path("/tmp/aas_pip.lock")  # noqa: S108 - shared by the processes of one notebook session


def _install(pins: list[str], progress) -> None:
    """In a run group both processes install the same pins; concurrent pip runs collide (live run 2026-11-07:
    ``OSError ... /usr/local/bin/diffusers-cli``). An exclusive file lock serializes them; the second finds the
    packages already installed."""
    progress("setup", 2, "Installing " + " ".join(pins))
    started = time.time()
    with _install_lock():
        waited = time.time() - started
        done = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", *pins], capture_output=True, text=True, check=False
        )
    if done.returncode != 0:
        raise RuntimeError("pip install failed: " + (done.stdout + done.stderr)[-400:])
    note = f" (waited {waited:.0f} s for the other process)" if waited >= 1 else ""
    _log(f"Installed {' '.join(pins)} in {time.time() - started:.0f} s{note}")


class _install_lock:
    def __enter__(self):
        try:
            import fcntl  # Linux (the notebook); absent on Windows, where tests never install anything
        except ImportError:
            self.handle = None
            return self
        self.handle = INSTALL_LOCK.open("w")
        fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc) -> None:
        if self.handle is not None:
            import fcntl

            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()


def _download(recipe: dict, progress) -> Path:
    from huggingface_hub import snapshot_download

    progress("setup", 10, f"Downloading {recipe['repo']} @ {recipe['revision'][:12]}")
    target = MODEL_ROOT / recipe["key"]
    started = time.time()
    snapshot_download(
        recipe["repo"], revision=recipe["revision"], allow_patterns=recipe["allow_patterns"], local_dir=target
    )
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    _log(f"Downloaded {size / 1e9:.1f} GB in {time.time() - started:.0f} s")
    return target


class _Torch:
    """Device and dtype for this run (fp16 on the GPU; never bf16 on the T4)."""

    def __init__(self, key: str) -> None:
        import torch

        self.torch = torch
        self.cpu_test = os.environ.get("AAS_ENTRY_DEVICE") == "cpu"
        if self.cpu_test:
            self.device = torch.device("cpu")
            self.dtype = torch.bfloat16 if key == "moss" else torch.float32
        else:
            if not torch.cuda.is_available():
                raise RuntimeError("No CUDA GPU is visible in this session.")
            self.device = torch.device("cuda:0")
            self.dtype = torch.float16

    def free(self) -> None:
        gc.collect()
        if not self.cpu_test:
            self.torch.cuda.empty_cache()

    def generator(self, seed: int):
        return self.torch.Generator("cpu").manual_seed(seed)


def _check(image) -> None:
    import numpy as np

    if not np.isfinite(image).all():
        raise RuntimeError("The model produced non-finite pixels (fp16 overflow).")
    if float(image.std()) < 0.01:
        raise RuntimeError("The model produced a blank image.")


def _save_png(image, path: Path) -> None:
    import numpy as np
    from PIL import Image

    pixels = (np.clip(image, 0, 1) * 255).round().astype(np.uint8)
    Image.fromarray(pixels).save(path, format="PNG")


class _Batch:
    """The images of one job: every task of a batch, or the single image of a normal job.

    A renderer asks it what to render next (``pending``), reports each result (``done`` / ``failed``) and announces
    the model load (``model_loaded``). Each PNG and the task results are written as soon as a task ends, so a
    timeout never loses a finished image.
    """

    def __init__(self, arguments: dict, output_dir: Path, progress) -> None:
        self.model_id = arguments["model_id"]
        self.recipe = arguments["recipe"]
        self.is_batch = "tasks" in arguments
        if self.is_batch:
            items = [dict(task) for task in arguments["tasks"]]
        else:
            fields = ("prompt", "negative_prompt", "width", "height", "seed")
            items = [{"task_id": None, "output": "image.png", **{k: arguments[k] for k in fields}}]
        for index, item in enumerate(items):
            item["index"] = index
            if item.get("seed") is None:
                item["seed"] = random.SystemRandom().randrange(2**32)
        self.items = items
        self.output_dir = output_dir
        self.progress = progress
        self.deadline = arguments.get("deadline_seconds") if self.is_batch else None
        self.started = time.monotonic()
        self.style = list(arguments.get("style_images") or [])  # never set for a batch (§14.9)
        self.style_strength = arguments.get("style_strength")
        self.ip_adapter = arguments.get("ip_adapter")
        self.input_dir: Path | None = None
        self.results: dict[int, dict] = {}
        self.errors: dict[int, Exception] = {}
        self.loads = 0
        self._last = 0.0
        self._task_started = 0.0

    def label(self, item: dict) -> str:
        return f"Task {item['task_id']}" if self.is_batch else "Image"

    def model_loaded(self) -> None:
        self.loads += 1
        _log(f"MODEL_LOAD {self.model_id} {self.recipe['revision']}")

    def pending(self):
        """Yields the items still to render, in order. Stops at the deadline and marks the rest ``not_run``."""
        for item in self.items:
            if item["index"] in self.results:
                continue  # already failed, for example while its prompt was encoded
            elapsed = time.monotonic() - self.started
            if self.deadline is not None and elapsed + self._last > self.deadline:
                rest = [i for i in self.items if i["index"] not in self.results]
                for other in rest:
                    self._record(
                        other,
                        "not_run",
                        None,
                        "The job's time budget ran out before this task started.",
                        "deadline",
                    )
                _log(f"Deadline reached after {elapsed:.0f} s; {len(rest)} task(s) not run.")
                return
            share = round(45 * len(self.results) / len(self.items))
            self.progress("inference", 50 + share, f"{self.label(item)}: rendering")
            self._task_started = time.monotonic()
            yield item

    def done(self, item: dict, image) -> None:
        try:
            _check(image)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            _save_png(image, self.output_dir / item["output"])
        except Exception as exc:
            self.failed(item, exc)
            return
        self._last = time.monotonic() - self._task_started
        self._record(item, "succeeded", round(self._last, 1), None)
        _log(f"{self.label(item)} rendered in {self._last:.1f} s")

    def failed(self, item: dict, exc: Exception) -> None:
        if self._task_started:
            self._last = time.monotonic() - self._task_started
        message = f"{exc.__class__.__name__}: {exc}"[:500]
        self.errors[item["index"]] = exc
        self._record(item, "failed", None, message, getattr(exc, "aas_reason", None))
        _log(f"{self.label(item)} failed: {message}")

    def _record(
        self, item: dict, status: str, seconds, message: str | None, reason: str | None = None
    ) -> None:
        self.results[item["index"]] = {
            "task_id": item["task_id"],
            "status": status,
            "seed": item["seed"],
            "seconds": seconds,
            "error": None if message is None else {"message": message, "reason": reason},
        }
        if not self.is_batch:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        rows = [self.results[i["index"]] for i in self.items if i["index"] in self.results]
        temp = self.output_dir / (TASK_RESULTS_FILE + ".tmp")
        temp.write_text(json.dumps({"v": 1, "tasks": rows}, indent=2), encoding="utf-8")
        os.replace(temp, self.output_dir / TASK_RESULTS_FILE)

    def finish(self) -> None:
        """A normal job fails with its image's error; a batch fails only if no task succeeded."""
        for item in self.items:  # a task the renderer never reached is reported, never dropped
            if item["index"] not in self.results:
                self._record(item, "failed", None, "The renderer stopped before this task.")
        succeeded = sum(1 for r in self.results.values() if r["status"] == "succeeded")
        if not self.is_batch:
            if succeeded == 0:
                raise self.errors.get(0) or RuntimeError("No image was produced.")
            return
        _log(
            f"Batch finished: {succeeded} of {len(self.items)} task(s) succeeded; {self.loads} model load(s)."
        )
        if succeeded == 0:
            raise RuntimeError("No task of this batch succeeded.")


# --- SDXL family (Animagine XL 4.0) ---------------------------------------------------------------------------


def _sdxl(batch: _Batch, folder: Path, rt: _Torch, progress) -> None:
    from diffusers import EulerAncestralDiscreteScheduler, StableDiffusionXLPipeline

    torch, recipe = rt.torch, batch.recipe
    progress("inference", 30, "Loading the pipeline")
    pipe = StableDiffusionXLPipeline.from_pretrained(folder, torch_dtype=rt.dtype, use_safetensors=True)
    if recipe["scheduler"] == "euler_ancestral":
        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
    pipe.to(rt.device)
    pipe.set_progress_bar_config(disable=True)
    batch.model_loaded()
    style = _sdxl_style(pipe, batch, rt, progress) if batch.style else {}

    toks, encs = [pipe.tokenizer, pipe.tokenizer_2], [pipe.text_encoder, pipe.text_encoder_2]

    def ids(tok, text):
        # verbose=False: the "longer than 77" warning does not apply, the ids are encoded in 75-token chunks
        return tok(text, truncation=False, add_special_tokens=False, verbose=False).input_ids

    def run(tok, enc, token_ids, chunks):
        hidden, pooled = [], None
        for c in range(chunks):
            row = [tok.bos_token_id, *token_ids[c * 75 : (c + 1) * 75], tok.eos_token_id]
            row += [tok.pad_token_id] * (77 - len(row))
            out = enc(torch.tensor([row], device=rt.device), output_hidden_states=True)
            hidden.append(out.hidden_states[-2])
            pooled = out[0] if pooled is None else pooled
        return torch.cat(hidden, 1), pooled

    for item in batch.pending():
        try:
            pos = [ids(t, item["prompt"]) for t in toks]
            neg = [ids(t, item["negative_prompt"] or "") for t in toks]
            chunks = max(1, math.ceil(max(len(i) for i in pos + neg) / 75))
            _log(f"{batch.label(item)}: {len(pos[0])} CLIP tokens, encoded in {chunks} window(s) of 75")
            with torch.no_grad():
                pe1, _ = run(toks[0], encs[0], pos[0], chunks)
                pe2, pooled = run(toks[1], encs[1], pos[1], chunks)
                ne1, _ = run(toks[0], encs[0], neg[0], chunks)
                ne2, npooled = run(toks[1], encs[1], neg[1], chunks)
                out = pipe(
                    prompt_embeds=torch.cat([pe1, pe2], -1),
                    pooled_prompt_embeds=pooled,
                    negative_prompt_embeds=torch.cat([ne1, ne2], -1),
                    negative_pooled_prompt_embeds=npooled,
                    width=item["width"],
                    height=item["height"],
                    num_inference_steps=recipe["steps"],
                    guidance_scale=recipe["guidance"],
                    generator=rt.generator(item["seed"]),
                    output_type="np",
                    **style,
                )
            batch.done(item, out.images[0])
        except Exception as exc:
            batch.failed(item, exc)


def _style_images(batch: _Batch) -> list[tuple[dict, object]]:
    from PIL import Image

    images = []
    for entry in batch.style:
        with Image.open(batch.input_dir / entry["file"]) as image:
            images.append((entry, image.convert("RGB")))
    return images


def _sdxl_style(pipe, batch: _Batch, rt: _Torch, progress) -> dict:
    """IP-Adapter on the style block only; the images are encoded once and the encoder leaves the GPU."""
    ipa = batch.ip_adapter
    progress("inference", 35, f"Loading the IP-Adapter for {len(batch.style)} style image(s)")
    folder = _download(ipa, progress)
    pipe.load_ip_adapter(
        str(folder),
        subfolder=ipa["subfolder"],
        weight_name=ipa["weight_name"],
        image_encoder_folder=ipa["image_encoder_folder"],
    )
    strength = float(batch.style_strength)
    block = {
        k: {b: [strength if v else 0.0 for v in vs] for b, vs in d.items()}
        for k, d in ipa["style_block"].items()
    }
    pipe.set_ip_adapter_scale(block)
    crop = pipe.feature_extractor.crop_size
    images = _style_images(batch)
    for entry, image in images:
        _log(
            f"Style image {entry['input_id']}: {image.width}x{image.height} -> {crop['width']}x{crop['height']} "
            "(CLIP image processor: shorter side resized, centre crop)"
        )
    _log(f"IP-Adapter {ipa['repo']} @ {ipa['revision']}; style block only; strength {strength:g}")
    with rt.torch.no_grad():
        embeds = pipe.prepare_ip_adapter_image_embeds(
            [[image for _, image in images]], None, rt.device, 1, True
        )
    pipe.image_encoder.to("cpu")
    rt.free()
    return {"ip_adapter_image_embeds": embeds}


# --- text encoder first, image model second (FLUX.2 klein, MOSS-Image) ------------------------------------------


def _text_encoder(folder: Path, rt: _Torch, max_gpu_gib: int = 13):
    import transformers
    from transformers import AutoTokenizer

    index = json.loads((folder / "model_index.json").read_text(encoding="utf-8"))
    cls = getattr(transformers, index["text_encoder"][1])
    tokenizer = AutoTokenizer.from_pretrained(folder / "tokenizer")
    if rt.cpu_test:
        return cls.from_pretrained(folder / "text_encoder", dtype=rt.dtype).eval(), tokenizer
    size = sum(f.stat().st_size for f in (folder / "text_encoder").glob("*.safetensors"))
    if size < (max_gpu_gib - 1) * 2**30:
        return cls.from_pretrained(folder / "text_encoder", dtype=rt.dtype).to(rt.device).eval(), tokenizer
    _log(
        f"Text encoder ({size / 2**30:.1f} GiB) is split: {max_gpu_gib} GiB on the GPU, the rest in host RAM"
    )
    model = cls.from_pretrained(
        folder / "text_encoder",
        dtype=rt.dtype,
        device_map="auto",
        max_memory={0: f"{max_gpu_gib}GiB", "cpu": "40GiB"},
    )
    return model.eval(), tokenizer


def _finite(*tensors) -> None:
    for tensor in tensors:
        if not bool(tensor.float().isfinite().all()):
            raise RuntimeError("The text encoder produced non-finite values (fp16 overflow).")


def _klein(batch: _Batch, folder: Path, rt: _Torch, progress) -> None:
    from diffusers import Flux2KleinPipeline
    from transformers import AutoTokenizer

    torch, recipe = rt.torch, batch.recipe
    tokenizer = AutoTokenizer.from_pretrained(folder / "tokenizer")
    windows = {}
    for item in batch.items:  # before any model loads (§14.8)
        text = tokenizer.apply_chat_template(
            [{"role": "user", "content": item["prompt"]}],
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        tokens = len(tokenizer(text).input_ids)
        window = next((w for w in KLEIN_WINDOWS if tokens <= w), None)
        if window is None:
            batch.failed(item, PromptTooLong(tokens, KLEIN_WINDOWS[-1]))
            continue
        windows[item["index"]] = window
        _log(f"{batch.label(item)}: {tokens} Qwen3 tokens, window {window}")
    if not windows:
        return
    progress("inference", 30, f"Encoding {len(windows)} prompt(s)")
    encoder, tokenizer = _text_encoder(folder, rt)
    embeds = {}
    for item in batch.items:
        if item["index"] not in windows:
            continue
        try:
            with torch.no_grad():
                value = Flux2KleinPipeline._get_qwen3_prompt_embeds(
                    encoder,
                    tokenizer,
                    item["prompt"],
                    dtype=rt.dtype,
                    device=torch.device("cpu"),
                    max_sequence_length=windows[item["index"]],
                )
            _finite(value)
            embeds[item["index"]] = value
        except Exception as exc:
            batch.failed(item, exc)
    del encoder
    rt.free()
    references = _klein_references(batch) if batch.style else None
    progress("inference", 45, "Loading the image model")
    pipe = Flux2KleinPipeline.from_pretrained(folder, text_encoder=None, tokenizer=None, torch_dtype=rt.dtype)
    pipe.to(rt.device)
    pipe.set_progress_bar_config(disable=True)
    batch.model_loaded()
    for item in batch.pending():
        try:
            with torch.no_grad():
                extra = {"image": references} if references else {}
                out = pipe(
                    prompt_embeds=embeds[item["index"]].to(rt.device),
                    **extra,
                    width=item["width"],
                    height=item["height"],
                    num_inference_steps=recipe["steps"],
                    guidance_scale=recipe["guidance"],
                    generator=rt.generator(item["seed"]),
                    output_type="np",
                )
            batch.done(item, out.images[0])
        except Exception as exc:
            batch.failed(item, exc)


def _klein_references(batch: _Batch) -> list:
    """Reference images as FLUX.2 prepares them: at most 1 MP, both sides a multiple of 16 (logged per image)."""
    from PIL import Image

    prepared = []
    for entry, image in _style_images(batch):
        width, height = image.size
        if width * height > KLEIN_REFERENCE_AREA:
            scale = math.sqrt(KLEIN_REFERENCE_AREA / (width * height))
            width, height = int(width * scale), int(height * scale)
        width, height = max(16, width // 16 * 16), max(16, height // 16 * 16)
        _log(
            f"Style image {entry['input_id']}: {image.width}x{image.height} -> {width}x{height} (FLUX.2 reference)"
        )
        prepared.append(image.resize((width, height), Image.Resampling.LANCZOS))
    return prepared


def _moss_format(tokenizer, text: str) -> str:
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": text}],
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )


def _moss_encode(encoder, tokenizer, text: str, rt: _Torch):
    """One prompt → (embeddings, mask) on the CPU. A plain function, not a closure: a closure (or a default
    argument) would keep the 15.6 GiB encoder alive after ``del`` and the image model would not fit."""
    inputs = tokenizer(_moss_format(tokenizer, text), return_tensors="pt").to(
        rt.device
    )  # checked: never truncated
    row = encoder(**inputs, use_cache=False, return_dict=True).last_hidden_state[0]
    return row[None].to("cpu"), rt.torch.ones(1, row.shape[0], dtype=rt.torch.bool)


def _moss(batch: _Batch, folder: Path, rt: _Torch, progress) -> None:
    import importlib

    from diffusers import AutoencoderKLFlux2
    from transformers import AutoTokenizer

    torch, recipe = rt.torch, batch.recipe
    tokenizer = AutoTokenizer.from_pretrained(folder / "tokenizer")
    for item in batch.items:  # before any model loads (§14.8)
        tokens = max(
            len(tokenizer(_moss_format(tokenizer, text)).input_ids)
            for text in (item["prompt"], item["negative_prompt"] or "")
        )
        if tokens > MOSS_MAX_TOKENS:
            batch.failed(item, PromptTooLong(tokens, MOSS_MAX_TOKENS))
    if len(batch.results) == len(batch.items):
        return
    progress("inference", 30, f"Encoding {len(batch.items) - len(batch.results)} prompt(s)")
    encoder, tokenizer = _text_encoder(folder, rt)
    encoded = {}
    for item in batch.items:
        if item["index"] in batch.results:
            continue
        try:
            with torch.no_grad():
                emb, mask = _moss_encode(encoder, tokenizer, item["prompt"], rt)
                neg, neg_mask = _moss_encode(encoder, tokenizer, item["negative_prompt"] or "", rt)
            _finite(emb, neg)
            encoded[item["index"]] = (emb, mask, neg, neg_mask)
        except Exception as exc:
            batch.failed(item, exc)
    del encoder
    rt.free()
    if not rt.cpu_test:
        _log(f"GPU memory after freeing the text encoder: {torch.cuda.memory_allocated() / 2**30:.1f} GiB")
    progress("inference", 40, "Loading the image model")
    sys.path.insert(0, str(folder))
    module = importlib.import_module(
        "pipeline_moss_image"
    )  # the repository's own file at the pinned revision
    transformer = module.MOSSImageTransformer.from_pretrained(
        folder / "transformer", torch_dtype=rt.dtype
    ).eval()
    scheduler = module.MOSSImageScheduler.from_pretrained(folder / "scheduler")
    vae = AutoencoderKLFlux2.from_pretrained(folder / "vae", torch_dtype=torch.float32).eval()
    pipe = module.MOSSImagePipeline(transformer, scheduler, text_encoder=None, tokenizer=None, vae=vae)
    pipe.to(rt.device)
    pipe.set_progress_bar_config(disable=True)
    batch.model_loaded()
    for item in batch.pending():
        try:
            emb, mask, neg, neg_mask = encoded[item["index"]]
            with torch.no_grad():
                out = pipe(
                    prompt_embeds=emb,
                    prompt_attention_mask=mask,
                    negative_prompt_embeds=neg,
                    negative_prompt_attention_mask=neg_mask,
                    width=item["width"],
                    height=item["height"],
                    num_inference_steps=recipe["steps"],
                    guidance_scale=recipe["guidance"],
                    generator=rt.generator(item["seed"]),
                    output_type="np",
                    **recipe.get("extra", {}),
                )
            batch.done(item, out.images[0])
        except Exception as exc:
            batch.failed(item, exc)


FAMILIES = {"sdxl": _sdxl, "flux2_klein": _klein, "moss": _moss}


def main(arguments: dict, input_dir: Path, output_dir: Path, progress) -> None:
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.pop("HF_TOKEN", None)  # ungated weights only (D-032)
    # One model, one T4 (D-033); in a run group the runner names this process's GPU. Set before torch loads.
    os.environ["CUDA_VISIBLE_DEVICES"] = os.environ.get("AAS_GPU_INDEX", "0")
    batch = _Batch(arguments, Path(output_dir), progress)
    batch.input_dir = Path(input_dir)
    recipe = batch.recipe
    deadline = f"; deadline {batch.deadline} s" if batch.deadline is not None else ""
    _log(
        f"Model {recipe['repo']} @ {recipe['revision']}; {len(batch.items)} image(s); {recipe['steps']} steps; "
        f"guidance {recipe['guidance']}{deadline}"
    )
    for item in batch.items:
        _log(f"{batch.label(item)}: {item['width']}x{item['height']}; seed {item['seed']}")
        _log("Prompt sent to the model: " + item["prompt"])
        if item.get("negative_prompt"):
            _log("Negative prompt: " + item["negative_prompt"])
    if batch.style:
        _log(f"{len(batch.style)} style image(s): " + ", ".join(e["input_id"] for e in batch.style))

    _install(arguments["pins"], progress)
    folder = _download(recipe, progress)
    rt = _Torch(recipe["family"])
    _log(f"Device {rt.device}, dtype {str(rt.dtype).replace('torch.', '')}")
    started = time.time()
    FAMILIES[recipe["family"]](batch, folder, rt, progress)
    _log(f"Rendering finished in {time.time() - started:.1f} s")
    shutil.rmtree(folder, ignore_errors=True)
    if batch.ip_adapter:
        shutil.rmtree(MODEL_ROOT / batch.ip_adapter["key"], ignore_errors=True)
    batch.finish()
    progress("inference", 100, "Images written")
