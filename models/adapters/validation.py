"""Output format checks used by ``collect_outputs`` (docs/CONTRACTS.md §3.5)."""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

from PIL import Image

GLB_MAGIC = b"glTF"
CHUNK_JSON = 0x4E4F534A
CHUNK_BIN = 0x004E4942
_COMPONENT_SIZES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
_TYPE_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}


def validate_png(path: Path) -> tuple[int, int]:
    """Return ``(width, height)`` or raise ``ValueError`` when the file is not a decodable PNG."""
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError(f"format is {image.format}, expected PNG")
            image.verify()
        with Image.open(path) as image:
            image.load()
            return image.size
    except ValueError:
        raise
    except Exception as exc:  # Pillow raises many exception types for corrupt data
        raise ValueError(f"PNG cannot be decoded: {exc.__class__.__name__}") from exc


def validate_glb_bytes(data: bytes) -> dict:
    """Structural glTF 2.0 binary check. Returns the parsed JSON chunk or raises ``ValueError``."""
    if len(data) < 20:
        raise ValueError("file too small for a GLB header")
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != GLB_MAGIC:
        raise ValueError("bad magic (not glTF)")
    if version != 2:
        raise ValueError(f"glTF version {version}, expected 2")
    if length != len(data):
        raise ValueError("header length does not match the file size")
    json_length, json_type = struct.unpack_from("<II", data, 12)
    if json_type != CHUNK_JSON or 20 + json_length > len(data):
        raise ValueError("first chunk is not a valid JSON chunk")
    try:
        document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON chunk cannot be parsed") from exc
    if not isinstance(document, dict) or document.get("asset", {}).get("version") != "2.0":
        raise ValueError("asset.version must be '2.0'")

    offset = 20 + json_length
    binary = b""
    if offset < len(data):
        if offset + 8 > len(data):
            raise ValueError("truncated BIN chunk header")
        bin_length, bin_type = struct.unpack_from("<II", data, offset)
        if bin_type != CHUNK_BIN or offset + 8 + bin_length > len(data):
            raise ValueError("second chunk is not a valid BIN chunk")
        binary = data[offset + 8 : offset + 8 + bin_length]

    buffers = document.get("buffers", [])
    for buffer in buffers:
        if "uri" in buffer:
            raise ValueError("external buffers are not allowed; everything must be embedded")
    if buffers and buffers[0].get("byteLength", 0) > len(binary):
        raise ValueError("buffer 0 is larger than the BIN chunk")

    views = document.get("bufferViews", [])
    for view in views:
        if view.get("byteOffset", 0) + view.get("byteLength", 0) > len(binary):
            raise ValueError("a bufferView exceeds the binary buffer")
    for accessor in document.get("accessors", []):
        view_index = accessor.get("bufferView")
        if view_index is None or view_index >= len(views):
            raise ValueError("an accessor references a missing bufferView")
        size = _COMPONENT_SIZES.get(accessor.get("componentType"), 0) * _TYPE_COUNTS.get(
            accessor.get("type"), 0
        )
        if size == 0:
            raise ValueError("an accessor has an unknown componentType or type")
        if accessor.get("byteOffset", 0) + size * accessor.get("count", 0) > views[view_index]["byteLength"]:
            raise ValueError("an accessor exceeds its bufferView")

    meshes = document.get("meshes", [])
    if not meshes or not all(
        "POSITION" in primitive.get("attributes", {})
        for mesh in meshes
        for primitive in mesh.get("primitives", [])
    ):
        raise ValueError("no mesh with a POSITION attribute")

    for image in document.get("images", []):
        if "uri" in image:
            raise ValueError("external images are not allowed; textures must be embedded")
        view = views[image["bufferView"]]
        start = view.get("byteOffset", 0)
        payload = binary[start : start + view["byteLength"]]
        try:
            with Image.open(io.BytesIO(payload)) as embedded:
                embedded.verify()
        except Exception as exc:
            raise ValueError("an embedded texture cannot be decoded") from exc
    return document


def validate_glb(path: Path) -> dict:
    return validate_glb_bytes(path.read_bytes())
