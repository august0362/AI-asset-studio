"""Atomic file writes (temp file in the same directory + fsync + rename)."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(10):  # Windows: the target may be briefly open by a reader
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.05)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_bytes(path, json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def remove_tree(path: Path) -> None:
    """Delete a directory (or file) that the backend owns. Ignores missing paths; retries briefly on Windows."""
    for attempt in range(5):
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.1)
