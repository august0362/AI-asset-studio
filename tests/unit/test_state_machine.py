"""Every allowed and every disallowed job state transition (CONTRACTS §4)."""

from __future__ import annotations

import itertools
from datetime import timedelta

import pytest

from aas_backend.orchestrator.records import InternalState, JobRecord, RequestRecord
from aas_backend.orchestrator.state_machine import ALLOWED_TRANSITIONS, InvalidTransition, apply_transition
from aas_backend.orchestrator.worker import is_timed_out
from aas_backend.schemas import ComputeView, Execution, StatusEntry
from kaggle_connector.resources import ResourcePlan
from models.contracts import JOB_STATUSES, utc_now

ALLOWED = {
    ("created", "uploading"),
    ("created", "queued"),
    ("uploading", "queued"),
    ("queued", "running"),
    ("running", "downloading"),
    ("downloading", "completed"),
    ("created", "failed"),
    ("uploading", "failed"),
    ("queued", "failed"),
    ("running", "failed"),
    ("downloading", "failed"),
}


def record(status: str) -> JobRecord:
    now = utc_now()
    return JobRecord(
        contract_version="1.0",
        job_id="job_20261106T101500Z_a1b2c3",
        status=status,
        status_history=[StatusEntry(status=status, at=now)],
        request=RequestRecord(
            pipeline_type="text_to_2d",
            asset_category="weapon",
            model_id="mock-t2d-basic",
            prompt="x",
            output_format="png",
            options={},
            inputs=[],
        ),
        compute=ComputeView(
            profile_id="default",
            accelerator_id="cpu",
            resource_plan=ResourcePlan(
                contract_version="1.0",
                profile_id="default",
                accelerator_id="cpu",
                selection="recommended",
                fit="ok",
                required_seconds=645,
                estimate_basis={
                    "estimated_runtime_seconds": 30,
                    "safety_factor": 1.5,
                    "overhead_seconds": 600,
                },
                session_limit_seconds=43200,
                quota_remaining_seconds=None,
                candidates=[],
                warnings=[],
                errors=[],
            ),
        ),
        execution=Execution(backend="mock"),
        created_at=now,
        updated_at=now,
        internal=InternalState(
            client_request_id="c", original_request={}, timeout_seconds=645, deadline_seconds=806
        ),
    )


def test_transition_table_matches_the_contract():
    table = {(a, b) for a, targets in ALLOWED_TRANSITIONS.items() for b in targets}
    assert table == ALLOWED


@pytest.mark.parametrize("current,new", sorted(ALLOWED))
def test_allowed_transition_appends_history(current, new):
    later = utc_now() + timedelta(seconds=5)
    updated = apply_transition(record(current), new, later)
    assert updated.status == new
    assert [h.status for h in updated.status_history] == [current, new]
    assert updated.updated_at == later


@pytest.mark.parametrize("current,new", sorted(set(itertools.product(JOB_STATUSES, JOB_STATUSES)) - ALLOWED))
def test_disallowed_transition_is_rejected(current, new):
    original = record(current)
    with pytest.raises(InvalidTransition):
        apply_transition(original, new, utc_now())
    assert original.status == current and len(original.status_history) == 1


def test_timeout_rule_uses_required_seconds_times_1_25():
    assert not is_timed_out(1950 * 1.25, 1950 * 1.25)
    assert is_timed_out(1950 * 1.25 + 1, 1950 * 1.25)
