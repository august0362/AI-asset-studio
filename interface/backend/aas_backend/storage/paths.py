"""Path safety (docs/CONTRACTS.md §9): every path is ``data_root / <validated relative path>``."""

from __future__ import annotations

import os
import re
from pathlib import Path

from models.contracts.common import (
    ARTIFACT_ID_PATTERN,
    INPUT_ID_PATTERN,
    JOB_ID_PATTERN,
    UPLOAD_ID_PATTERN,
)

ID_PATTERNS = {
    "job_id": re.compile(JOB_ID_PATTERN),
    "upload_id": re.compile(UPLOAD_ID_PATTERN),
    "input_id": re.compile(INPUT_ID_PATTERN),
    "artifact_id": re.compile(ARTIFACT_ID_PATTERN),
}
_DRIVE = re.compile(r"^[A-Za-z]:")


class PathInvalid(Exception):
    code = "PATH_INVALID"


def is_valid_id(kind: str, value: str) -> bool:
    return isinstance(value, str) and ID_PATTERNS[kind].fullmatch(value) is not None


def check_id(kind: str, value: str) -> str:
    if not is_valid_id(kind, value):
        raise PathInvalid(f"invalid {kind}")
    return value


def _is_link(path: Path) -> bool:
    isjunction = getattr(os.path, "isjunction", None)
    return path.is_symlink() or bool(isjunction and isjunction(path))


def safe_path(root: Path, relative: str) -> Path:
    """Resolve a POSIX relative path under ``root``. Rejects absolute paths, ``..``, backslashes and links."""
    if (
        not relative
        or "\\" in relative
        or "\x00" in relative
        or relative.startswith("/")
        or _DRIVE.match(relative)
    ):
        raise PathInvalid("absolute or malformed path")
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PathInvalid("path traversal")
    current = root
    for part in parts:
        current = current / part
        if _is_link(current):
            raise PathInvalid("symlinks are not allowed under the data root")
    if not current.resolve().is_relative_to(root.resolve()):
        raise PathInvalid("path escapes the data root")
    return current


def to_relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
