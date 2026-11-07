"""Contract v1.2 fixtures (CONTRACTS §14): every fixture validates against its model and round-trips exactly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aas_backend.schemas import (
    BulkDeleteResult,
    ErrorResponse,
    GenerationResult,
    JobList,
    RunGroup,
)
from models.contracts import ErrorItem

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "v12"
MODELS = {
    "job_held": GenerationResult,
    "job_waiting": GenerationResult,
    "job_grouped": GenerationResult,
    "job_failed_prompt_too_long": GenerationResult,
    "job_list": JobList,
    "run_group": RunGroup,
    "bulk_delete": BulkDeleteResult,
    "error_job_already_started": ErrorResponse,
    "error_job_group_invalid": ErrorResponse,
    "warning_runtime_exceeds_estimate": ErrorItem,
}


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_every_fixture_has_a_model():
    assert {p.stem for p in FIXTURES.glob("*.json")} == set(MODELS)


@pytest.mark.parametrize("name", sorted(MODELS))
def test_fixture_validates_and_round_trips(name):
    payload = load(name)
    assert MODELS[name].model_validate(payload).model_dump(mode="json") == payload


def test_fixtures_show_each_condition_inside_created():
    assert load("job_held")["scheduling"]["queue_state"] == "held"
    assert load("job_held")["scheduling"]["run_requested_at"] is None
    waiting = load("job_waiting")
    assert waiting["status"] == "created" and waiting["scheduling"]["queue_position"] == 1
    grouped = load("job_grouped")["scheduling"]
    assert grouped["group_id"] == load("run_group")["group_id"] and grouped["gpu_index"] == 0
    assert all("scheduling" in job for job in load("job_list")["jobs"])


def test_fixtures_carry_the_new_codes():
    assert load("error_job_already_started")["errors"][0]["code"] == "JOB_ALREADY_STARTED"
    invalid = load("error_job_group_invalid")["errors"][0]
    assert invalid["code"] == "JOB_GROUP_INVALID" and invalid["details"]["reason"] == "not_held"
    error = load("job_failed_prompt_too_long")["error"]
    assert error["code"] == "MODEL_PROMPT_TOO_LONG"
    assert {"tokens", "max_tokens"} <= set(error["details"])
    assert load("warning_runtime_exceeds_estimate")["code"] == "MODEL_RUNTIME_EXCEEDS_ESTIMATE"
    assert load("bulk_delete")["refused"][0]["code"] == "JOB_NOT_FOUND"
