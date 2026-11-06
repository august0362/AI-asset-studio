"""Parser for the notebook output protocol (docs/CONTRACTS.md §6.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from .contracts import ProgressEvent, TelemetrySample

PROGRESS_PREFIX = "AAS_PROGRESS "
TELEMETRY_PREFIX = "AAS_TELEMETRY "
MAX_LINE_BYTES = 4096


@dataclass(frozen=True)
class ParsedLine:
    kind: Literal["progress", "telemetry", "malformed", "text"]
    progress: ProgressEvent | None = None
    telemetry: TelemetrySample | None = None


def parse_line(line: str) -> ParsedLine:
    """Classify one log line. Malformed protocol lines are reported (and later skipped and counted)."""
    for prefix, kind in ((PROGRESS_PREFIX, "progress"), (TELEMETRY_PREFIX, "telemetry")):
        if line.startswith(prefix):
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                return ParsedLine("malformed")
            try:
                payload = json.loads(line[len(prefix) :])
                if kind == "progress":
                    return ParsedLine("progress", progress=ProgressEvent.model_validate(payload))
                return ParsedLine("telemetry", telemetry=TelemetrySample.model_validate(payload))
            except (json.JSONDecodeError, ValidationError):
                return ParsedLine("malformed")
    return ParsedLine("text")
