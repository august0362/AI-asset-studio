"""Job state machine (docs/CONTRACTS.md §4)."""

from __future__ import annotations

from datetime import datetime

from models.contracts import TERMINAL_STATUSES

from ..schemas import StatusEntry
from .records import JobRecord

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"uploading", "queued", "failed"}),
    "uploading": frozenset({"queued", "failed"}),
    "queued": frozenset({"running", "failed"}),
    "running": frozenset({"downloading", "failed"}),
    "downloading": frozenset({"completed", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}


class InvalidTransition(Exception):
    pass


def can_transition(current: str, new: str) -> bool:
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())


def apply_transition(record: JobRecord, new: str, at: datetime) -> JobRecord:
    """Return a copy in state ``new`` with history appended. Terminal states never change."""
    if record.status in TERMINAL_STATUSES or not can_transition(record.status, new):
        raise InvalidTransition(f"{record.status} -> {new} is not allowed")
    updated = record.model_copy(deep=True)
    updated.status = new
    updated.status_history.append(StatusEntry(status=new, at=at))
    updated.updated_at = at
    return updated
