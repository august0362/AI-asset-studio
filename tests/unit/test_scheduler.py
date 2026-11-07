"""CONTRACTS §14.3: when the FIFO head may take a session slot. Pure logic, no threads started."""

from __future__ import annotations

import threading
import types

from aas_backend.orchestrator.scheduler import Entry, Scheduler


def scheduler(quota_seconds: float | None) -> Scheduler:
    service = types.SimpleNamespace(
        settings=types.SimpleNamespace(max_parallel_sessions=3),
        stopping=threading.Event(),
        _lock=threading.RLock(),
        gpu_quota_remaining_seconds=lambda profile_id: quota_seconds,
    )
    return Scheduler(service)


def entry(key: str, profile: str = "alpha", gpu: bool = True, required: float | None = 1000) -> Entry:
    return Entry(key=key, job_ids=(key,), profile_id=profile, gpu=gpu, required_seconds=required)


def test_sessions_running_at_once_share_one_profile():
    s = scheduler(None)
    s._sessions = {"a": entry("a", "alpha")}
    assert s.can_start(entry("b", "alpha"))
    assert not s.can_start(entry("c", "beta"))


def test_quota_is_reserved_within_the_profile_only():
    s = scheduler(quota_seconds=2500)
    s._sessions = {"a": entry("a", required=1000)}
    assert s.can_start(entry("b", required=1500))  # 1000 + 1500 <= 2500
    assert not s.can_start(entry("c", required=1600))  # 2600 > 2500: waits until a session ends
    s._sessions = {"a": entry("a", required=1000), "b": entry("b", required=1500)}
    assert not s.can_start(entry("d", required=1))


def test_unknown_quota_or_cpu_sessions_do_not_block():
    assert scheduler(None).can_start(entry("b"))
    s = scheduler(quota_seconds=10)
    s._sessions = {"a": entry("a", gpu=False, required=5000)}
    assert s.can_start(entry("b", required=5))  # a CPU session reserves no GPU quota
    s._sessions = {}
    assert s.can_start(entry("c", required=10_000))  # alone, the head always starts (its plan was checked)
