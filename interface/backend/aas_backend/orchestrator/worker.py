"""One in-process worker per compute profile, concurrency 1 (D-006). Drives a job through CONTRACTS §4.

Runs are never resubmitted automatically. Transient remote reads and downloads get at most 3 retries.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar

from kaggle_connector.client import ComputeError, KaggleJobSpec, OutputSpec, RemoteRefNotFound
from kaggle_connector.jobs.manifest import ManifestInvalid, read_manifest, verify_outputs
from kaggle_connector.jobs.packaging import OUTPUT_DIR_NAME
from kaggle_connector.resources import parse_line
from models.adapters import ArtifactInvalidError
from models.adapters.base import PACKAGE_ROOT
from models.contracts import CONTRACT_VERSION, GenerationInput, GenerationRequest

from ..schemas import PreviewRef, Progress
from ..storage.files import remove_tree
from ..storage.paths import safe_path
from .records import JobRecord

if TYPE_CHECKING:
    from .service import JobService

log = logging.getLogger("aas_backend")
T = TypeVar("T")
MAX_TRANSIENT_RETRIES = 3

FAILURE_MESSAGES = {
    "KAGGLE_KERNEL_ERROR": "The remote notebook exited with an error. See the job logs.",
    "KAGGLE_TIMEOUT": "The run took longer than its planned time limit.",
    "BACKEND_RESTARTED": "The backend restarted while this job was in progress. Retry the job.",
    "INTERNAL_ERROR": "Unexpected internal error. Details are in the local log.",
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
        try:
            lines, next_offset = self.s.client.logs(rec.execution.remote_ref, rec.internal.remote_log_offset)
        except ComputeError:
            return rec  # logs are best-effort; the authoritative read happens at the end
        if not lines:
            return rec
        texts = []
        for line in lines:
            parsed = parse_line(line)
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
                raise JobFailure("KAGGLE_KERNEL_ERROR", details={"remote_status": "error"})
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
        out_root = self.s.store.outputs_dir(rec.job_id)
        raw = out_root / "remote_raw"
        rec, _ = self._with_retries(rec, "download", lambda: self.s.client.download(ref, raw))
        rec = self._pull_logs(rec)
        output_dir = raw / OUTPUT_DIR_NAME
        try:
            manifest = read_manifest(output_dir)
            if manifest.status == "error":
                raise JobFailure(
                    "KAGGLE_KERNEL_ERROR",
                    details={
                        "remote_status": "error",
                        "manifest_error": manifest.error.model_dump() if manifest.error else None,
                    },
                )
            verify_outputs(manifest, output_dir, rec.job_id)
            artifacts = self.s.registry.adapter(rec.request.model_id).collect_outputs(
                generation_request(rec), output_dir
            )
        except ManifestInvalid as exc:
            raise JobFailure("ARTIFACT_INVALID", exc.message) from exc
        except ArtifactInvalidError as exc:
            raise JobFailure("ARTIFACT_INVALID", exc.message, details=exc.details) from exc

        for artifact in artifacts:
            relative = f"outputs/{rec.job_id}/{artifact.artifact_id}.{artifact.format}"
            os.replace(output_dir / artifact.path, safe_path(self.s.data_root, relative))
            artifact.path = relative
        remove_tree(raw)
        preview = next((a for a in artifacts if a.kind == "preview"), None) or next(
            (a for a in artifacts if a.is_primary and a.kind == "image"), None
        )

        def complete(r: JobRecord) -> None:
            r.artifacts = artifacts
            r.preview = PreviewRef(artifact_id=preview.artifact_id) if preview else None
            if r.execution.finished_at is None:
                self._finished(r)

        rec = self.s.transition(rec, "completed", complete)
        self.s.log(rec.job_id, f"Completed with {len(artifacts)} artifact(s).")
        return rec

    # --- entry point -----------------------------------------------------------------------------------------

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
            current = self.s.get_record(job_id)
            if current is not None and current.status not in ("completed", "failed"):
                self.s.fail(current, "INTERNAL_ERROR", FAILURE_MESSAGES["INTERNAL_ERROR"], {}, False)


class ProfileWorker(threading.Thread):
    def __init__(self, service: JobService, profile_id: str) -> None:
        super().__init__(name=f"aas-worker-{profile_id}", daemon=True)
        self.profile_id = profile_id
        self.queue: queue.Queue[str] = queue.Queue()
        self.runner = JobRunner(service)
        self._service = service

    def enqueue(self, job_id: str) -> None:
        self.queue.put(job_id)

    def run(self) -> None:
        while not self._service.stopping.is_set():
            try:
                job_id = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self.runner.process(job_id)
