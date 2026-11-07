"""Session scheduler (D-040, D-041; CONTRACTS §14.3).

``AAS_MAX_PARALLEL_SESSIONS`` slots across all profiles, v1 jobs, run groups and V2 batch jobs. The FIFO is strict:
the head starts only when a slot is free, every running session uses the head's profile, and the head's
``required_seconds`` plus those of that profile's running GPU sessions fits the profile's known GPU quota. Otherwise
the head waits until a session ends; no waiting job overtakes it. Quota is never combined across profiles, a job
never changes profile and is never resubmitted.

Taking a slot and deleting a job use the service lock, so a delete either wins (the job is gone) or sees the job
``starting`` and is refused.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .worker import JobRunner

if TYPE_CHECKING:
    from .records import JobRecord
    from .service import JobService

log = logging.getLogger("aas_backend")
WAKE_SECONDS = 1.0  # re-check the head now and then: the cached quota may have changed


@dataclass(frozen=True)
class Entry:
    """One FIFO entry: a job, or a run group of two jobs (one entry, one session)."""

    key: str
    job_ids: tuple[str, ...]
    profile_id: str
    gpu: bool
    required_seconds: float | None


def fifo_key(record: JobRecord) -> tuple:
    return (
        record.scheduling.run_requested_at,
        record.scheduling.requested_ns,
        record.created_at,
        record.internal.created_ns,
        record.job_id,
    )


class Scheduler(threading.Thread):
    def __init__(self, service: JobService) -> None:
        super().__init__(name="aas-scheduler", daemon=True)
        self.s = service
        self.runner = JobRunner(service)
        self._wake = threading.Event()
        self._sessions: dict[str, Entry] = {}
        self._threads: list[threading.Thread] = []

    @property
    def slots(self) -> int:
        return self.s.settings.max_parallel_sessions

    def notify(self) -> None:
        self._wake.set()

    def running_sessions(self) -> list[Entry]:
        with self.s._lock:
            return list(self._sessions.values())

    # --- sessions ------------------------------------------------------------------------------------------------

    def resume(self, entries: list[Entry]) -> None:
        """Jobs that already have a remote run continue at once: they were running before the restart."""
        with self.s._lock:
            for entry in entries:
                self._open(entry)

    def _open(self, entry: Entry) -> None:
        self._sessions[entry.key] = entry
        thread = threading.Thread(
            target=self._session, args=(entry,), name=f"aas-session-{entry.key}", daemon=True
        )
        self._threads = [t for t in self._threads if t.is_alive()]
        self._threads.append(thread)
        thread.start()

    def _session(self, entry: Entry) -> None:
        try:
            if len(entry.job_ids) == 1:
                self.runner.process(entry.job_ids[0])
            else:
                self.runner.process_group(list(entry.job_ids))
        except Exception:  # the runner handles job failures; this only keeps the slot accounting right
            log.exception("session %s ended unexpectedly", entry.key)
        finally:
            with self.s._lock:
                self._sessions.pop(entry.key, None)
            self._wake.set()

    # --- dispatch ------------------------------------------------------------------------------------------------

    def run(self) -> None:
        while not self.s.stopping.is_set():
            self._wake.wait(WAKE_SECONDS)
            self._wake.clear()
            if self.s.stopping.is_set():
                return
            try:
                self.dispatch()
            except Exception:
                log.exception("scheduler dispatch failed")

    def dispatch(self) -> None:
        with self.s._lock:
            while len(self._sessions) < self.slots:
                fifo = self.s.fifo()
                if not fifo:
                    return
                head = fifo[0]
                if not self.s.profile_enabled(head.profile_id):
                    for job_id in head.job_ids:
                        self.s.fail(
                            self.s.get_record(job_id),
                            "INTERNAL_ERROR",
                            "No worker for this compute profile.",
                            {},
                            False,
                        )
                    continue
                if not self.can_start(head):
                    return
                self.s.take_slot(head)
                self._open(head)

    def can_start(self, head: Entry) -> bool:
        running = list(self._sessions.values())
        if any(entry.profile_id != head.profile_id for entry in running):
            return False  # sessions that run at the same time use one profile
        same = [entry for entry in running if entry.gpu]
        if head.gpu and same and head.required_seconds is not None:
            remaining = self.s.gpu_quota_remaining_seconds(head.profile_id)
            reserved = sum(entry.required_seconds or 0 for entry in same)
            if remaining is not None and head.required_seconds + reserved > remaining:
                return False
        return True

    def join_sessions(self, timeout: float) -> None:
        for thread in list(self._threads):
            thread.join(timeout=timeout)
