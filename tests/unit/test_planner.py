"""Deterministic planner: every branch of CONTRACTS §7.2."""

from __future__ import annotations

from datetime import timedelta

import pytest

from kaggle_connector.client import mock_profile
from kaggle_connector.resources import (
    QuotaReading,
    ResourceRequirements,
    build_snapshot,
    plan,
    required_seconds,
    run_timeout_seconds,
)
from kaggle_connector.resources.contracts import utc_now

GIB = 1024**3
NOW = utc_now()


def snapshot(remaining: float | None = 18.5, quota_age: int = 60, tpu: float | None = None):
    quota = QuotaReading(
        30.0,
        None if remaining is None else 30 - remaining,
        remaining,
        tpu,
        None,
        tpu,
        None,
        NOW - timedelta(seconds=quota_age),
        "mock",
    )
    return build_snapshot(
        mock_profile(),
        auth_status="authenticated",
        quota=quota,
        session=None,
        telemetry=None,
        telemetry_source="mock",
        now=NOW,
    )


def req(kinds=("gpu_cuda",), multi="optional", vram=12 * GIB, runtime=900):
    return ResourceRequirements(
        accelerator_kinds=list(kinds),
        multi_gpu=multi,
        minimum_gpu_vram_bytes=vram,
        estimated_runtime_seconds=runtime,
    )


def codes(items):
    return [i.code for i in items]


def test_required_seconds_formula():
    assert required_seconds(900, 1.5, 600) == 1950
    assert required_seconds(40000, 1.5, 600) == 60600
    assert required_seconds(None, 1.5, 600) is None


def test_user_selected_ok_matches_section_7_3():
    result = plan(req(), mock_profile(), snapshot(), "gpu_t4x2")
    assert (result.fit, result.selection, result.accelerator_id) == ("ok", "user_selected", "gpu_t4x2")
    assert result.required_seconds == 1950
    assert result.session_limit_seconds == 43200
    assert result.quota_remaining_seconds == 66600
    assert [c.accelerator_id for c in result.candidates] == ["gpu_t4x2"]
    assert result.errors == [] and result.warnings == []


def test_recommendation_takes_first_ok_in_profile_order():
    result = plan(req(), mock_profile(), snapshot(), None)
    assert (result.selection, result.accelerator_id, result.fit) == ("recommended", "gpu_p100", "ok")
    assert [c.accelerator_id for c in result.candidates] == ["gpu_p100", "gpu_t4x2"]


def test_model_preference_order_comes_first():
    result = plan(req(kinds=("cpu", "gpu_cuda"), vram=None, runtime=30), mock_profile(), snapshot(), None)
    assert result.accelerator_id == "cpu" and result.fit == "ok"
    assert result.quota_remaining_seconds is None  # no quota term for CPU


def test_no_compatible_accelerator():
    result = plan(req(kinds=("tpu",), multi="required"), mock_profile(), snapshot(), None)
    assert codes(result.errors) == ["MODEL_ACCELERATOR_INCOMPATIBLE"] and result.fit == "insufficient"


def test_user_choice_outside_candidates_is_incompatible():
    result = plan(req(), mock_profile(), snapshot(), "tpu_vm")
    assert codes(result.errors) == ["MODEL_ACCELERATOR_INCOMPATIBLE"]
    assert result.errors[0].details["compatible_accelerators"] == ["gpu_p100", "gpu_t4x2"]


def test_multi_gpu_required_drops_single_device_accelerators():
    result = plan(req(multi="required"), mock_profile(), snapshot(), None)
    assert [c.accelerator_id for c in result.candidates] == ["gpu_t4x2"]
    assert codes(plan(req(multi="required"), mock_profile(), snapshot(), "gpu_p100").errors) == [
        "MODEL_ACCELERATOR_INCOMPATIBLE"
    ]


def test_vram_insufficient_on_every_candidate_blocks_with_first_reasons():
    result = plan(req(vram=20 * GIB), mock_profile(), snapshot(), None)
    assert result.fit == "insufficient" and result.accelerator_id is None
    assert codes(result.errors) == ["COMPUTE_VRAM_INSUFFICIENT"]
    assert result.errors[0].details["accelerator_id"] == "gpu_p100"


def test_vram_between_devices_picks_the_one_that_fits():
    result = plan(req(vram=int(15.5 * GIB)), mock_profile(), snapshot(), None)
    assert result.accelerator_id == "gpu_p100" and result.fit == "ok"
    assert codes(plan(req(vram=int(15.5 * GIB)), mock_profile(), snapshot(), "gpu_t4x2").errors) == [
        "COMPUTE_VRAM_INSUFFICIENT"
    ]


def test_unknown_vram_is_a_warning_and_fit_unknown():
    result = plan(req(vram=None), mock_profile(), snapshot(), "gpu_t4x2")
    assert (
        result.fit == "unknown" and codes(result.warnings) == ["COMPUTE_VRAM_UNKNOWN"] and not result.errors
    )


def test_unknown_runtime_is_a_warning_and_timeout_uses_the_session_limit():
    result = plan(req(runtime=None), mock_profile(), snapshot(), "gpu_t4x2")
    assert result.required_seconds is None and result.fit == "unknown"
    assert "MODEL_RUNTIME_UNKNOWN" in codes(result.warnings)
    assert run_timeout_seconds(result) == 43200


def test_session_limit_exceeded():
    result = plan(req(runtime=40000), mock_profile(), snapshot(remaining=None), None)
    assert result.fit == "insufficient" and codes(result.errors) == ["COMPUTE_SESSION_LIMIT_EXCEEDED"]


@pytest.mark.parametrize("remaining,age", [(None, 60), (18.5, 601)])
def test_quota_null_or_stale_is_a_warning(remaining, age):
    result = plan(req(), mock_profile(), snapshot(remaining=remaining, quota_age=age), "gpu_t4x2")
    assert (
        result.fit == "unknown" and codes(result.warnings) == ["COMPUTE_QUOTA_UNKNOWN"] and not result.errors
    )


def test_quota_insufficient_is_retryable():
    result = plan(req(), mock_profile(), snapshot(remaining=0.3), "gpu_t4x2")
    assert codes(result.errors) == ["COMPUTE_QUOTA_INSUFFICIENT"] and result.errors[0].retryable
    assert result.errors[0].details == {
        "accelerator_id": "gpu_t4x2",
        "required_seconds": 1950,
        "quota_remaining_seconds": 1080,
    }


def test_recommendation_falls_back_to_unknown_when_nothing_is_ok():
    result = plan(req(vram=None), mock_profile(), snapshot(), None)
    assert result.accelerator_id == "gpu_p100" and result.fit == "unknown"


def test_run_timeout_is_capped_by_the_session_limit():
    result = plan(req(), mock_profile(), snapshot(), "gpu_t4x2")
    assert run_timeout_seconds(result) == 1950


def test_not_applicable_vram_gives_no_warning():
    """A null VRAM requirement that the model does not list as unknown is "not applicable" (CONTRACTS §2.1)."""
    result = plan(
        req(kinds=("cpu", "gpu_cuda"), vram=None, runtime=30),
        mock_profile(),
        snapshot(),
        "gpu_t4x2",
        vram_requirement_unknown=False,
    )
    assert result.fit == "ok" and not result.warnings and not result.errors


def test_declared_unknown_vram_still_warns():
    result = plan(req(vram=None), mock_profile(), snapshot(), "gpu_t4x2", vram_requirement_unknown=True)
    assert codes(result.warnings) == ["COMPUTE_VRAM_UNKNOWN"] and result.fit == "unknown"


def test_unknown_accelerator_vram_warns_even_with_a_known_requirement():
    profile = mock_profile()
    accelerators = [
        a.model_copy(update={"vram_bytes_per_device": None}) if a.accelerator_id == "gpu_t4x2" else a
        for a in profile.accelerators
    ]
    result = plan(req(), profile.model_copy(update={"accelerators": accelerators}), snapshot(), "gpu_t4x2")
    assert codes(result.warnings) == ["COMPUTE_VRAM_UNKNOWN"]
