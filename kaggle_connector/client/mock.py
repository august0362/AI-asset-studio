"""MockKaggleClient (D-014): runs the real job package locally, with the same status sequence, ``AAS_*`` log lines
and output manifest as Kaggle, plus configurable resource scenarios and controlled failures.

It never contacts Kaggle and needs no credentials. Every value it reports is labeled ``source: "mock"``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Literal

from ..jobs.packaging import OUTPUT_DIR_NAME, write_package
from ..resources.catalog import PROVISIONAL_ACCELERATORS
from ..resources.contracts import (
    CONTRACT_VERSION,
    ComputeProfile,
    KaggleResourceSnapshot,
    TelemetrySample,
    utc_now,
)
from ..resources.snapshot import QuotaReading, ResourceMonitor, SessionState
from ..resources.telemetry import parse_line
from .base import ComputeError, KaggleJobSpec, RemoteRefNotFound, RemoteStatus

SCENARIOS = (
    "fresh",
    "no_session",
    "quota_missing",
    "telemetry_stale",
    "telemetry_unavailable",
    "gpu_split",
    "quota_low",
)
FAILURES = (
    "none",
    "upload",
    "submit",
    "kernel_error",
    "download",
    "download_transient",
    "status_transient",
    "invalid_artifact",
    "missing_manifest",
)
MOCK_PROFILE_ID = "default"
GIB = 1024**3
QUOTA_CACHE_SECONDS = 300
REFRESH_MIN_INTERVAL = 60
_SIMULATED_SESSION_SCENARIOS = {"fresh", "telemetry_stale", "telemetry_unavailable", "gpu_split"}
_KERNEL_ERROR_ENTRY = (
    "def main(arguments, input_dir, output_dir, progress):\n"
    '    raise RuntimeError("Simulated kernel failure (mock)")\n'
)


def mock_profile() -> ComputeProfile:
    return ComputeProfile(
        contract_version=CONTRACT_VERSION,
        profile_id=MOCK_PROFILE_ID,
        display_name="Mock Kaggle (no real account)",
        owner_label="mock",
        mode="mock",
        enabled=True,
        authorization_confirmed=True,
        accelerators=PROVISIONAL_ACCELERATORS,
    )


def mock_sample_fields(scenario: str, accelerator_id: str) -> dict:
    """Fixed telemetry values for a scenario. Clearly synthetic; reported with ``source: "mock"``."""
    fields = {"cpu_percent": 63.5, "ram_used_bytes": 9663676416, "ram_total_bytes": 33285996544}
    if accelerator_id == "gpu_t4x2":
        if scenario == "gpu_split":
            gpus = [
                {
                    "index": 0,
                    "name": "Tesla T4 (mock)",
                    "utilization_percent": 97.0,
                    "vram_used_bytes": 13421772800,
                    "vram_total_bytes": 16106127360,
                    "temperature_c": 71.0,
                },
                {
                    "index": 1,
                    "name": "Tesla T4 (mock)",
                    "utilization_percent": 4.0,
                    "vram_used_bytes": 524288000,
                    "vram_total_bytes": 16106127360,
                    "temperature_c": None,
                },
            ]
        else:
            gpus = [
                {
                    "index": 0,
                    "name": "Tesla T4 (mock)",
                    "utilization_percent": 72.0,
                    "vram_used_bytes": 9 * GIB,
                    "vram_total_bytes": 16106127360,
                    "temperature_c": 66.0,
                },
                {
                    "index": 1,
                    "name": "Tesla T4 (mock)",
                    "utilization_percent": 58.0,
                    "vram_used_bytes": 7 * GIB,
                    "vram_total_bytes": 16106127360,
                    "temperature_c": 62.0,
                },
            ]
        return {**fields, "gpu_source": "nvml", "gpus": gpus}
    if accelerator_id == "gpu_p100":
        gpus = [
            {
                "index": 0,
                "name": "Tesla P100 (mock)",
                "utilization_percent": 81.0,
                "vram_used_bytes": 11 * GIB,
                "vram_total_bytes": 17179869184,
                "temperature_c": 64.0,
            }
        ]
        return {**fields, "gpu_source": "nvml", "gpus": gpus}
    return {**fields, "gpu_source": "none", "gpus": []}


def _telemetry_config(scenario: str, accelerator_id: str) -> dict:
    if scenario == "telemetry_unavailable":
        return {"mode": "off"}
    return {
        "mode": "fixed",
        "interval_seconds": 5,
        "age_seconds": 120 if scenario == "telemetry_stale" else 0,
        "fixed_sample": mock_sample_fields(scenario, accelerator_id),
    }


@dataclass
class _Run:
    spec: KaggleJobSpec
    sandbox: Path
    state: RemoteStatus = "queued"
    lines: list[str] = field(default_factory=list)
    status_calls: int = 0
    download_calls: int = 0


class MockKaggleClient:
    mode: Literal["mock"] = "mock"

    def __init__(
        self,
        *,
        scenario: str = "fresh",
        failure: str = "none",
        queue_seconds: float = 1.0,
        run_seconds: float = 4.0,
        remote_root: Path | None = None,
        python_executable: str | None = None,
        clock=utc_now,
    ) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown mock scenario {scenario!r}; expected one of {SCENARIOS}")
        if failure not in FAILURES:
            raise ValueError(f"unknown mock failure {failure!r}; expected one of {FAILURES}")
        self.scenario = scenario
        self.failure = failure
        self.queue_seconds = queue_seconds
        self.run_seconds = run_seconds
        self._clock = clock
        self._python = python_executable or sys.executable
        self._owns_root = remote_root is None
        self._root = Path(tempfile.mkdtemp(prefix="aas-mock-remote-")) if remote_root is None else remote_root
        self._root = self._root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._runs: dict[str, _Run] = {}
        self._profile = mock_profile()
        self.monitor = ResourceMonitor(
            self._profile, session_source="mock", telemetry_source="mock", clock=clock
        )
        self.monitor.set_auth("authenticated")
        self._last_refresh = None

    # --- profiles and snapshots ------------------------------------------------------------------------------

    def profiles(self) -> list[ComputeProfile]:
        return [self._profile]

    def _read_quota(self) -> QuotaReading | None:
        if self.scenario == "quota_missing":
            return None
        used, remaining = (29.7, 0.3) if self.scenario == "quota_low" else (11.5, 18.5)
        return QuotaReading(
            gpu_total_hours=30.0,
            gpu_used_hours=used,
            gpu_remaining_hours=remaining,
            tpu_total_hours=None,
            tpu_used_hours=None,
            tpu_remaining_hours=None,
            reset_at=None,
            observed_at=self._clock(),
            source="mock",
        )

    def snapshot(self, profile_id: str, *, refresh: bool = False) -> KaggleResourceSnapshot:
        if profile_id != MOCK_PROFILE_ID:
            raise KeyError(profile_id)
        now = self._clock()
        with self._lock:
            allow_refresh = refresh and (
                self._last_refresh is None
                or (now - self._last_refresh).total_seconds() >= REFRESH_MIN_INTERVAL
            )
            if allow_refresh:
                self._last_refresh = now
        quota = self.monitor.quota
        stale_cache = quota is None or (now - quota.observed_at).total_seconds() > QUOTA_CACHE_SECONDS
        if allow_refresh or stale_cache:
            self.monitor.set_quota(self._read_quota())
        if self.monitor.session is None and self.scenario in _SIMULATED_SESSION_SCENARIOS:
            session = SessionState("running", "gpu_t4x2", now - timedelta(minutes=3), now, "mock")
            config = _telemetry_config(self.scenario, "gpu_t4x2")
            telemetry = None
            if config["mode"] == "fixed":
                telemetry = TelemetrySample.model_validate(
                    {
                        "v": 1,
                        "job_id": "mock-session",
                        "at": now - timedelta(seconds=config["age_seconds"]),
                        **config["fixed_sample"],
                    }
                )
            return self.monitor.snapshot(session=session, telemetry=telemetry, override_session=True)
        return self.monitor.snapshot()

    # --- job execution ---------------------------------------------------------------------------------------

    def _sandbox(self, job_id: str) -> Path:
        return self._root / job_id

    def upload_inputs(self, spec: KaggleJobSpec) -> None:
        if self.failure == "upload":
            raise ComputeError(
                "KAGGLE_UPLOAD_FAILED", "Simulated input upload failure (mock).", retryable=True
            )
        inputs = self._sandbox(spec.job_id) / "inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        for path in spec.input_files:
            shutil.copyfile(path, inputs / path.name)

    def submit(self, spec: KaggleJobSpec) -> str:
        if self.failure == "submit":
            raise ComputeError(
                "KAGGLE_SUBMIT_FAILED", "Simulated kernel push failure (mock).", retryable=True
            )
        sandbox = self._sandbox(spec.job_id)
        inputs = sandbox / "inputs"
        if spec.requires_input_upload and not inputs.is_dir():
            raise ComputeError("KAGGLE_SUBMIT_FAILED", "Inputs were not uploaded before submission.")
        inputs.mkdir(parents=True, exist_ok=True)
        working = sandbox / "working"
        working.mkdir(parents=True, exist_ok=True)
        package = sandbox / "package"
        write_package(
            spec,
            package,
            input_dir=str(inputs),
            output_dir=str(working / OUTPUT_DIR_NAME),
            telemetry=_telemetry_config(self.scenario, spec.accelerator_id),
        )
        if self.failure == "kernel_error":
            (package / "entry.py").write_text(_KERNEL_ERROR_ENTRY, encoding="utf-8")
        ref = f"mock/aas-runner/{spec.job_id}"
        run = _Run(spec=spec, sandbox=sandbox)
        with self._lock:
            self._runs[ref] = run
        self.monitor.session_submitted(spec.job_id, spec.accelerator_id)
        threading.Thread(
            target=self._execute, args=(run,), name=f"mock-run-{spec.job_id}", daemon=True
        ).start()
        return ref

    def _scrub(self, line: str) -> str:
        """Remote logs must not expose local paths: the sandbox plays the role of /kaggle."""
        for variant in {str(self._root), self._root.as_posix(), str(self._root).replace("\\", "\\\\")}:
            line = line.replace(variant, "<remote>")
        return line

    def _execute(self, run: _Run) -> None:
        if self._stop.wait(self.queue_seconds):
            return
        with self._lock:
            run.state = "running"
        started = time.monotonic()
        package = run.sandbox / "package"
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("KAGGLE", "AAS_PROFILE"))}
        env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        process = subprocess.Popen(
            [self._python, str(package / "runner.py"), str(package / "job.json")],
            cwd=run.sandbox / "working",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        killer = threading.Timer(run.spec.timeout_seconds, process.kill)
        killer.daemon = True
        killer.start()
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                line = self._scrub(raw.rstrip("\r\n"))
                parsed = parse_line(line)
                if parsed.kind == "telemetry" and parsed.telemetry is not None:
                    self.monitor.telemetry_observed(parsed.telemetry)
                with self._lock:
                    run.lines.append(line)
            code = process.wait()
        finally:
            killer.cancel()
        remaining = self.run_seconds - (time.monotonic() - started)
        if remaining > 0 and self._stop.wait(remaining):
            return
        output = run.sandbox / "working" / OUTPUT_DIR_NAME
        if code == 0 and self.failure == "invalid_artifact":
            self._corrupt_primary(run, output)
        if self.failure == "missing_manifest":
            (output / "manifest.json").unlink(missing_ok=True)
        with self._lock:
            run.state = "complete" if code == 0 else "error"

    @staticmethod
    def _corrupt_primary(run: _Run, output: Path) -> None:
        primary = next((o for o in run.spec.expected_outputs if o.required), None)
        manifest_path = output / "manifest.json"
        if primary is None or not manifest_path.is_file():
            return
        garbage = b"not a valid file (simulated corrupt output)"
        (output / primary.name).write_bytes(garbage)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["outputs"]:
            if entry["name"] == primary.name:
                entry.update(size_bytes=len(garbage), sha256=hashlib.sha256(garbage).hexdigest())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def _get(self, remote_ref: str) -> _Run:
        with self._lock:
            run = self._runs.get(remote_ref)
        if run is None:
            raise RemoteRefNotFound(remote_ref)
        return run

    def status(self, remote_ref: str) -> RemoteStatus:
        run = self._get(remote_ref)
        with self._lock:
            run.status_calls += 1
            calls, state = run.status_calls, run.state
        if self.failure == "status_transient" and calls <= 2:
            raise ComputeError(
                "KAGGLE_NETWORK_ERROR", "Simulated network timeout (mock).", transient=True, retryable=True
            )
        session = {"queued": "queued", "running": "running", "complete": "finished", "error": "failed"}[state]
        self.monitor.session_observed(run.spec.job_id, session)
        return state

    def logs(self, remote_ref: str, offset: int) -> tuple[list[str], int]:
        run = self._get(remote_ref)
        with self._lock:
            lines = run.lines[offset:]
            return lines, offset + len(lines)

    def download(self, remote_ref: str, dest_dir: Path) -> None:
        run = self._get(remote_ref)
        with self._lock:
            run.download_calls += 1
            calls, state = run.download_calls, run.state
        if self.failure == "download" or (self.failure == "download_transient" and calls <= 2):
            raise ComputeError(
                "ARTIFACT_DOWNLOAD_FAILED",
                "Simulated download failure (mock).",
                transient=True,
                retryable=True,
            )
        if state != "complete":
            raise ComputeError("ARTIFACT_DOWNLOAD_FAILED", "The run has not completed.", retryable=True)
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(run.sandbox / "working", dest_dir, dirs_exist_ok=True)

    def close(self) -> None:
        self._stop.set()
        if self._owns_root:
            shutil.rmtree(self._root, ignore_errors=True)
