"""Job logs (``logs/<job_id>.log``, JSON lines) and telemetry (``logs/<job_id>.telemetry.jsonl``), redacted."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from models.contracts import format_timestamp

_SECRET_PATTERNS = [
    (re.compile(r"(KAGGLE_(?:KEY|API_TOKEN)\s*[=:]\s*)\S+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"KGAT_[A-Za-z0-9]+"), "[REDACTED]"),
]


class Redactor:
    """Removes credentials (CONTRACTS §10) and local absolute paths from text that may reach logs or the API."""

    def __init__(self, secrets: Iterable[str] = (), paths: Iterable[Path] = ()) -> None:
        self._secrets = [s for s in secrets if s and len(s) >= 4]
        variants: set[str] = set()
        for path in paths:
            resolved = path.resolve()
            variants |= {str(resolved), resolved.as_posix(), str(resolved).replace("\\", "\\\\")}
        self._paths = sorted(variants, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for pattern, replacement in _SECRET_PATTERNS:
            text = pattern.sub(replacement, text)
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED]")
        for path in self._paths:
            text = text.replace(path, "<data>")
        return text


class RedactingFilter(logging.Filter):
    def __init__(self, redact: Redactor) -> None:
        super().__init__()
        self._redact = redact

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = self._redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


class JobLogs:
    def __init__(self, logs_dir: Path, redact: Redactor, clock: Callable[[], datetime]) -> None:
        self.dir = logs_dir
        self.redact = redact
        self.clock = clock
        self._lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self.dir.mkdir(parents=True, exist_ok=True)

    def log_path(self, job_id: str) -> Path:
        return self.dir / f"{job_id}.log"

    def telemetry_path(self, job_id: str) -> Path:
        return self.dir / f"{job_id}.telemetry.jsonl"

    def _count(self, job_id: str) -> int:
        if job_id not in self._counts:
            path = self.log_path(job_id)
            self._counts[job_id] = sum(1 for _ in path.open(encoding="utf-8")) if path.exists() else 0
        return self._counts[job_id]

    def append(self, job_id: str, source: str, texts: Iterable[str]) -> None:
        with self._lock:
            n = self._count(job_id)
            at = format_timestamp(self.clock())
            rows = []
            for text in texts:
                rows.append(
                    json.dumps({"n": n, "at": at, "source": source, "text": self.redact(text)[:4000]})
                )
                n += 1
            if rows:
                with self.log_path(job_id).open("a", encoding="utf-8") as handle:
                    handle.write("\n".join(rows) + "\n")
                self._counts[job_id] = n

    def read(self, job_id: str, offset: int, limit: int) -> tuple[list[dict[str, Any]], int, int]:
        """(lines, next_offset, total)."""
        with self._lock:
            path = self.log_path(job_id)
            if not path.exists():
                return [], offset, 0
            lines: list[dict[str, Any]] = []
            total = 0
            with path.open(encoding="utf-8") as handle:
                for index, raw in enumerate(handle):
                    total = index + 1
                    if offset <= index < offset + limit:
                        try:
                            lines.append(json.loads(raw))
                        except json.JSONDecodeError:
                            continue
            return lines, offset + len(lines) if lines else min(offset, total), total

    def append_telemetry(self, job_id: str, sample: dict[str, Any]) -> None:
        with self._lock, self.telemetry_path(job_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample) + "\n")

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._counts.pop(job_id, None)
