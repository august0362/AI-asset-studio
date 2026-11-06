"""Kaggle CLI wrapper and parsers, on recorded redacted output (tests/fixtures/kaggle_cli, CLI 2.2.4)."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kaggle_connector.client.cli import (
    CliResult,
    KaggleCli,
    SecretRedactor,
    classify,
    parse_config_user,
    parse_dataset_status,
    parse_hours,
    parse_kernel_status,
    parse_log_blob,
    parse_push,
    parse_quota,
    payload_lines,
)
from kaggle_connector.client.kaggle_cli import STATUS_MAP, dataset_slug_for_slug
from kaggle_connector.jobs.kaggle_package import dataset_slug_for, slug_for
from kaggle_connector.resources.telemetry import parse_line
from tests.kaggle_fake import fixture

TOKEN = "KGAT_0123456789abcdef0123456789abcdef"


# --- quota (DF-05) -----------------------------------------------------------------------------------------------


def test_quota_json_is_parsed_from_recorded_output():
    values = parse_quota(fixture("quota.json.txt"))
    assert values is not None
    assert (values.gpu_total, values.gpu_used, values.gpu_remaining) == (30.0, 25.13, 4.87)
    assert (values.tpu_total, values.tpu_used, values.tpu_remaining) == (20.0, 0.0, 20.0)
    assert values.reset_at == datetime(2026, 11, 7, tzinfo=UTC)  # refreshAt has no zone: read as UTC


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "Warning: Looks like you're using an outdated `kaggle` version\n",
        "[{not json",
        '{"resource": "GPU"}',
        "[]",
        '[{"resource": "GPU", "used": "lots", "remaining": null, "total": "30.00h"}]',
    ],
)
def test_missing_or_malformed_quota_never_invents_values(stdout):
    values = parse_quota(stdout)
    if values is not None:  # only the last case parses: unreadable fields stay None
        assert values.gpu_total == 30.0
        assert values.gpu_used is None and values.gpu_remaining is None and values.tpu_total is None


def test_old_cli_without_quota_is_classified_unsupported():
    result = CliResult(2, "", fixture("quota_old_cli.stderr.txt"))
    assert classify(result).kind == "unsupported"
    assert parse_quota(result.stdout) is None


@pytest.mark.parametrize(
    ("value", "hours"), [("4.87h", 4.87), ("30.00h", 30.0), ("0h", 0.0), (2, 2.0), ("", None)]
)
def test_hours(value, hours):
    assert parse_hours(value) == hours


# --- status, push, config, datasets ------------------------------------------------------------------------------


def test_status_lines_map_to_remote_status():
    assert parse_kernel_status(fixture("status_running.txt")) == ("RUNNING", None)
    assert parse_kernel_status(fixture("status_complete.txt")) == ("COMPLETE", None)
    failed = (
        'a/aas-x has status "KernelWorkerStatus.ERROR"\nFailure message: "Your notebook tried to raise."\n'
    )
    assert parse_kernel_status(failed) == ("ERROR", "Your notebook tried to raise.")
    assert {STATUS_MAP[s] for s in ("QUEUED", "NEW_SCRIPT")} == {"queued"}
    assert STATUS_MAP["RUNNING"] == "running" and STATUS_MAP["COMPLETE"] == "complete"
    assert {STATUS_MAP[s] for s in ("ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED")} == {"error"}


def test_cannot_access_right_after_push_is_classified_as_denied():
    result = CliResult(
        1, fixture("status_cannot_access.stdout.txt"), fixture("status_cannot_access.stderr.txt")
    )
    assert parse_kernel_status(result.text) is None
    assert classify(result).kind == "denied"
    assert not classify(result).transient


def test_dropped_connection_is_transient():
    result = CliResult(1, fixture("network_error.stdout.txt"), fixture("network_error.stderr.txt"))
    failure = classify(result)
    assert failure.kind == "network" and failure.transient
    assert classify(CliResult(None, "", "timed out")).transient
    assert classify(CliResult(1, "", "429 Client Error: Too Many Requests")).kind == "rate_limited"
    assert classify(CliResult(1, "", "401 Client Error: Unauthorized")).kind == "auth"


def test_push_success_and_errors():
    pushed = parse_push(fixture("push_ok.txt"))
    assert pushed is not None
    assert (pushed.version, pushed.owner, pushed.slug) == (1, "aas-test-user", "aas-m3-spike-telemetry")
    assert parse_push("Kernel push error: Notebook not found") is None  # printed with exit code 0
    assert (
        parse_push("The following are not valid dataset sources ...\nKernel version 2 successfully pushed.")
        is None
    )


def test_config_view_resolves_the_account_name():
    assert parse_config_user(fixture("config_view.txt")) == ("aas-test-user", "ACCESS_TOKEN")
    assert parse_config_user("- username: None\n") == (None, None)


def test_dataset_status_word():
    assert (
        parse_dataset_status("Warning: Looks like you're using an outdated `kaggle` version x\nready\n")
        == "ready"
    )
    assert parse_dataset_status("blobs_received") == "blobs_received"
    assert parse_dataset_status("") is None


def test_version_warning_is_not_payload():
    assert payload_lines(fixture("status_running.txt")) == [
        'aas-test-user/aas-m3-spike-telemetry has status "KernelWorkerStatus.RUNNING"'
    ]


# --- logs and telemetry (DF-07) ----------------------------------------------------------------------------------


def test_log_blob_keeps_order_and_gpu0_gpu1_stay_separate():
    lines = parse_log_blob(fixture("logs_blob_t4x2.txt"))
    assert lines is not None and lines[0].startswith("AAS_SPIKE_INFO")
    telemetry = [line for line in lines if line.startswith("AAS_TELEMETRY ")]
    assert len(telemetry) == 2
    payload = json.loads(telemetry[0].split(" ", 1)[1])
    payload.pop("seq")  # the spike added a sequence number; the contract runner does not emit it
    parsed = parse_line("AAS_TELEMETRY " + json.dumps(payload))
    assert parsed.kind == "telemetry"
    gpus = parsed.telemetry.gpus
    assert [g.index for g in gpus] == [0, 1]
    assert all(g.vram_total_bytes == 16106127360 for g in gpus)


def test_log_blob_is_empty_while_running():
    assert parse_log_blob(fixture("logs_blob_running.txt")) is None


# --- slugs -------------------------------------------------------------------------------------------------------


def test_slugs_derive_from_the_job_id():
    job_id = "job_20261106T101500Z_a1b2c3"
    assert slug_for(job_id) == "aas-job-20261106t101500z-a1b2c3"
    assert dataset_slug_for(job_id) == "aas-in-job-20261106t101500z-a1b2c3"
    assert dataset_slug_for_slug(slug_for(job_id)) == dataset_slug_for(job_id)


# --- redaction and subprocess isolation (CONTRACTS §10) ------------------------------------------------------------


def test_redactor_removes_token_patterns_and_account_name():
    redact = SecretRedactor([TOKEN], ["Real-User"])
    text = f"token {TOKEN} other KGAT_zzz9 KAGGLE_KEY=abc123 https://kaggle.com/code/real-user/aas-x"
    out = redact(text)
    assert TOKEN not in out and "KGAT_" not in out and "abc123" not in out
    assert "real-user" not in out.lower() and "<kaggle-user>/aas-x" in out
    assert "real-user" in redact.secrets_only(text).lower()


def test_cli_subprocess_gets_only_its_own_credentials(monkeypatch):
    monkeypatch.setenv("KAGGLE_KEY", "inherited-key")
    monkeypatch.setenv("KAGGLE_USERNAME", "inherited-user")
    monkeypatch.setenv("AAS_PROFILE_OTHER_KAGGLE_API_TOKEN", "KGAT_other_profile_token")
    cli = KaggleCli(token=TOKEN, username="sunny-user", executable=sys.executable)
    script = "import json, os; print(json.dumps({k: v for k, v in os.environ.items() if 'KAGGLE' in k or 'AAS' in k}))"
    result = cli.run(["-c", script], timeout=30)
    assert result.ok, result.text
    env = json.loads(result.stdout)
    assert env["KAGGLE_API_TOKEN"] == "[REDACTED]"  # it was there, and the captured output is redacted
    assert env["KAGGLE_USERNAME"] == "sunny-user"
    assert "KAGGLE_KEY" not in env and "AAS_PROFILE_OTHER_KAGGLE_API_TOKEN" not in env
    config_dir = Path(env["KAGGLE_CONFIG_DIR"])
    assert config_dir.is_dir() and not any(config_dir.iterdir())
    assert TOKEN not in os.environ.get("KAGGLE_API_TOKEN", "")  # the parent process env is untouched
    cli.close()
    assert not config_dir.exists()


def test_cli_timeout_and_missing_executable(tmp_path: Path):
    cli = KaggleCli(token=TOKEN, username="u", executable=sys.executable)
    assert cli.run(["-c", "import time; time.sleep(5)"], timeout=0.5).timed_out
    cli.close()
    missing = KaggleCli(token=TOKEN, username="u", executable=str(tmp_path / "no-kaggle.exe"))
    result = missing.run(["quota"], timeout=5)
    assert result.returncode == 127 and TOKEN not in result.text
    missing.close()
