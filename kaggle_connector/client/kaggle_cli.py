"""KaggleCliClient (M3): the ComputeClient for one authorized Kaggle account, through the official CLI (D-007).

* Exactly one profile is enabled (D-008, D-025). Other listed profiles are shown as disabled and their credentials
  are never loaded. Nothing here selects, rotates, pools or fails over between profiles.
* ``remote_ref`` is ``<profile_id>/<kernel slug>``: it identifies the run without storing the Kaggle account name.
* One private kernel per job (``aas-<job id>``) and, when the job has inputs, one private dataset per job
  (``aas-in-<job id>``), deleted by :meth:`release` once the job is terminal (DF-08).
* Submission is never retried here or by the worker. Reads raise ``ComputeError(transient=True)`` for network and
  rate-limit failures so the worker applies its bounded retries (D-015).
* Quota comes only from ``kaggle quota --format json`` (D-009); live telemetry only from ``AAS_TELEMETRY`` lines in
  ``kaggle kernels logs -f`` (D-010). Unknown values stay ``null``.
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..jobs.kaggle_package import dataset_slug_for, slug_for, write_dataset_package, write_kernel_package
from ..jobs.packaging import OUTPUT_DIR_NAME
from ..resources.catalog import KAGGLE_ACCELERATORS, KAGGLE_MACHINE_SHAPES
from ..resources.contracts import CONTRACT_VERSION, ComputeProfile, KaggleResourceSnapshot, utc_now
from ..resources.snapshot import QuotaReading, ResourceMonitor
from ..resources.telemetry import parse_line
from .base import ComputeError, KaggleJobSpec, RemoteRefNotFound, RemoteStatus
from .cli import (
    CliResult,
    CliRunner,
    KaggleCli,
    LineStream,
    SecretRedactor,
    classify,
    is_noise,
    parse_config_user,
    parse_dataset_status,
    parse_kernel_status,
    parse_log_blob,
    parse_push,
    parse_quota,
)

log = logging.getLogger("kaggle_connector")

QUOTA_CACHE_SECONDS = 300  # D-009
REFRESH_MIN_INTERVAL = 60
STATUS_GRACE_SECONDS = 180  # "Cannot access kernel" right after a push is eventual consistency, not a failure
DATASET_READY_TIMEOUT = 600
DATASET_POLL_SECONDS = 5
FOLLOWER_JOIN_SECONDS = 30
READ_TIMEOUT = 90
PUSH_TIMEOUT = 300
TRANSFER_TIMEOUT = 900

TEST_FAILURE_ENTRY = (
    "def main(arguments, input_dir, output_dir, progress):\n"
    "    progress('inference', 5, 'Test switch AAS_KAGGLE_TEST_FAILURE=kernel_error is on: failing on purpose')\n"
    "    raise RuntimeError('Deliberate test failure (AAS_KAGGLE_TEST_FAILURE=kernel_error)')\n"
)

STATUS_MAP: dict[str, RemoteStatus] = {
    "QUEUED": "queued",
    "NEW_SCRIPT": "queued",
    "RUNNING": "running",
    "COMPLETE": "complete",
    "ERROR": "error",
    "CANCEL_REQUESTED": "error",
    "CANCEL_ACKNOWLEDGED": "error",
}
_SESSION = {"queued": "queued", "running": "running", "complete": "finished", "error": "failed"}


@dataclass(frozen=True)
class KaggleProfileConfig:
    """One Kaggle account from ``.env``. Credentials are present only for the enabled profile."""

    profile_id: str
    username: str
    authorization_confirmed: bool
    enabled: bool
    token: str | None = field(default=None, repr=False)
    legacy_key: str | None = field(default=None, repr=False)
    display_name: str | None = None
    owner_label: str | None = None

    def public(self) -> ComputeProfile:
        return ComputeProfile(
            contract_version=CONTRACT_VERSION,
            profile_id=self.profile_id,
            display_name=self.display_name or f"Kaggle ({self.profile_id})",
            owner_label=self.owner_label or self.profile_id,
            mode="kaggle",
            enabled=self.enabled,
            authorization_confirmed=self.authorization_confirmed,
            accelerators=KAGGLE_ACCELERATORS,
        )


@dataclass
class _Account:
    config: KaggleProfileConfig
    cli: CliRunner
    monitor: ResourceMonitor
    redact: SecretRedactor
    owner: str | None = None  # the account name the credentials resolve to (``kaggle config view``)
    last_refresh: float | None = None
    refresh_lock: threading.Lock = field(default_factory=threading.Lock)


@dataclass
class _Run:
    profile_id: str
    slug: str
    job_id: str | None
    submitted_at: float | None  # monotonic; None for a run resumed after a backend restart
    dataset_ref: str | None = None
    lines: list[str] = field(default_factory=list)  # what logs() returns: remote lines plus local notes
    remote_lines: list[str] = field(default_factory=list)  # remote lines only, aligned with the final blob
    stream: LineStream | None = None
    follower: threading.Thread | None = None
    final_logs_merged: bool = False
    failure_noted: bool = False
    state: RemoteStatus = "queued"


class KaggleCliClient:
    mode: Literal["kaggle"] = "kaggle"

    def __init__(
        self,
        profiles: list[KaggleProfileConfig],
        *,
        cli_factory: Callable[[KaggleProfileConfig, SecretRedactor], CliRunner] | None = None,
        executable: str | None = None,
        work_root: Path | None = None,
        clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        background_refresh: bool = True,
        dataset_poll_seconds: float = DATASET_POLL_SECONDS,
        test_failure: Literal["kernel_error"] | None = None,
    ) -> None:
        enabled = [p for p in profiles if p.enabled]
        if len(enabled) != 1:
            raise ValueError("exactly one Kaggle compute profile must be enabled (D-008)")
        profile = enabled[0]
        if not profile.authorization_confirmed:
            raise ValueError(f"profile {profile.profile_id} is not authorized (AUTHORIZATION_CONFIRMED=true)")
        if not (profile.token or profile.legacy_key):
            raise ValueError(f"profile {profile.profile_id} has no Kaggle API token")
        self._configs = profiles
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._dataset_poll = dataset_poll_seconds
        self._test_failure = test_failure
        self._owns_root = work_root is None
        self._root = Path(tempfile.mkdtemp(prefix="aas-kaggle-")) if work_root is None else work_root
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._runs: dict[str, _Run] = {}
        self._datasets: dict[str, str] = {}  # job_id -> owner/dataset-slug

        redact = SecretRedactor([s for s in (profile.token, profile.legacy_key) if s], [profile.username])
        if cli_factory is None:

            def cli_factory(config: KaggleProfileConfig, red: SecretRedactor) -> CliRunner:
                return KaggleCli(
                    token=config.token,
                    username=config.username,
                    legacy_key=config.legacy_key,
                    executable=executable,
                    redact=red,
                )

        public = profile.public()
        monitor = ResourceMonitor(
            public, session_source="kaggle_cli_status", telemetry_source="notebook_telemetry", clock=clock
        )
        self._account = _Account(
            config=profile, cli=cli_factory(profile, redact), monitor=monitor, redact=redact
        )
        self._refresher: threading.Thread | None = None
        if background_refresh:
            self._refresher = threading.Thread(
                target=self._refresh_loop, name="aas-kaggle-refresh", daemon=True
            )
            self._refresher.start()

    # --- profiles, auth, quota -----------------------------------------------------------------------------------

    def profiles(self) -> list[ComputeProfile]:
        return [p.public() for p in self._configs]

    def redaction_terms(self) -> list[str]:
        config = self._account.config
        terms = [t for t in (config.token, config.legacy_key, config.username, self._account.owner) if t]
        return sorted(set(terms), key=len, reverse=True)

    def _acct(self, profile_id: str) -> _Account:
        if profile_id != self._account.config.profile_id:
            raise KeyError(profile_id)
        return self._account

    def _refresh_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh(self._account.config.profile_id)
            except Exception:  # never let the refresher die; the snapshot reports what is unknown
                log.exception("Kaggle quota refresh failed")
            if self._stop.wait(QUOTA_CACHE_SECONDS):
                return

    def _check_auth(self, acct: _Account) -> bool:
        """``kaggle config view`` resolves the account the credentials belong to. Returns True if authenticated."""
        result = acct.cli.run(["config", "view"], timeout=READ_TIMEOUT)
        if not result.ok:
            kind = classify(result).kind
            acct.monitor.set_auth("invalid_credentials" if kind in ("auth", "denied") else "unknown")
            return False
        user, _method = parse_config_user(result.stdout)
        if user is None:
            acct.monitor.set_auth("unknown")
            return False
        if user.lower() != acct.config.username.lower():
            # A wrong or swapped token (another person's account) must never be used under this profile.
            acct.monitor.set_auth(
                "invalid_credentials",
                f"The Kaggle token of profile '{acct.config.profile_id}' belongs to a different account than "
                f"AAS_PROFILE_{acct.config.profile_id.upper()}_KAGGLE_USERNAME. Fix the username or the token "
                "in .env.",
            )
            return False
        acct.owner = user
        acct.redact.add_user(user)
        return True

    def _read_quota(self, acct: _Account) -> tuple[QuotaReading | None, bool]:
        """(reading or None, credentials rejected)."""
        result = acct.cli.run(["quota", "--format", "json"], timeout=READ_TIMEOUT)
        if not result.ok:
            return None, classify(result).kind == "auth"
        values = parse_quota(result.stdout)
        if values is None:
            return None, False
        return (
            QuotaReading(
                gpu_total_hours=values.gpu_total,
                gpu_used_hours=values.gpu_used,
                gpu_remaining_hours=values.gpu_remaining,
                tpu_total_hours=values.tpu_total,
                tpu_used_hours=values.tpu_used,
                tpu_remaining_hours=values.tpu_remaining,
                reset_at=values.reset_at,
                observed_at=self._clock(),
                source="kaggle_cli_quota",
            ),
            False,
        )

    def refresh(self, profile_id: str, *, force: bool = False) -> bool:
        """Re-check auth and quota now. Rate-limited to one call per minute. Returns True if it ran."""
        acct = self._acct(profile_id)
        with acct.refresh_lock:
            now = self._monotonic()
            if not force and acct.last_refresh is not None and now - acct.last_refresh < REFRESH_MIN_INTERVAL:
                return False
            acct.last_refresh = now
            if not self._check_auth(acct):
                acct.monitor.set_quota(None)
                return True
            reading, rejected = self._read_quota(acct)
            if rejected:
                acct.monitor.set_auth("invalid_credentials")
            else:
                acct.monitor.set_auth("authenticated")
            acct.monitor.set_quota(reading)
            return True

    def snapshot(self, profile_id: str, *, refresh: bool = False) -> KaggleResourceSnapshot:
        """Cached by default (validation must not contact Kaggle). ``refresh`` re-reads auth and quota."""
        acct = self._acct(profile_id)
        if refresh:
            self.refresh(profile_id)
        return acct.monitor.snapshot()

    # --- runs ----------------------------------------------------------------------------------------------------

    def _require_owner(self, acct: _Account) -> str:
        if acct.owner is None:
            self.refresh(acct.config.profile_id, force=True)
        if acct.owner is None or acct.monitor.auth_status != "authenticated":
            raise ComputeError("KAGGLE_AUTH_FAILED", "The Kaggle credentials could not be verified.")
        return acct.owner

    def _fail(self, result: CliResult, code: str, message: str, *, read: bool) -> ComputeError:
        failure = classify(result)
        if failure.kind == "auth":
            return ComputeError("KAGGLE_AUTH_FAILED", "Kaggle rejected the credentials of this profile.")
        if failure.kind == "rate_limited":
            return ComputeError(
                "KAGGLE_RATE_LIMITED", "Kaggle rate-limited the request.", transient=read, retryable=True
            )
        if failure.kind == "network":
            return ComputeError(
                "KAGGLE_NETWORK_ERROR", "Kaggle could not be reached.", transient=read, retryable=True
            )
        if failure.kind == "quota":
            return ComputeError("KAGGLE_QUOTA_EXHAUSTED", "Kaggle refused the run because of quota.")
        return ComputeError(code, message, retryable=True)

    def upload_inputs(self, spec: KaggleJobSpec) -> None:
        if not spec.input_files:
            return
        acct = self._acct(spec.profile_id)
        owner = self._require_owner(acct)
        slug = dataset_slug_for(spec.job_id)
        ref = f"{owner}/{slug}"
        folder = self._root / spec.job_id / "dataset"
        try:
            write_dataset_package(spec, folder, owner=owner, slug=slug)
            result = acct.cli.run(["datasets", "create", "-p", str(folder), "-q"], timeout=TRANSFER_TIMEOUT)
            if not result.ok or "is being created" not in result.text:
                raise self._fail(
                    result, "KAGGLE_UPLOAD_FAILED", "Kaggle did not accept the input dataset.", read=False
                )
            with self._lock:
                self._datasets[spec.job_id] = ref
            try:
                self._wait_dataset_ready(acct, ref)
            except ComputeError:
                self._discard_dataset(acct, spec.job_id)
                raise
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _wait_dataset_ready(self, acct: _Account, ref: str) -> None:
        deadline = self._monotonic() + DATASET_READY_TIMEOUT
        errors = 0
        while True:
            result = acct.cli.run(["datasets", "status", ref], timeout=READ_TIMEOUT)
            status = parse_dataset_status(result.stdout) if result.ok else None
            if status == "ready":
                return
            if status in ("failed", "deleted"):
                raise ComputeError(
                    "KAGGLE_UPLOAD_FAILED", "Kaggle could not process the input dataset.", retryable=True
                )
            if status is None:
                errors += 1
                if errors > 3 and not classify(result).transient:
                    raise self._fail(
                        result, "KAGGLE_UPLOAD_FAILED", "The input dataset status is unknown.", read=False
                    )
            if self._monotonic() > deadline:
                raise ComputeError(
                    "KAGGLE_UPLOAD_FAILED", "The input dataset was not ready in time.", retryable=True
                )
            if self._stop.wait(self._dataset_poll):
                raise ComputeError("KAGGLE_UPLOAD_FAILED", "The backend is stopping.", retryable=True)

    def submit(self, spec: KaggleJobSpec) -> str:
        acct = self._acct(spec.profile_id)
        owner = self._require_owner(acct)
        if spec.accelerator_id not in KAGGLE_MACHINE_SHAPES:
            raise ComputeError(
                "KAGGLE_SUBMIT_FAILED",
                f"Accelerator {spec.accelerator_id} is not available on Kaggle profiles.",
            )
        with self._lock:
            dataset_ref = self._datasets.get(spec.job_id)
        if spec.requires_input_upload and dataset_ref is None:
            raise ComputeError("KAGGLE_SUBMIT_FAILED", "Inputs were not uploaded before submission.")
        shape = KAGGLE_MACHINE_SHAPES[spec.accelerator_id]
        slug = slug_for(spec.job_id)
        folder = self._root / spec.job_id / "kernel"
        try:
            if self._test_failure == "kernel_error":
                spec = dataclasses.replace(spec, entrypoint_file=self._failing_entry(spec.job_id))
            write_kernel_package(
                spec, folder, owner=owner, slug=slug, dataset_ref=dataset_ref, gpu=shape is not None
            )
            args = ["kernels", "push", "-p", str(folder), "--timeout", str(int(spec.timeout_seconds))]
            if shape:
                args += ["--accelerator", shape]
            result = acct.cli.run(args, timeout=PUSH_TIMEOUT)
        finally:
            shutil.rmtree(folder.parent, ignore_errors=True)
        pushed = parse_push(result.text) if result.ok else None
        if pushed is None:
            # Never retried automatically: a push that timed out may still have started a run (D-015).
            # The job fails without a remote reference, so its input dataset is removed now.
            self._discard_dataset(acct, spec.job_id)
            raise self._fail(
                result, "KAGGLE_SUBMIT_FAILED", "Kaggle did not accept the kernel push.", read=False
            )
        if pushed.slug and pushed.slug != slug:
            slug = pushed.slug
        ref = f"{acct.config.profile_id}/{slug}"
        run = _Run(acct.config.profile_id, slug, spec.job_id, self._monotonic(), dataset_ref=dataset_ref)
        with self._lock:
            self._runs[ref] = run
        acct.monitor.session_submitted(spec.job_id, spec.accelerator_id)
        return ref

    def _failing_entry(self, job_id: str) -> Path:
        """AAS_KAGGLE_TEST_FAILURE=kernel_error: the real notebook runs on Kaggle and fails on purpose."""
        path = self._root / job_id / "test_failure_entry.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(TEST_FAILURE_ENTRY, encoding="utf-8")
        return path

    def _discard_dataset(self, acct: _Account, job_id: str) -> None:
        with self._lock:
            ref = self._datasets.pop(job_id, None)
        if ref is not None:
            self._delete_dataset(acct, ref)

    def _delete_dataset(self, acct: _Account, ref: str) -> None:
        result = acct.cli.run(["datasets", "delete", ref, "-y"], timeout=READ_TIMEOUT)
        if not result.ok:
            log.warning("could not delete an input dataset (%s)", classify(result).kind)

    def _run_for(self, remote_ref: str) -> tuple[_Account, _Run]:
        profile_id, _, slug = remote_ref.partition("/")
        try:
            acct = self._acct(profile_id)
        except KeyError:
            raise RemoteRefNotFound(remote_ref) from None
        if not slug.startswith("aas-"):
            raise RemoteRefNotFound(remote_ref)
        with self._lock:
            run = self._runs.get(remote_ref)
            if run is None:  # resumed after a backend restart: the reference alone identifies the kernel
                run = self._runs[remote_ref] = _Run(profile_id, slug, None, None)
        return acct, run

    def _kernel(self, acct: _Account, run: _Run) -> str:
        owner = acct.owner or self._require_owner(acct)
        return f"{owner}/{run.slug}"

    def status(self, remote_ref: str) -> RemoteStatus:
        acct, run = self._run_for(remote_ref)
        result = acct.cli.run(["kernels", "status", self._kernel(acct, run)], timeout=READ_TIMEOUT)
        parsed = parse_kernel_status(result.text) if result.ok else None
        if parsed is None:
            failure = classify(result)
            in_grace = (
                run.submitted_at is not None and self._monotonic() - run.submitted_at < STATUS_GRACE_SECONDS
            )
            if failure.kind == "denied" and in_grace:
                return "queued"
            if failure.kind == "denied":
                raise ComputeError("KAGGLE_AUTH_FAILED", "Kaggle denied access to this run's kernel.")
            if failure.kind == "other":
                raise ComputeError(
                    "KAGGLE_NETWORK_ERROR",
                    "Kaggle returned an unreadable status.",
                    transient=True,
                    retryable=True,
                )
            raise self._fail(result, "KAGGLE_NETWORK_ERROR", "The run status could not be read.", read=True)
        raw, failure_message = parsed
        state = STATUS_MAP.get(raw)
        if state is None:
            raise ComputeError(
                "KAGGLE_NETWORK_ERROR", f"Unrecognized Kaggle status {raw}.", transient=True, retryable=True
            )
        run.state = state
        if run.job_id:
            acct.monitor.session_observed(run.job_id, _SESSION[state])
        if state == "running":
            self._start_follower(acct, run)
        elif state in ("complete", "error"):
            self._merge_final_logs(acct, run)
            if failure_message and not run.failure_noted:
                run.failure_noted = True
                self._append(acct, run, [f"Kaggle reported: {failure_message}"], remote=False)
        return state

    # --- logs ----------------------------------------------------------------------------------------------------

    def _append(self, acct: _Account, run: _Run, lines: list[str], *, remote: bool = True) -> None:
        clean = [acct.redact(line) for line in lines if not is_noise(line)]
        with self._lock:
            run.lines.extend(clean)
            if remote:
                run.remote_lines.extend(clean)
        for line in clean:
            parsed = parse_line(line)
            if parsed.kind == "telemetry" and parsed.telemetry is not None:
                acct.monitor.telemetry_observed(parsed.telemetry)

    def _start_follower(self, acct: _Account, run: _Run) -> None:
        with self._lock:
            if run.follower is not None or run.final_logs_merged:
                return
            run.follower = threading.Thread(
                target=self._follow, args=(acct, run), name=f"aas-logs-{run.slug}", daemon=True
            )
        run.follower.start()

    def _follow(self, acct: _Account, run: _Run) -> None:
        """``logs -f`` replays the session from its start and ends at END_OF_LOG (measured latency ~1 s, DF-07)."""
        try:
            stream = acct.cli.follow(["kernels", "logs", "-f", self._kernel(acct, run)])
        except (OSError, ComputeError):
            return
        run.stream = stream
        try:
            for line in stream:
                if self._stop.is_set() or run.final_logs_merged:
                    break
                self._append(acct, run, [line])
        except Exception:  # the live stream is best-effort; the final log blob is authoritative
            log.warning("Kaggle log stream for %s ended unexpectedly", run.slug)
        finally:
            stream.terminate()

    def _merge_final_logs(self, acct: _Account, run: _Run) -> None:
        """After the run ends, the persisted log blob fills in whatever the live stream missed."""
        if run.final_logs_merged:
            return
        if run.follower is not None:
            run.follower.join(timeout=FOLLOWER_JOIN_SECONDS)
            if run.follower.is_alive() and run.stream is not None:
                run.stream.terminate()
                run.follower.join(timeout=5)
        result = acct.cli.run(["kernels", "logs", self._kernel(acct, run)], timeout=READ_TIMEOUT)
        lines = parse_log_blob(result.stdout) if result.ok else None
        if lines is None:
            return  # best-effort: try again on the next status or download
        lines = [acct.redact(line) for line in lines if not is_noise(line)]
        with self._lock:
            have = len(run.remote_lines)
            missing = lines[have:] if lines[:have] == run.remote_lines else []
            run.final_logs_merged = True
        if missing:
            self._append(acct, run, missing)

    def logs(self, remote_ref: str, offset: int) -> tuple[list[str], int]:
        _acct, run = self._run_for(remote_ref)
        with self._lock:
            lines = run.lines[offset:]
            return lines, offset + len(lines)

    # --- outputs and cleanup -------------------------------------------------------------------------------------

    def download(self, remote_ref: str, dest_dir: Path) -> None:
        acct, run = self._run_for(remote_ref)
        dest_dir.mkdir(parents=True, exist_ok=True)
        result = acct.cli.run(
            ["kernels", "output", self._kernel(acct, run), "-p", str(dest_dir), "-o", "--page-size", "200"],
            timeout=TRANSFER_TIMEOUT,
        )
        if not result.ok:
            failure = classify(result)
            raise ComputeError(
                "ARTIFACT_DOWNLOAD_FAILED",
                "The run outputs could not be downloaded from Kaggle.",
                transient=failure.transient,
                retryable=True,
            )
        output = dest_dir / OUTPUT_DIR_NAME
        if not output.is_dir() and (dest_dir / "manifest.json").is_file():
            output.mkdir()  # flat download: move the files the manifest lists under aas_output/
            for item in dest_dir.iterdir():
                if item.is_file() and not item.name.endswith(".log"):
                    item.replace(output / item.name)
        self._merge_final_logs(acct, run)

    def release(self, remote_ref: str, *, succeeded: bool = False) -> None:
        """Once the job is terminal: delete its input dataset (the user's images) and, if it succeeded, its kernel.

        A failed job's kernel stays on Kaggle so the owner can inspect it there (D-031). Best-effort; never raises.
        """
        try:
            acct, run = self._run_for(remote_ref)
        except ComputeError:
            return
        if run.stream is not None:
            run.stream.terminate()
        if succeeded and acct.owner:
            result = acct.cli.run(
                ["kernels", "delete", f"{acct.owner}/{run.slug}", "-y"], timeout=READ_TIMEOUT
            )
            if not result.ok:
                log.warning("could not delete the kernel of a finished job (%s)", classify(result).kind)
        dataset = run.dataset_ref
        if dataset is None and run.job_id is None:
            dataset = f"{acct.owner}/{dataset_slug_for_slug(run.slug)}" if acct.owner else None
            probe = acct.cli.run(["datasets", "status", dataset], timeout=READ_TIMEOUT) if dataset else None
            if probe is None or parse_dataset_status(probe.stdout) is None:
                dataset = None
        if dataset is None:
            return
        self._delete_dataset(acct, dataset)
        with self._lock:
            if run.job_id:
                self._datasets.pop(run.job_id, None)
            run.dataset_ref = None

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            streams = [r.stream for r in self._runs.values() if r.stream is not None]
        for stream in streams:
            stream.terminate()
        self._account.cli.close()
        if self._owns_root:
            shutil.rmtree(self._root, ignore_errors=True)


def dataset_slug_for_slug(kernel_slug: str) -> str:
    """``aas-job-…`` (kernel) → ``aas-in-job-…`` (its dataset): both derive from the same job id."""
    return ("aas-in-" + kernel_slug.removeprefix("aas-"))[:50].rstrip("-")
