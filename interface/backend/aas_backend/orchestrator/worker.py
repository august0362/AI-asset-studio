"""Drives one session (a job, or a run group of two jobs) through CONTRACTS §4; :mod:`.scheduler` decides when.

Runs are never resubmitted automatically. Transient remote reads and downloads get at most 3 retries. Every terminal
run is cleaned up on Kaggle, completed or failed (CONTRACTS §14.7).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from kaggle_connector.client import (
    ComputeError,
    KaggleGroupSpec,
    KaggleJobSpec,
    OutputSpec,
    RemoteRefNotFound,
)
from kaggle_connector.jobs.manifest import ManifestInvalid, read_manifest, verify_outputs
from kaggle_connector.jobs.packaging import OUTPUT_DIR_NAME
from kaggle_connector.resources import parse_line
from kaggle_connector.resources.contracts import OutputManifest
from models.adapters import ArtifactInvalidError
from models.adapters.base import PACKAGE_ROOT
from models.contracts import CONTRACT_VERSION, GenerationInput, GenerationRequest, warning

from ..schemas import PreviewRef, Progress
from ..storage.files import remove_tree
from ..storage.paths import safe_path
from .records import JobRecord

if TYPE_CHECKING:
    from .service import JobService

log = logging.getLogger("aas_backend")
T = TypeVar("T")
MAX_TRANSIENT_RETRIES = 3

GROUP_LINE = re.compile(r"^\[(job_\d{8}T\d{6}Z_[0-9a-f]{6})\] ?(.*)$", re.DOTALL)
CODED_REMOTE_ERRORS = frozenset({"MODEL_PROMPT_TOO_LONG"})  # model errors the runner reports by code (§14.8)

FAILURE_MESSAGES = {
    "KAGGLE_KERNEL_ERROR": "The remote notebook exited with an error. See the job logs.",
    "KAGGLE_TIMEOUT": "The run took longer than its planned time limit.",
    "BACKEND_RESTARTED": "The backend restarted while this job was in progress. Retry the job.",
    "INTERNAL_ERROR": "Unexpected internal error. Details are in the local log.",
    "MODEL_PROMPT_TOO_LONG": "The prompt is longer than the model's text encoder can read. Shorten the prompt.",
}


class JobFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message or FAILURE_MESSAGES.get(code, code)
        self.details = details or {}
        self.retryable = retryable


class ShuttingDown(Exception):
    """The backend is stopping; the job stays non-terminal and is reconciled on the next start."""


def is_timed_out(seconds_since_submit: float, deadline_seconds: float) -> bool:
    """§4 rule 7: queued or running for longer than required_seconds × 1.25."""
    return seconds_since_submit > deadline_seconds


def generation_request(record: JobRecord) -> GenerationRequest:
    req = record.request
    return GenerationRequest(
        contract_version=CONTRACT_VERSION,
        job_id=record.job_id,
        pipeline_type=req.pipeline_type,
        asset_category=req.asset_category,
        model_id=req.model_id,
        prompt=req.prompt,
        inputs=[
            GenerationInput(
                input_id=i.input_id,
                role=i.role,
                path=i.path,
                mime_type=i.mime_type,
                width=i.width,
                height=i.height,
                size_bytes=i.size_bytes,
                sha256=i.sha256,
            )
            for i in req.inputs
        ],
        options=req.options,
        output_format=req.output_format,
        created_at=record.created_at,
        tasks=req.tasks,
        time_budget_seconds=record.internal.timeout_seconds or None if req.tasks is not None else None,
    )


def batch_partial(request: GenerationRequest, artifacts, report: dict[str, dict]):
    """The ``BATCH_PARTIAL`` warning (§13.7) when a batch job completed without every task, else ``None``.

    A task with no image is ``not_run`` if the runner said so, otherwise ``failed`` (with the runner's message, or a
    generic one when the runner reported nothing or its PNG was invalid).
    """
    succeeded = {a.task_id for a in artifacts}
    failed, not_run, tasks = [], [], {}
    for task in request.tasks or []:
        if task.task_id in succeeded:
            continue
        entry = report.get(task.task_id) or {}
        if entry.get("status") == "not_run":
            not_run.append(task.task_id)
            tasks[task.task_id] = {
                "status": "not_run",
                "reason": entry.get("reason") or "job_failed",
                "message": entry.get("message") or "The task did not start.",
            }
        else:
            failed.append(task.task_id)
            tasks[task.task_id] = {
                "status": "failed",
                "reason": entry.get("reason"),  # e.g. prompt_too_long (§14.8)
                "message": entry.get("message")
                or (
                    "The task produced no valid PNG."
                    if entry.get("status") == "succeeded"
                    else "The runner reported no result for this task."
                ),
            }
    if not tasks:
        return None
    return warning(
        "BATCH_PARTIAL",
        None,
        f"{len(succeeded)} of {len(request.tasks or [])} task(s) succeeded.",
        {"failed": failed, "not_run": not_run, "tasks": tasks},
    )


class JobRunner:
    def __init__(self, service: JobService) -> None:
        self.s = service

    # --- helpers ---------------------------------------------------------------------------------------------

    def _with_retries(self, rec: JobRecord, operation: str, fn: Callable[[], T]) -> tuple[JobRecord, T]:
        delays = self.s.settings.retry_delays_seconds
        attempt = 0
        while True:
            try:
                return rec, fn()
            except RemoteRefNotFound as exc:
                raise JobFailure(
                    "BACKEND_RESTARTED",
                    retryable=True,
                    details={"reason": "remote reference no longer known"},
                ) from exc
            except ComputeError as exc:
                if not exc.transient or attempt >= MAX_TRANSIENT_RETRIES:
                    raise JobFailure(
                        exc.code, exc.message, retryable=exc.retryable, details={"attempts": attempt + 1}
                    ) from exc
                rec.execution.transient_retries += 1
                rec = self.s.commit(rec)
                self.s.log(
                    rec.job_id,
                    f"Transient error during {operation} ({exc.code}); retry {attempt + 1} "
                    f"of {MAX_TRANSIENT_RETRIES} in {delays[attempt]:g} s.",
                )
                if self.s.stopping.wait(delays[attempt]):
                    raise ShuttingDown from exc
                attempt += 1

    def _pull_logs(self, rec: JobRecord) -> JobRecord:
        """New remote lines into the job's log. In a run group (§6.4) every job reads the session's lines and keeps
        its own: progress by ``job_id``, plain lines by their ``[<job_id>]`` prefix (removed), session-wide lines and
        telemetry for both jobs."""
        try:
            lines, next_offset = self.s.client.logs(rec.execution.remote_ref, rec.internal.remote_log_offset)
        except ComputeError:
            return rec  # logs are best-effort; the authoritative read happens at the end
        if not lines:
            return rec
        grouped = rec.scheduling.group_id is not None
        texts = []
        for line in lines:
            if grouped and (match := GROUP_LINE.match(line)):
                if match.group(1) != rec.job_id:
                    continue
                line = match.group(2)
            parsed = parse_line(line)
            if grouped and parsed.kind == "progress" and parsed.progress.job_id != rec.job_id:
                continue
            if parsed.kind == "telemetry":
                self.s.logs.append_telemetry(rec.job_id, parsed.telemetry.model_dump(mode="json"))
                rec.internal.telemetry_samples += 1
                continue  # never returned by the logs endpoint (§5)
            if parsed.kind == "malformed":
                rec.internal.telemetry_malformed += 1
                continue
            if parsed.kind == "progress":
                p = parsed.progress
                rec.internal.progress = Progress(stage=p.stage, percent=p.percent, message=p.message)
            texts.append(line)
        self.s.logs.append(rec.job_id, "remote", texts)
        rec.internal.remote_log_offset = next_offset
        return self.s.commit(rec)

    def _spec(self, rec: JobRecord) -> KaggleJobSpec:
        adapter = self.s.registry.adapter(rec.request.model_id)
        invocation = adapter.build_invocation(generation_request(rec))
        entry = (PACKAGE_ROOT / invocation.entrypoint).resolve()
        if not entry.is_relative_to((PACKAGE_ROOT / "models").resolve()) or not entry.is_file():
            raise JobFailure("INTERNAL_ERROR", details={"reason": "adapter entrypoint not found"})
        return KaggleJobSpec(
            job_id=rec.job_id,
            profile_id=rec.compute.profile_id,
            accelerator_id=rec.compute.accelerator_id,
            timeout_seconds=rec.internal.timeout_seconds,
            entrypoint_file=entry,
            arguments=invocation.arguments,
            input_files=[safe_path(self.s.data_root, p) for p in invocation.input_files],
            expected_outputs=[
                OutputSpec(o.name, o.kind, o.format, o.required) for o in invocation.expected_outputs
            ],
            internet=adapter.requires_internet,
        )

    # --- stages ----------------------------------------------------------------------------------------------

    def _submit(self, rec: JobRecord) -> JobRecord:
        spec = self._spec(rec)
        if spec.requires_input_upload:
            rec = self.s.transition(rec, "uploading")
            try:
                self.s.client.upload_inputs(spec)
            except ComputeError as exc:
                raise JobFailure(exc.code, exc.message, retryable=exc.retryable) from exc
        try:
            ref = self.s.client.submit(spec)
        except ComputeError as exc:
            raise JobFailure(exc.code, exc.message, retryable=exc.retryable) from exc

        def mark(r: JobRecord) -> None:
            r.execution.remote_ref = ref
            r.execution.submitted_at = self.s.clock()

        rec = self.s.transition(rec, "queued", mark)
        self.s.log(
            rec.job_id,
            f"Submitted to {self.s.client.mode} compute as {ref} "
            f"(accelerator {spec.accelerator_id}, timeout {spec.timeout_seconds} s).",
        )
        return rec

    def _started(self, r: JobRecord) -> None:
        r.execution.started_at = r.execution.started_at or self.s.clock()

    def _poll(self, rec: JobRecord) -> JobRecord | None:
        ref = rec.execution.remote_ref
        while not self.s.stopping.is_set():
            rec, remote = self._with_retries(rec, "status check", lambda: self.s.client.status(ref))
            rec = self._pull_logs(rec)
            if remote in ("queued", "running"):
                if remote == "running" and rec.status == "queued":
                    rec = self.s.transition(rec, "running", self._started)
                submitted = rec.execution.submitted_at or rec.created_at
                elapsed = (self.s.clock() - submitted).total_seconds()
                if is_timed_out(elapsed, rec.internal.deadline_seconds):
                    raise JobFailure(
                        "KAGGLE_TIMEOUT",
                        retryable=True,
                        details={
                            "elapsed_seconds": int(elapsed),
                            "deadline_seconds": rec.internal.deadline_seconds,
                        },
                    )
            elif remote == "complete":
                if rec.status == "queued":  # finished between two polls
                    rec = self.s.transition(rec, "running", self._started)
                if rec.status == "running":
                    rec = self.s.transition(rec, "downloading", self._finished)
                return rec
            else:  # error: the remote run started and ended in error
                if rec.status == "queued":
                    rec = self.s.transition(rec, "running", self._started)
                raise self._remote_error(rec, [rec.job_id])[rec.job_id]
            if self.s.stopping.wait(self.s.settings.effective_poll_seconds):
                return None
        return None

    def _finished(self, r: JobRecord) -> None:
        r.execution.finished_at = self.s.clock()
        if r.execution.started_at:
            r.execution.duration_seconds = int(
                (r.execution.finished_at - r.execution.started_at).total_seconds()
            )

    def _download(self, rec: JobRecord) -> JobRecord:
        ref = rec.execution.remote_ref
        raw = self.s.store.outputs_dir(rec.job_id) / "remote_raw"
        rec, _ = self._with_retries(rec, "download", lambda: self.s.client.download(ref, raw))
        rec = self._pull_logs(rec)
        rec = self._collect(rec, raw / OUTPUT_DIR_NAME)
        remove_tree(raw)  # kept when collecting fails, so the outputs can be inspected
        return rec

    def _manifest_failure(self, manifest: OutputManifest) -> JobFailure:
        error = manifest.error
        if error is not None and error.code in CODED_REMOTE_ERRORS:
            return JobFailure(error.code, details=dict(error.details))
        return JobFailure(
            "KAGGLE_KERNEL_ERROR",
            details={"remote_status": "error", "manifest_error": error.model_dump() if error else None},
        )

    def _collect(self, rec: JobRecord, output_dir: Path) -> JobRecord:
        """One job's downloaded outputs → artifacts, then ``completed``. Raises ``JobFailure``."""
        try:
            manifest = read_manifest(output_dir)
            if manifest.status == "error":
                raise self._manifest_failure(manifest)
            verify_outputs(manifest, output_dir, rec.job_id)
            adapter = self.s.registry.adapter(rec.request.model_id)
            request = generation_request(rec)
            artifacts = adapter.collect_outputs(request, output_dir)
            partial = (
                batch_partial(request, artifacts, adapter.task_report(request, output_dir))
                if request.tasks is not None
                else None
            )
        except ManifestInvalid as exc:
            raise JobFailure("ARTIFACT_INVALID", exc.message) from exc
        except ArtifactInvalidError as exc:
            raise JobFailure("ARTIFACT_INVALID", exc.message, details=exc.details) from exc

        for artifact in artifacts:
            relative = f"outputs/{rec.job_id}/{artifact.artifact_id}.{artifact.format}"
            target = safe_path(self.s.data_root, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(output_dir / artifact.path, target)
            artifact.path = relative
        preview = next((a for a in artifacts if a.kind == "preview"), None) or next(
            (a for a in artifacts if a.is_primary and a.kind == "image"), None
        )

        def complete(r: JobRecord) -> None:
            r.artifacts = artifacts
            r.preview = PreviewRef(artifact_id=preview.artifact_id) if preview else None
            if partial is not None:
                r.warnings = [*r.warnings, partial]
            if r.execution.finished_at is None:
                self._finished(r)

        rec = self.s.transition(rec, "completed", complete)
        self.s.log(rec.job_id, f"Completed with {len(artifacts)} artifact(s).")
        if partial is not None:
            self.s.log(
                rec.job_id,
                f"Batch partial: failed {partial.details['failed']}, not run {partial.details['not_run']}.",
            )
        return rec

    def _remote_error(self, rec: JobRecord, job_ids: list[str]) -> dict[str, JobFailure]:
        """The run ended in error. A job whose manifest reports a coded model error (§14.8) fails with that code;
        any other job fails with ``KAGGLE_KERNEL_ERROR``. The outputs are read once, best-effort."""
        failures = {
            job_id: JobFailure("KAGGLE_KERNEL_ERROR", details={"remote_status": "error"})
            for job_id in job_ids
        }
        raw = self.s.store.outputs_dir(job_ids[0]) / "remote_raw"
        try:
            self.s.client.download(rec.execution.remote_ref, raw)
            for job_id in job_ids:
                folder = raw / OUTPUT_DIR_NAME / job_id if len(job_ids) > 1 else raw / OUTPUT_DIR_NAME
                try:
                    manifest = read_manifest(folder)
                except ManifestInvalid:
                    continue
                if manifest.job_id == job_id and manifest.status == "error":
                    failures[job_id] = self._manifest_failure(manifest)
        except ComputeError:
            pass
        finally:
            remove_tree(raw)
        return failures

    # --- entry point: one job ----------------------------------------------------------------------------------

    def process(self, job_id: str) -> None:
        rec = self.s.get_record(job_id)
        if rec is None or rec.status in ("completed", "failed"):
            return
        try:
            if rec.status == "created":
                rec = self._submit(rec)
            if rec.status in ("queued", "running"):
                polled = self._poll(rec)
                if polled is None:
                    return  # shutting down: reconciled on the next start
                rec = polled
            if rec.status == "downloading":
                self._download(rec)
        except ShuttingDown:
            return
        except JobFailure as failure:
            self.s.fail(
                self.s.get_record(job_id), failure.code, failure.message, failure.details, failure.retryable
            )
        except Exception:
            log.exception("unexpected error while processing %s", job_id)
            self._internal_error(job_id)
        self._release([job_id])

    def _internal_error(self, job_id: str) -> None:
        current = self.s.get_record(job_id)
        if current is not None and current.status not in ("completed", "failed"):
            self.s.fail(current, "INTERNAL_ERROR", FAILURE_MESSAGES["INTERNAL_ERROR"], {}, False)

    def _release(self, job_ids: list[str], remote_ref: str | None = None) -> None:
        """Once every job of the run is terminal: clean up on Kaggle (§14.7), then store the final log lines that
        the cleanup merged. Best-effort; a cleanup failure never changes a job's outcome."""
        records = [r for r in (self.s.get_record(j) for j in job_ids) if r is not None]
        if any(r.status not in ("completed", "failed") for r in records):
            return
        remote_ref = remote_ref or next(
            (r.execution.remote_ref for r in records if r.execution.remote_ref), None
        )
        if not remote_ref:
            return
        try:
            self.s.client.release(remote_ref, list(job_ids))
        except Exception:
            log.exception("cleaning up the remote run %s failed", remote_ref)
        for record in records:
            if record.execution.remote_ref:
                self._pull_logs(record)
                self.s.log(
                    record.job_id, "Remote run cleaned up: kernel and input dataset deleted on Kaggle."
                )

    # --- entry point: a run group (§14.4) ---------------------------------------------------------------------

    def process_group(self, job_ids: list[str]) -> None:
        ref = None
        try:
            recs = [self.s.get_record(j) for j in job_ids]
            if any(r is None for r in recs) or all(r.status in ("completed", "failed") for r in recs):
                return
            ref = next((r.execution.remote_ref for r in recs if r.execution.remote_ref), None)
            if all(r.status == "created" for r in recs):
                recs, ref = self._submit_group(recs)
            if any(r.status in ("queued", "running") for r in recs):
                polled = self._poll_group(recs)
                if polled is None:
                    return  # shutting down: reconciled on the next start
                recs = polled
            if any(r.status == "downloading" for r in recs):
                self._download_group(recs)
        except ShuttingDown:
            return
        except JobFailure as failure:
            for job_id in job_ids:
                self.s.fail(
                    self.s.get_record(job_id),
                    failure.code,
                    failure.message,
                    failure.details,
                    failure.retryable,
                )
        except Exception:
            log.exception("unexpected error while processing the run group of %s", job_ids)
            for job_id in job_ids:
                self._internal_error(job_id)
        self._release(job_ids, ref)

    def _group_spec(self, recs: list[JobRecord]) -> KaggleGroupSpec:
        specs = tuple(self._spec(r) for r in recs)
        first = recs[0]
        return KaggleGroupSpec(
            group_id=first.scheduling.group_id,
            profile_id=first.compute.profile_id,
            accelerator_id=first.compute.accelerator_id,
            timeout_seconds=max(spec.timeout_seconds for spec in specs),
            members=specs,
        )

    def _submit_group(self, recs: list[JobRecord]) -> tuple[list[JobRecord], str]:
        spec = self._group_spec(recs)
        if any(m.requires_input_upload for m in spec.members):
            recs = [self.s.transition(r, "uploading") for r in recs]
            for member in spec.members:
                if member.requires_input_upload:
                    try:
                        self.s.client.upload_inputs(member)
                    except ComputeError as exc:
                        raise JobFailure(exc.code, exc.message, retryable=exc.retryable) from exc
        try:
            ref = self.s.client.submit_group(spec)
        except ComputeError as exc:
            raise JobFailure(exc.code, exc.message, retryable=exc.retryable) from exc

        def mark(r: JobRecord) -> None:
            r.execution.remote_ref = ref
            r.execution.submitted_at = self.s.clock()

        recs = [self.s.transition(r, "queued", mark) for r in recs]
        for r in recs:
            self.s.log(
                r.job_id,
                f"Submitted to {self.s.client.mode} compute as {ref} in run group {spec.group_id} "
                f"(GPU {r.scheduling.gpu_index}; accelerator {spec.accelerator_id}, "
                f"timeout {spec.timeout_seconds} s).",
            )
        return recs, ref

    def _advance(self, recs: list[JobRecord], new: str, before: str, mutate) -> list[JobRecord]:
        """Moves every job of the group that is still in ``before`` to ``new`` (they share these states)."""
        current = [self.s.get_record(r.job_id) or r for r in recs]
        return [self.s.transition(r, new, mutate) if r.status == before else r for r in current]

    def _poll_group(self, recs: list[JobRecord]) -> list[JobRecord] | None:
        ref = recs[0].execution.remote_ref
        deadline = max(r.internal.deadline_seconds for r in recs)
        while not self.s.stopping.is_set():
            _, remote = self._with_retries(recs[0], "status check", lambda: self.s.client.status(ref))
            recs = [self._pull_logs(self.s.get_record(r.job_id) or r) for r in recs]
            if remote in ("queued", "running"):
                if remote == "running":
                    recs = self._advance(recs, "running", "queued", self._started)
                submitted = recs[0].execution.submitted_at or recs[0].created_at
                elapsed = (self.s.clock() - submitted).total_seconds()
                if is_timed_out(elapsed, deadline):
                    raise JobFailure(
                        "KAGGLE_TIMEOUT",
                        retryable=True,
                        details={"elapsed_seconds": int(elapsed), "deadline_seconds": deadline},
                    )
            elif remote == "complete":
                recs = self._advance(recs, "running", "queued", self._started)
                return self._advance(recs, "downloading", "running", self._finished)
            else:  # the kernel ends in error only when both jobs failed; each gets the code from its manifest
                recs = self._advance(recs, "running", "queued", self._started)
                failures = self._remote_error(recs[0], [r.job_id for r in recs])
                for r in recs:
                    f = failures[r.job_id]
                    self.s.fail(self.s.get_record(r.job_id), f.code, f.message, f.details, f.retryable)
                return [self.s.get_record(r.job_id) or r for r in recs]
            if self.s.stopping.wait(self.s.settings.effective_poll_seconds):
                return None
        return None

    def _download_group(self, recs: list[JobRecord]) -> None:
        """One download for the session; then each job completes or fails from its own manifest."""
        ref = recs[0].execution.remote_ref
        raw = self.s.store.outputs_dir(recs[0].job_id) / "remote_raw"
        self._with_retries(recs[0], "download", lambda: self.s.client.download(ref, raw))
        failed = False
        for rec in recs:
            rec = self._pull_logs(self.s.get_record(rec.job_id) or rec)
            if rec.status != "downloading":
                continue
            try:
                self._collect(rec, raw / OUTPUT_DIR_NAME / rec.job_id)
            except JobFailure as failure:
                failed = True
                self.s.fail(
                    self.s.get_record(rec.job_id),
                    failure.code,
                    failure.message,
                    failure.details,
                    failure.retryable,
                )
        if not failed:
            remove_tree(raw)  # kept when a job's outputs are invalid, so they can be inspected
