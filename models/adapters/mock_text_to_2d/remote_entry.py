"""Remote entrypoint for mock Text→2D. Self-contained: standard library + Pillow only.

The runner calls ``main(arguments, input_dir, output_dir, progress)``. Output: ``image.png``, or for a batch job
(``arguments["tasks"]``, §13.9) one ``task_<task_id>.png`` per task plus ``task_results.json``.
Deterministic for a given seed; a null seed draws a random one.
"""

from __future__ import annotations

import json
import os
import random
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CATEGORY_COLORS = {
    "character": (58, 92, 204),
    "skill_effect": (142, 52, 176),
    "weapon": (190, 48, 48),
    "companion": (40, 146, 74),
}


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def render(arguments: dict, input_dir: Path) -> Image.Image:
    width, height = int(arguments["width"]), int(arguments["height"])
    category = arguments["asset_category"]
    seed = arguments.get("seed")
    # Decorative shapes only; not security relevant.
    rng = random.Random(seed if seed is not None else random.SystemRandom().randrange(2**32))  # noqa: S311
    base = CATEGORY_COLORS.get(category, (90, 90, 90))

    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):  # vertical gradient from the category color to near-black
        t = y / max(height - 1, 1)
        draw.line([(0, y), (width, y)], fill=tuple(int(c * (1 - 0.75 * t)) for c in base))
    for _ in range(14):  # seeded decorative shapes
        r = rng.randint(width // 30, width // 6)
        x, y = rng.randint(0, width), rng.randint(0, height)
        tint = tuple(min(255, c + rng.randint(30, 110)) for c in base)
        draw.ellipse([x - r, y - r, x + r, y + r], outline=tint, width=max(2, width // 256))

    style_name = arguments.get("style_reference")
    if style_name:
        with Image.open(input_dir / style_name) as style:
            thumb = style.convert("RGB")
            thumb.thumbnail((width // 4, height // 4))
            image.paste(thumb, (width - thumb.width - width // 32, height // 32))

    panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rectangle(
        [width // 16, height // 2, width - width // 16, height - height // 16], fill=(0, 0, 0, 150)
    )
    image = Image.alpha_composite(image.convert("RGBA"), panel).convert("RGB")
    draw = ImageDraw.Draw(image)

    big, small = _font(max(12, width // 14)), _font(max(10, width // 40))
    left, top = width // 10, height // 2 + height // 32
    draw.text((left, top), "MOCK OUTPUT", font=big, fill=(255, 255, 255))
    lines = [
        "Not AI-generated. Placeholder from mock_text_to_2d.",
        f"Category: {category}    Model: {arguments['model_id']}",
        f"Seed: {seed if seed is not None else 'random'}",
    ]
    prompt = (arguments.get("prompt") or "").strip()
    if prompt:
        excerpt = prompt if len(prompt) <= 160 else prompt[:157] + "..."
        lines += ["Prompt:", *textwrap.wrap(excerpt, width=48)[:4]]
    y = top + int(big.size if hasattr(big, "size") else 24) + height // 40
    for line in lines:
        draw.text((left, y), line, font=small, fill=(230, 230, 230))
        y += max(12, width // 32)
    return image


def _write_results(output_dir: Path, results: list) -> None:
    path = output_dir / "task_results.json"
    temp = output_dir / "task_results.json.tmp"
    temp.write_text(json.dumps({"v": 1, "tasks": results}, indent=2), encoding="utf-8")
    os.replace(temp, path)


def run_batch(arguments: dict, input_dir: Path, output_dir: Path, progress) -> None:
    """Batch job (§13.9): one load, then the tasks in order. Test hooks (mock only): ``AAS_MOCK_FAIL_TASKS``
    (comma-separated task_ids that raise), ``AAS_MOCK_TASK_SECONDS`` (time per task) and
    ``AAS_MOCK_DEADLINE_SECONDS`` (overrides the deadline)."""
    tasks = arguments["tasks"]
    failing = {t for t in os.environ.get("AAS_MOCK_FAIL_TASKS", "").split(",") if t}
    task_seconds = float(os.environ.get("AAS_MOCK_TASK_SECONDS", "0") or 0)
    deadline = os.environ.get("AAS_MOCK_DEADLINE_SECONDS") or arguments.get("deadline_seconds")
    deadline = float(deadline) if deadline is not None else None
    started = time.monotonic()
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"MODEL_LOAD {arguments['model_id']} mock", flush=True)
    results: list = []
    last = 0.0
    for index, task in enumerate(tasks):
        elapsed = time.monotonic() - started
        if deadline is not None and elapsed + last > deadline:
            for rest in tasks[index:]:
                results.append(
                    {
                        "task_id": rest["task_id"],
                        "status": "not_run",
                        "seed": rest.get("seed"),
                        "seconds": None,
                        "error": {
                            "message": "The job's time budget ran out before this task started.",
                            "reason": "deadline",
                        },
                    }
                )
            print(
                f"Deadline reached after {elapsed:.1f} s; {len(tasks) - index} task(s) not run.", flush=True
            )
            break
        progress(
            "inference",
            round(100 * index / len(tasks), 1),
            f"Task {index + 1}/{len(tasks)}: {task['task_id']}",
        )
        print(f"TASK_START {task['task_id']}", flush=True)
        task_started = time.monotonic()
        seed = task.get("seed")
        if seed is None:
            seed = random.SystemRandom().randrange(2**32)
        try:
            if task_seconds:
                time.sleep(task_seconds)
            if task["task_id"] in failing:
                raise RuntimeError(f"Simulated task failure (mock): {task['task_id']}")
            image = render(
                {
                    "prompt": task["prompt"],
                    "asset_category": arguments["asset_category"],
                    "model_id": arguments["model_id"],
                    "width": task["width"],
                    "height": task["height"],
                    "seed": seed,
                },
                input_dir,
            )
            image.save(output_dir / task["output"], format="PNG", optimize=False)
            entry = {"task_id": task["task_id"], "status": "succeeded", "seed": seed, "error": None}
        except Exception as exc:
            message = f"{exc.__class__.__name__}: {exc}"[:500]
            print(f"Task {task['task_id']} failed: {message}", flush=True)
            entry = {
                "task_id": task["task_id"],
                "status": "failed",
                "seed": seed,
                "error": {"message": message, "reason": None},
            }
        last = time.monotonic() - task_started
        entry["seconds"] = round(last, 3)
        results.append(entry)
        _write_results(output_dir, results)
    _write_results(output_dir, results)
    succeeded = sum(1 for r in results if r["status"] == "succeeded")
    print(f"Batch finished: {succeeded} of {len(tasks)} task(s) succeeded.", flush=True)
    if not succeeded:
        raise RuntimeError("No task of this batch succeeded.")
    progress("inference", 100, f"{succeeded} of {len(tasks)} image(s) written")


def main(arguments: dict, input_dir: Path, output_dir: Path, progress) -> None:
    if "tasks" in arguments:
        run_batch(arguments, Path(input_dir), Path(output_dir), progress)
        return
    progress("inference", 10, "Rendering mock image")
    image = render(arguments, Path(input_dir))
    progress("inference", 80, "Encoding PNG")
    output_dir.mkdir(parents=True, exist_ok=True)
    image.save(output_dir / "image.png", format="PNG", optimize=False)
    progress("inference", 100, "Mock image written")
