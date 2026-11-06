"""Two-phase upload staging (docs/CONTRACTS.md §3.1, §9): ``inputs/staging/<upload_id>/{file.<ext>, upload.json}``."""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from PIL import Image
from pydantic import ValidationError

from models.contracts import CONTRACT_VERSION, MAX_UPLOAD_BYTES, UploadRecord

from ..errors import api_error
from .files import atomic_write_json, read_json, remove_tree
from .paths import is_valid_id, safe_path

log = logging.getLogger("aas_backend")

MIME_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
PILLOW_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
CHUNK = 1 << 20


def sniff_mime(head: bytes) -> str | None:
    """Detect the type from the file bytes, never from the name or header (§1.3)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def display_name(filename: str | None) -> str:
    """Display only; never used in a path."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (name or "upload")[:255]


@dataclass(frozen=True)
class StagedUpload:
    record: UploadRecord
    path: Path


class UploadStore:
    def __init__(self, data_root: Path, ttl: timedelta, clock: Callable[[], datetime]) -> None:
        self.root = data_root
        self.staging = data_root / "inputs" / "staging"
        self.ttl = ttl
        self.clock = clock
        self.staging.mkdir(parents=True, exist_ok=True)

    def _dir(self, upload_id: str) -> Path:
        return safe_path(self.root, f"inputs/staging/{upload_id}")

    def save(self, stream: BinaryIO, filename: str | None) -> UploadRecord:
        upload_id = f"upl_{secrets.token_hex(16)}"
        directory = self._dir(upload_id)
        directory.mkdir(parents=True)
        partial = directory / "file.part"
        digest, size, head = hashlib.sha256(), 0, b""
        try:
            with partial.open("wb") as out:
                while chunk := stream.read(CHUNK):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise api_error(
                            413,
                            "UPLOAD_TOO_LARGE",
                            "file",
                            f"The file is larger than the {MAX_UPLOAD_BYTES}-byte limit.",
                            {"max_upload_bytes": MAX_UPLOAD_BYTES},
                        )
                    if len(head) < 16:
                        head += chunk[: 16 - len(head)]
                    digest.update(chunk)
                    out.write(chunk)
            mime = sniff_mime(head)
            if mime is None:
                raise api_error(
                    415,
                    "UPLOAD_UNSUPPORTED_TYPE",
                    "file",
                    "Only PNG, JPEG and WebP images are accepted.",
                    {"supported_upload_mime_types": list(MIME_EXTENSIONS)},
                )
            try:
                with Image.open(partial) as image:
                    if image.format != PILLOW_FORMATS[mime]:
                        raise ValueError("content does not match its signature")
                    image.verify()
                with Image.open(partial) as image:
                    image.load()
                    width, height = image.size
            except Exception as exc:
                raise api_error(422, "UPLOAD_CORRUPT", "file", "The image cannot be decoded.") from exc
            final = directory / f"file.{MIME_EXTENSIONS[mime]}"
            partial.replace(final)
            now = self.clock()
            record = UploadRecord(
                contract_version=CONTRACT_VERSION,
                upload_id=upload_id,
                filename=display_name(filename),
                mime_type=mime,
                size_bytes=size,
                width=width,
                height=height,
                sha256=digest.hexdigest(),
                created_at=now,
                expires_at=now + self.ttl,
            )
            atomic_write_json(directory / "upload.json", record.model_dump(mode="json"))
            return record
        except BaseException:
            remove_tree(directory)
            raise

    def _load(self, upload_id: str) -> StagedUpload | None:
        if not is_valid_id("upload_id", upload_id):
            return None
        directory = self._dir(upload_id)
        try:
            record = UploadRecord.model_validate(read_json(directory / "upload.json"))
        except FileNotFoundError:
            return None
        except (ValueError, ValidationError):
            log.warning("ignoring malformed upload metadata for %s", upload_id)
            return None
        if record.upload_id != upload_id:
            return None
        path = safe_path(
            self.root, f"inputs/staging/{upload_id}/file.{MIME_EXTENSIONS.get(record.mime_type, 'x')}"
        )
        return StagedUpload(record, path) if path.is_file() else None

    def get(self, upload_id: str) -> StagedUpload | None:
        """A live (not expired) upload, or None."""
        staged = self._load(upload_id)
        if staged is None or staged.record.expires_at <= self.clock():
            return None
        return staged

    def delete(self, upload_id: str) -> None:
        remove_tree(self._dir(upload_id))

    def sweep(self, referenced: set[str]) -> int:
        """Delete expired staged uploads that no job references, and leftovers without valid metadata."""
        removed = 0
        now = self.clock()
        for directory in self.staging.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            name = directory.name
            if not is_valid_id("upload_id", name):
                continue
            if name in referenced:
                continue
            staged = self._load(name)
            if staged is None:
                mtime = datetime.fromtimestamp(directory.stat().st_mtime, tz=now.tzinfo)
                expired = now - mtime > self.ttl
            else:
                expired = staged.record.expires_at <= now
            if expired:
                remove_tree(directory)
                removed += 1
        return removed
