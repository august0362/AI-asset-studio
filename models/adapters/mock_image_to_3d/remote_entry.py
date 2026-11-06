"""Remote entrypoint for mock Image→3D. Self-contained: standard library + Pillow only.

Writes ``model.glb`` (glTF 2.0 binary: a box sized from the front view, with an embedded 2×2 texture atlas of
front / side / back / detail views) and ``preview.png``. No AI: this is a structural placeholder.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CATEGORY_COLORS = {
    "character": (58, 92, 204),
    "skill_effect": (142, 52, 176),
    "weapon": (190, 48, 48),
    "companion": (40, 146, 74),
}
# Atlas cells (column, row) in a 2×2 grid. glTF UV (0, 0) is the top-left of the image.
CELLS = {"front": (0, 0), "side": (1, 0), "back": (0, 1), "detail": (1, 1)}


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _cell_image(path: Path | None, label: str, size: int, color: tuple[int, int, int]) -> Image.Image:
    cell = Image.new("RGB", (size, size), color)
    if path is not None:
        with Image.open(path) as source:
            view = source.convert("RGB")
            view.thumbnail((size, size))
            cell.paste(view, ((size - view.width) // 2, (size - view.height) // 2))
    else:
        ImageDraw.Draw(cell).text(
            (size // 10, size // 2), f"no {label} view", font=_font(size // 12), fill="white"
        )
    return cell


def build_atlas(views: dict, details: list, input_dir: Path, resolution: int, color) -> Image.Image:
    cell = resolution // 2
    atlas = Image.new("RGB", (resolution, resolution), color)
    sources = {
        "front": views.get("front") or views.get("three_quarter"),
        "side": views.get("side") or views.get("three_quarter"),
        "back": views.get("back"),
        "detail": details[0] if details else None,
    }
    for name, (col, row) in CELLS.items():
        file_name = sources[name]
        atlas.paste(
            _cell_image(input_dir / file_name if file_name else None, name, cell, color),
            (col * cell, row * cell),
        )
    return atlas


def _box(width: float, height: float, depth: float):
    """24 vertices (4 per face), with per-face UVs into the atlas cells."""
    x, z = width / 2, depth / 2

    def uv(cell: str, u: float, v: float) -> tuple[float, float]:
        col, row = CELLS[cell]
        return ((col + u) / 2, (row + v) / 2)

    # Each face: 4 corners, counter-clockwise seen from outside (top-left, bottom-left, bottom-right, top-right)
    faces = [
        ((0, 0, 1), "front", [(-x, height, z), (-x, 0, z), (x, 0, z), (x, height, z)]),
        ((0, 0, -1), "back", [(x, height, -z), (x, 0, -z), (-x, 0, -z), (-x, height, -z)]),
        ((1, 0, 0), "side", [(x, height, z), (x, 0, z), (x, 0, -z), (x, height, -z)]),
        ((-1, 0, 0), "side", [(-x, height, -z), (-x, 0, -z), (-x, 0, z), (-x, height, z)]),
        ((0, 1, 0), "detail", [(-x, height, -z), (-x, height, z), (x, height, z), (x, height, -z)]),
        ((0, -1, 0), "detail", [(-x, 0, z), (-x, 0, -z), (x, 0, -z), (x, 0, z)]),
    ]
    corner_uv = [(0, 0), (0, 1), (1, 1), (1, 0)]
    positions, normals, uvs, indices = [], [], [], []
    for normal, cell, corners in faces:
        base = len(positions)
        for corner, (u, v) in zip(corners, corner_uv, strict=True):
            positions.append(corner)
            normals.append(normal)
            uvs.append(uv(cell, u, v))
        indices += [base, base + 1, base + 2, base, base + 2, base + 3]
    return positions, normals, uvs, indices


def write_glb(path: Path, positions, normals, uvs, indices, texture_png: bytes, name: str) -> None:
    binary = bytearray()
    views: list[dict] = []

    def add_view(data: bytes, target: int | None = None) -> int:
        while len(binary) % 4:
            binary.append(0)
        view = {"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        binary.extend(data)
        views.append(view)
        return len(views) - 1

    def floats(rows) -> bytes:
        flat = [float(value) for row in rows for value in row]
        return struct.pack(f"<{len(flat)}f", *flat)

    pos_view = add_view(floats(positions), 34962)
    nrm_view = add_view(floats(normals), 34962)
    uv_view = add_view(floats(uvs), 34962)
    idx_view = add_view(struct.pack(f"<{len(indices)}H", *indices), 34963)
    img_view = add_view(texture_png)
    while len(binary) % 4:
        binary.append(0)

    count = len(positions)
    document = {
        "asset": {"version": "2.0", "generator": "AI Asset Studio mock_image_to_3d (not AI-generated)"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                        "indices": 3,
                        "material": 0,
                        "mode": 4,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "mock_atlas",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
            }
        ],
        "textures": [{"sampler": 0, "source": 0}],
        "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
        "images": [{"bufferView": img_view, "mimeType": "image/png"}],
        "accessors": [
            {
                "bufferView": pos_view,
                "componentType": 5126,
                "count": count,
                "type": "VEC3",
                "min": [min(p[i] for p in positions) for i in range(3)],
                "max": [max(p[i] for p in positions) for i in range(3)],
            },
            {"bufferView": nrm_view, "componentType": 5126, "count": count, "type": "VEC3"},
            {"bufferView": uv_view, "componentType": 5126, "count": count, "type": "VEC2"},
            {"bufferView": idx_view, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary)
    with path.open("wb") as handle:
        handle.write(struct.pack("<4sII", b"glTF", 2, total))
        handle.write(struct.pack("<I4s", len(json_chunk), b"JSON"))
        handle.write(json_chunk)
        handle.write(struct.pack("<I4s", len(binary), b"BIN\x00"))
        handle.write(bytes(binary))


def _aspect(input_dir: Path, file_name: str | None, default: float) -> float:
    if not file_name:
        return default
    with Image.open(input_dir / file_name) as image:
        return image.height / image.width


def main(arguments: dict, input_dir: Path, output_dir: Path, progress) -> None:
    input_dir, output_dir = Path(input_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    views, details = arguments.get("views", {}), arguments.get("details", [])
    color = CATEGORY_COLORS.get(arguments.get("asset_category"), (90, 90, 90))
    resolution = int(arguments.get("texture_resolution") or 1024)

    progress("inference", 10, "Building mock texture atlas")
    atlas = build_atlas(views, details, input_dir, resolution, color)
    buffer = io.BytesIO()
    atlas.save(buffer, format="PNG")

    progress("inference", 50, "Building mock mesh")
    front = views.get("front") or views.get("three_quarter")
    height = min(3.0, max(0.5, _aspect(input_dir, front, 1.5)))
    side = views.get("side")
    depth = min(1.0, max(0.2, height / _aspect(input_dir, side, height / 0.5))) if side else 0.5
    positions, normals, uvs, indices = _box(1.0, height, depth)
    write_glb(output_dir / "model.glb", positions, normals, uvs, indices, buffer.getvalue(), "mock_asset")

    progress("inference", 80, "Rendering preview")
    preview = Image.new("RGB", (512, 512), color)
    thumb = atlas.crop((0, 0, resolution // 2, resolution // 2))
    thumb.thumbnail((400, 400))
    preview.paste(thumb, ((512 - thumb.width) // 2, 40))
    ImageDraw.Draw(preview).text(
        (20, 470), "MOCK 3D PREVIEW (not AI-generated)", font=_font(22), fill="white"
    )
    preview.save(output_dir / "preview.png", format="PNG")
    progress("inference", 100, "Mock GLB written")
