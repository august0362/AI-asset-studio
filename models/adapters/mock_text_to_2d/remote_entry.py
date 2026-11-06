"""Remote entrypoint for mock Text→2D. Self-contained: standard library + Pillow only.

The runner calls ``main(arguments, input_dir, output_dir, progress)``. Output: ``image.png``.
Deterministic for a given seed; a null seed draws a random one.
"""

from __future__ import annotations

import random
import textwrap
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


def main(arguments: dict, input_dir: Path, output_dir: Path, progress) -> None:
    progress("inference", 10, "Rendering mock image")
    image = render(arguments, Path(input_dir))
    progress("inference", 80, "Encoding PNG")
    output_dir.mkdir(parents=True, exist_ok=True)
    image.save(output_dir / "image.png", format="PNG", optimize=False)
    progress("inference", 100, "Mock image written")
