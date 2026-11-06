"""KaggleResourceSnapshot builder and per-profile resource monitor (docs/CONTRACTS.md §6.2, §6.3).

Every group carries its own source, timestamp and freshness. Unknown values stay ``null``; nothing is derived from
assumed limits (D-009, NFR-3).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

from .contracts import (
    CONTRACT_VERSION,
    AcceleratorAvailability,
    ComputeProfile,
    ErrorItem,
    GpuDevice,
    GroupFreshness,
    GroupSources,
    KaggleResourceSnapshot,
    ObservedAt,
    Source,
    TelemetrySample,
    issue,
    utc_now,
)

QUOTA_FRESH_SECONDS = 600
SESSION_FRESH_SECONDS = 60
DEFAULT_REPORTER_INTERVAL = 15
AuthStatus = Literal["authenticated", "unauthenticated", "invalid_credentials", "unknown"]
SessionStatus = Literal["queued", "running", "finished", "failed", "unknown"]


@dataclass(frozen=True)
class QuotaReading:
    gpu_total_hours: float | None
    gpu_used_hours: float | None
    gpu_remaining_hours: float | None
    tpu_total_hours: float | None
    tpu_used_hours: float | None
    tpu_remaining_hours: float | None
    reset_at: datetime | None
    observed_at: datetime
    source: Source


@dataclass(frozen=True)
class SessionState:
    status: SessionStatus
    accelerator_id: str
    started_at: datetime | None
    observed_at: datetime
    source: Source


def _age(now: datetime, then: datetime) -> int:
    return max(0, int((now - then).total_seconds()))


def build_snapshot(
    profile: ComputeProfile,
    *,
    auth_status: AuthStatus,
    quota: QuotaReading | None,
    session: SessionState | None,
    telemetry: TelemetrySample | None,
    telemetry_source: Source,
    now: datetime,
    reporter_interval: int = DEFAULT_REPORTER_INTERVAL,
    auth_message: str | None = None,
) -> KaggleResourceSnapshot:
    errors: list[ErrorItem] = []
    accelerators = {a.accelerator_id: a for a in profile.accelerators}

    if auth_status in ("unauthenticated", "invalid_credentials"):
        errors.append(
            issue(
                "KAGGLE_AUTH_FAILED",
                "error",
                "authentication_status",
                auth_message or "The Kaggle credentials for this profile are missing or were rejected.",
            )
        )

    # --- quota ---
    if quota is None:
        q_fresh, q_source, q_at = "unavailable", "none", None
        q_values = dict.fromkeys(("gt", "gu", "gr", "tt", "tu", "tr", "reset"))
        errors.append(
            issue(
                "COMPUTE_QUOTA_UNKNOWN",
                "warning",
                "quota",
                "Kaggle did not report quota (old CLI or the command failed).",
                retryable=True,
            )
        )
    else:
        q_source, q_at = quota.source, quota.observed_at
        q_fresh = "fresh" if _age(now, q_at) <= QUOTA_FRESH_SECONDS else "stale"
        q_values = {
            "gt": quota.gpu_total_hours,
            "gu": quota.gpu_used_hours,
            "gr": quota.gpu_remaining_hours,
            "tt": quota.tpu_total_hours,
            "tu": quota.tpu_used_hours,
            "tr": quota.tpu_remaining_hours,
            "reset": quota.reset_at,
        }
        if quota.gpu_remaining_hours is None or q_fresh != "fresh":
            errors.append(
                issue(
                    "COMPUTE_QUOTA_UNKNOWN",
                    "warning",
                    "quota",
                    "GPU quota is unknown or not fresh.",
                    {"freshness": q_fresh, "age_seconds": _age(now, q_at)},
                    retryable=True,
                )
            )
        if quota.tpu_total_hours is None:
            errors.append(
                issue(
                    "COMPUTE_TPU_QUOTA_UNAVAILABLE",
                    "warning",
                    "tpu_quota_total_hours",
                    "TPU quota was not reported by the Kaggle CLI.",
                    retryable=True,
                )
            )

    def remaining_for(kind: str) -> float | None:
        if kind == "gpu_cuda":
            return q_values["gr"]
        if kind == "tpu":
            return q_values["tr"]
        return None

    availability = []
    for spec in profile.accelerators:
        if spec.kind == "cpu":
            status = "available"
        else:
            remaining = remaining_for(spec.kind)
            status = (
                "unknown" if remaining is None else ("quota_exhausted" if remaining <= 0 else "available")
            )
        availability.append(AcceleratorAvailability(accelerator_id=spec.accelerator_id, status=status))

    # --- session ---
    if session is None:
        s_status, s_fresh, s_source, s_at = "none", "unavailable", "none", None
        started, remaining_s, accel_type = None, None, None
    else:
        s_status, s_source, s_at = session.status, session.source, session.observed_at
        s_fresh = "fresh" if _age(now, s_at) <= SESSION_FRESH_SECONDS else "stale"
        started, accel_type, remaining_s = session.started_at, session.accelerator_id, None
        spec = accelerators.get(session.accelerator_id)
        if session.status == "running" and spec is not None:
            terms = []
            if started is not None:
                terms.append(spec.max_session_seconds - _age(now, started))
            quota_hours = remaining_for(spec.kind)
            if quota_hours is not None:
                terms.append(math.floor(quota_hours * 3600))
            remaining_s = max(0, min(terms)) if terms else None

    # --- host / gpu telemetry ---
    cpu = ram_used = ram_total = None
    devices: list[GpuDevice] = []
    h_at = g_at = None
    h_source = g_source = "none"
    running_spec = (
        accelerators.get(session.accelerator_id) if session and session.status == "running" else None
    )
    if running_spec is None:
        h_fresh = g_fresh = "not_applicable"
    elif running_spec.kind == "tpu":
        h_fresh = g_fresh = "unsupported"
    else:
        gpu_applies = running_spec.kind == "gpu_cuda"
        if telemetry is None:
            h_fresh = "unavailable"
            g_fresh = "unavailable" if gpu_applies else "not_applicable"
            for group in ("host", "gpu") if gpu_applies else ("host",):
                errors.append(
                    issue(
                        "COMPUTE_TELEMETRY_UNAVAILABLE",
                        "warning",
                        group,
                        "The session is running but no telemetry sample has arrived yet.",
                        retryable=True,
                    )
                )
        else:
            age = _age(now, telemetry.at)
            fresh = "fresh" if age <= 3 * reporter_interval else "stale"
            cpu, ram_used, ram_total = (
                telemetry.cpu_percent,
                telemetry.ram_used_bytes,
                telemetry.ram_total_bytes,
            )
            h_fresh, h_source, h_at = fresh, telemetry_source, telemetry.at
            if fresh == "stale":
                errors.append(
                    issue(
                        "COMPUTE_TELEMETRY_STALE",
                        "warning",
                        "host",
                        f"The last CPU/RAM sample is {age} s old.",
                        {"age_seconds": age},
                        retryable=True,
                    )
                )
            if not gpu_applies:
                g_fresh = "not_applicable"
            elif not telemetry.gpus:
                g_fresh = "unavailable"
                errors.append(
                    issue(
                        "COMPUTE_TELEMETRY_UNAVAILABLE",
                        "warning",
                        "gpu",
                        "The telemetry sample contains no GPU readings.",
                        {"gpu_source": telemetry.gpu_source},
                        retryable=True,
                    )
                )
            else:
                g_fresh, g_source, g_at = fresh, telemetry_source, telemetry.at
                # GPU0 and GPU1 stay independent: one entry per index, never summed or averaged.
                devices = [
                    GpuDevice(
                        index=g.index,
                        name=g.name,
                        utilization_percent=g.utilization_percent,
                        vram_used_bytes=g.vram_used_bytes,
                        vram_total_bytes=g.vram_total_bytes,
                        temperature_c=g.temperature_c,
                        status="available"
                        if any(
                            v is not None
                            for v in (g.utilization_percent, g.vram_used_bytes, g.vram_total_bytes)
                        )
                        else "unavailable",
                    )
                    for g in sorted(telemetry.gpus, key=lambda g: g.index)
                ]
                if fresh == "stale":
                    errors.append(
                        issue(
                            "COMPUTE_TELEMETRY_STALE",
                            "warning",
                            "gpu",
                            f"The last GPU sample is {age} s old.",
                            {"age_seconds": age},
                            retryable=True,
                        )
                    )

    return KaggleResourceSnapshot(
        contract_version=CONTRACT_VERSION,
        compute_profile_id=profile.profile_id,
        authentication_status=auth_status,
        accelerator_type=accel_type,
        accelerator_availability=availability,
        gpu_quota_total_hours=q_values["gt"],
        gpu_quota_used_hours=q_values["gu"],
        gpu_quota_remaining_hours=q_values["gr"],
        tpu_quota_total_hours=q_values["tt"],
        tpu_quota_used_hours=q_values["tu"],
        tpu_quota_remaining_hours=q_values["tr"],
        quota_reset_at=q_values["reset"],
        session_started_at=started,
        estimated_session_remaining_seconds=remaining_s,
        session_status=s_status,
        cpu_utilization_percent=cpu,
        ram_used_bytes=ram_used,
        ram_total_bytes=ram_total,
        gpu_devices=devices,
        observed_at=ObservedAt(snapshot=now, quota=q_at, session=s_at, host=h_at, gpu=g_at),
        source=GroupSources(quota=q_source, session=s_source, host=h_source, gpu=g_source),
        freshness_status=GroupFreshness(quota=q_fresh, session=s_fresh, host=h_fresh, gpu=g_fresh),
        error=errors,
    )


class ResourceMonitor:
    """Thread-safe per-profile state: auth, last quota reading, current session and latest telemetry sample."""

    def __init__(
        self,
        profile: ComputeProfile,
        *,
        session_source: Source,
        telemetry_source: Source,
        reporter_interval: int = DEFAULT_REPORTER_INTERVAL,
        clock=utc_now,
    ) -> None:
        self.profile = profile
        self._session_source = session_source
        self._telemetry_source = telemetry_source
        self._interval = reporter_interval
        self._clock = clock
        self._lock = threading.Lock()
        self.auth_status: AuthStatus = "unknown"
        self.auth_message: str | None = None
        self.quota: QuotaReading | None = None
        self.session: SessionState | None = None
        self.telemetry: TelemetrySample | None = None
        self.session_job_id: str | None = None

    def set_auth(self, status: AuthStatus, message: str | None = None) -> None:
        with self._lock:
            self.auth_status = status
            self.auth_message = message

    def set_quota(self, reading: QuotaReading | None) -> None:
        with self._lock:
            self.quota = reading

    def session_submitted(self, job_id: str, accelerator_id: str) -> None:
        with self._lock:
            self.session = SessionState("queued", accelerator_id, None, self._clock(), self._session_source)
            self.session_job_id = job_id
            self.telemetry = None

    def session_observed(self, job_id: str, status: SessionStatus) -> None:
        with self._lock:
            if self.session is None or self.session_job_id != job_id:
                return
            now = self._clock()
            started = self.session.started_at or (now if status == "running" else None)
            self.session = replace(self.session, status=status, observed_at=now, started_at=started)

    def telemetry_observed(self, sample: TelemetrySample) -> None:
        with self._lock:
            if self.session_job_id != sample.job_id:
                return
            if self.telemetry is None or sample.at >= self.telemetry.at:
                self.telemetry = sample

    def snapshot(
        self,
        *,
        session: SessionState | None = None,
        telemetry: TelemetrySample | None = None,
        override_session: bool = False,
    ) -> KaggleResourceSnapshot:
        with self._lock:
            use_session = session if override_session else self.session
            use_telemetry = telemetry if override_session else self.telemetry
            return build_snapshot(
                self.profile,
                auth_status=self.auth_status,
                quota=self.quota,
                session=use_session,
                telemetry=use_telemetry,
                telemetry_source=self._telemetry_source,
                now=self._clock(),
                reporter_interval=self._interval,
                auth_message=self.auth_message,
            )
