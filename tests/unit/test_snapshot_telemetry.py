"""Snapshots (§6.2, §6.3), telemetry parsing (§6.4) and the mock resource scenarios."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from kaggle_connector.client import SCENARIOS, MockKaggleClient, mock_profile
from kaggle_connector.client.mock import mock_sample_fields
from kaggle_connector.resources import QuotaReading, SessionState, TelemetrySample, build_snapshot, parse_line
from kaggle_connector.resources.contracts import utc_now

NOW = utc_now()
QUOTA = QuotaReading(
    30.0, 11.5, 18.5, None, None, None, None, NOW - timedelta(seconds=30), "kaggle_cli_quota"
)


def sample(age: int = 5, accelerator: str = "gpu_t4x2", scenario: str = "gpu_split") -> TelemetrySample:
    return TelemetrySample.model_validate(
        {
            "v": 1,
            "job_id": "job_x",
            "at": NOW - timedelta(seconds=age),
            **mock_sample_fields(scenario, accelerator),
        }
    )


def running(accelerator: str = "gpu_t4x2", started_minutes: int = 10) -> SessionState:
    return SessionState(
        "running", accelerator, NOW - timedelta(minutes=started_minutes), NOW, "kaggle_cli_status"
    )


def snap(**kwargs):
    defaults = {
        "auth_status": "authenticated",
        "quota": QUOTA,
        "session": None,
        "telemetry": None,
        "telemetry_source": "notebook_telemetry",
        "now": NOW,
    }
    return build_snapshot(mock_profile(), **{**defaults, **kwargs})


def codes(items):
    return [i.code for i in items]


def test_no_session_scenario():
    s = snap()
    assert s.session_status == "none" and s.gpu_devices == []
    assert (s.cpu_utilization_percent, s.ram_used_bytes, s.ram_total_bytes) == (None, None, None)
    assert (s.freshness_status.host, s.freshness_status.gpu) == ("not_applicable", "not_applicable")
    assert (s.source.host, s.source.gpu) == ("none", "none")
    assert s.estimated_session_remaining_seconds is None


def test_quota_missing_scenario():
    s = snap(quota=None)
    quota_fields = [
        s.gpu_quota_total_hours,
        s.gpu_quota_used_hours,
        s.gpu_quota_remaining_hours,
        s.tpu_quota_total_hours,
        s.tpu_quota_used_hours,
        s.tpu_quota_remaining_hours,
        s.quota_reset_at,
    ]
    assert all(v is None for v in quota_fields)
    assert s.freshness_status.quota == "unavailable" and "COMPUTE_QUOTA_UNKNOWN" in codes(s.error)
    assert {a.status for a in s.accelerator_availability if a.accelerator_id != "cpu"} == {"unknown"}


def test_quota_is_never_derived_and_tpu_gap_is_reported():
    s = snap()
    assert (s.gpu_quota_total_hours, s.gpu_quota_remaining_hours, s.tpu_quota_total_hours) == (
        30.0,
        18.5,
        None,
    )
    assert "COMPUTE_TPU_QUOTA_UNAVAILABLE" in codes(s.error)


def test_quota_older_than_ten_minutes_is_stale():
    old = QuotaReading(
        30.0, 11.5, 18.5, None, None, None, None, NOW - timedelta(minutes=11), "kaggle_cli_quota"
    )
    assert snap(quota=old).freshness_status.quota == "stale"


def test_gpu0_and_gpu1_are_independent():
    """V-08: each device keeps its own values; never summed or averaged."""
    s = snap(session=running(), telemetry=sample())
    assert [d.index for d in s.gpu_devices] == [0, 1]
    gpu0, gpu1 = s.gpu_devices
    assert (gpu0.utilization_percent, gpu0.vram_used_bytes, gpu0.temperature_c) == (97.0, 13421772800, 71.0)
    assert (gpu1.utilization_percent, gpu1.vram_used_bytes, gpu1.temperature_c) == (4.0, 524288000, None)
    assert s.freshness_status.gpu == "fresh" and s.source.gpu == "notebook_telemetry"


def test_telemetry_stale_keeps_last_values_and_warns():
    s = snap(session=running(), telemetry=sample(age=120))
    assert (s.freshness_status.host, s.freshness_status.gpu) == ("stale", "stale")
    assert s.cpu_utilization_percent == 63.5
    stale = [e for e in s.error if e.code == "COMPUTE_TELEMETRY_STALE"]
    assert stale and all(e.details["age_seconds"] == 120 for e in stale)


def test_telemetry_unavailable_while_running():
    s = snap(session=running(), telemetry=None)
    assert (s.freshness_status.host, s.freshness_status.gpu) == ("unavailable", "unavailable")
    assert s.cpu_utilization_percent is None and s.gpu_devices == []
    assert "COMPUTE_TELEMETRY_UNAVAILABLE" in codes(s.error)


def test_tpu_telemetry_is_unsupported_and_cpu_has_no_gpu_group():
    tpu = snap(session=running("tpu_vm"), telemetry=None)
    assert (tpu.freshness_status.host, tpu.freshness_status.gpu) == ("unsupported", "unsupported")
    cpu = snap(session=running("cpu"), telemetry=sample(accelerator="cpu"))
    assert (cpu.freshness_status.host, cpu.freshness_status.gpu) == ("fresh", "not_applicable")


def test_estimated_session_remaining_uses_known_terms_only():
    s = snap(session=running(started_minutes=10))
    assert s.estimated_session_remaining_seconds == 43200 - 600
    low = QuotaReading(30.0, 29.9, 0.1, None, None, None, None, NOW, "kaggle_cli_quota")
    assert snap(quota=low, session=running()).estimated_session_remaining_seconds == 360
    assert (
        snap(
            quota=None, session=SessionState("running", "gpu_t4x2", None, NOW, "local_observation")
        ).estimated_session_remaining_seconds
        is None
    )


def test_exhausted_quota_marks_gpu_accelerators():
    empty = QuotaReading(30.0, 30.0, 0.0, None, None, None, None, NOW, "kaggle_cli_quota")
    status = {a.accelerator_id: a.status for a in snap(quota=empty).accelerator_availability}
    assert status == {
        "cpu": "available",
        "gpu_p100": "quota_exhausted",
        "gpu_t4x2": "quota_exhausted",
        "tpu_vm": "unknown",
    }


def test_unauthenticated_profile_reports_auth_error():
    assert "KAGGLE_AUTH_FAILED" in codes(snap(auth_status="invalid_credentials").error)


# --- §6.4 parser ---------------------------------------------------------------------------------------------


def test_parse_progress_and_telemetry_lines():
    progress = parse_line(
        'AAS_PROGRESS {"v":1,"job_id":"j","at":"2026-11-06T10:20:00Z","stage":"inference",'
        '"percent":40,"message":"Reconstructing mesh"}'
    )
    assert progress.kind == "progress" and progress.progress.percent == 40
    payload = {
        "v": 1,
        "job_id": "j",
        "at": "2026-11-06T10:19:52Z",
        **mock_sample_fields("gpu_split", "gpu_t4x2"),
    }
    telemetry = parse_line("AAS_TELEMETRY " + json.dumps(payload))
    assert telemetry.kind == "telemetry" and len(telemetry.telemetry.gpus) == 2


@pytest.mark.parametrize(
    "line",
    [
        'AAS_TELEMETRY {"v":1,',
        "AAS_TELEMETRY []",
        'AAS_PROGRESS {"v":2,"job_id":"j","at":"x","stage":"s"}',
        "AAS_TELEMETRY "
        + json.dumps({"v": 1, "job_id": "j", "at": "2026-11-06T10:19:52Z", "errors": ["x" * 5000]}),
    ],
)
def test_malformed_protocol_lines(line):
    assert parse_line(line).kind == "malformed"


def test_plain_lines_are_text():
    assert parse_line("Loading weights...").kind == "text"


# --- mock scenarios ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_mock_scenario_produces_a_valid_labeled_snapshot(scenario, tmp_path):
    client = MockKaggleClient(scenario=scenario, remote_root=tmp_path)
    try:
        s = client.snapshot("default")
    finally:
        client.close()
    expected = {
        "fresh": ("running", "fresh", "fresh"),
        "no_session": ("none", "not_applicable", "fresh"),
        "quota_missing": ("none", "not_applicable", "unavailable"),
        "telemetry_stale": ("running", "stale", "fresh"),
        "telemetry_unavailable": ("running", "unavailable", "fresh"),
        "gpu_split": ("running", "fresh", "fresh"),
        "quota_low": ("none", "not_applicable", "fresh"),
    }[scenario]
    assert (s.session_status, s.freshness_status.gpu, s.freshness_status.quota) == expected
    assert {s.source.quota, s.source.session} <= {"mock", "none"}
    if scenario == "quota_low":
        assert s.gpu_quota_remaining_hours == 0.3
    if scenario == "gpu_split":
        assert [d.utilization_percent for d in s.gpu_devices] == [97.0, 4.0]


def test_mock_refresh_is_rate_limited(tmp_path):
    client = MockKaggleClient(remote_root=tmp_path)
    try:
        first = client.snapshot("default", refresh=True).observed_at.quota
        assert client.snapshot("default", refresh=True).observed_at.quota == first
    finally:
        client.close()
