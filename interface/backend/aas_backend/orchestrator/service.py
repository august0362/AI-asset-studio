"""Job orchestration: creation (idempotent), retry, deletion, listing, reconciliation and upload sweeps."""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from kaggle_connector.client import ComputeClient
from kaggle_connector.resources import run_timeout_seconds
from models.contracts import (
    CONTRACT_VERSION,
    TERMINAL_STATUSES,
    RetryRequest,
    UploadRecord,
    error,
    utc_now,
)
from models.registry import ModelRegistry, normalize_options, parse_create_job_request

from ..errors import ApiError, api_error
from ..schemas import ComputeView, Execution, StatusEntry
from ..settings import Settings
from ..storage.files import remove_tree
from ..storage.jobs import JobStore
from ..storage.logs import JobLogs, Redactor
from ..storage.paths import is_valid_id, safe_path
from ..storage.uploads import MIME_EXTENSIONS, UploadStore
from .records import InputRecord, InternalState, JobRecord, RequestRecord
from .state_machine import apply_transition
from .validation import ValidationOutcome, validate_request
from .worker import ProfileWorker

log = logging.getLogger("aas_backend")


def _creation_order(record: JobRecord) -> tuple:
    return (record.created_at, record.internal.created_ns, record.job_id)


class JobService:
    def __init__(
        self,
        settings: Settings,
        *,
        registry: ModelRegistry,
        client: ComputeClient,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.client = client
        self.clock = clock
        self.data_root = settings.data_dir.resolve()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.redact = Redactor(paths=[self.data_root])
        self.store = JobStore(self.data_root)
        self.uploads = UploadStore(self.data_root, timedelta(hours=settings.upload_ttl_hours), clock)
        self.logs = JobLogs(self.data_root / "logs", self.redact, clock)
        self.stopping = threading.Event()
        self._lock = threading.RLock()
        self._create_lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._by_request: dict[str, str] = {}
        self._workers: dict[str, ProfileWorker] = {}
        self._sweeper: threading.Thread | None = None

    # --- lifecycle -------------------------------------------------------------------------------------------

    def start(self) -> None:
        for record in self.store.load_all():
            self._jobs[record.job_id] = record
            self._by_request[record.internal.client_request_id] = record.job_id
        self.sweep_uploads()
        resume = self._reconcile()
        for profile in self.client.profiles():
            if profile.enabled:
                worker = ProfileWorker(self, profile.profile_id)
                self._workers[profile.profile_id] = worker
                worker.start()
        for job_id in resume:
            self._enqueue(self._jobs[job_id])
        self._sweeper = threading.Thread(target=self._sweep_loop, name="aas-upload-sweeper", daemon=True)
        self._sweeper.start()

    def stop(self) -> None:
        self.stopping.set()
        for worker in self._workers.values():
            worker.join(timeout=10)
        if self._sweeper:
            self._sweeper.join(timeout=2)

    def _reconcile(self) -> list[str]:
        """§4 rule 6: a job with a remote reference resumes polling; any other non-terminal job fails."""
        resume = []
        for record in sorted(self._jobs.values(), key=_creation_order):
            if record.status in TERMINAL_STATUSES:
                continue
            if record.execution.remote_ref:
                resume.append(record.job_id)
                self.log(record.job_id, f"Backend restarted; resuming {record.status} job.")
            else:
                self.fail(
                    record,
                    "BACKEND_RESTARTED",
                    "The backend restarted before this job was submitted. Retry the job.",
                    {},
                    True,
                )
        return resume

    def _sweep_loop(self) -> None:
        while not self.stopping.wait(self.settings.sweep_interval_seconds):
            try:
                self.sweep_uploads()
            except Exception:
                log.exception("upload sweep failed")

    def sweep_uploads(self) -> int:
        with self._lock:
            removed = self.uploads.sweep(self.referenced_uploads())
        if removed:
            log.info("swept %d expired upload(s)", removed)
        return removed

    # --- record access ---------------------------------------------------------------------------------------

    def get_record(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return record.model_copy(deep=True) if record else None

    def require(self, job_id: str) -> JobRecord:
        record = self.get_record(job_id)
        if record is None:
            raise api_error(404, "JOB_NOT_FOUND", None, "Job not found.")
        return record

    def commit(self, record: JobRecord) -> JobRecord:
        with self._lock:
            if record.job_id not in self._jobs:
                return record  # deleted meanwhile
            self.store.save(record)
            self._jobs[record.job_id] = record.model_copy(deep=True)
        return record

    def transition(
        self, record: JobRecord, new: str, mutate: Callable[[JobRecord], None] | None = None
    ) -> JobRecord:
        updated = apply_transition(record, new, self.clock())
        if mutate:
            mutate(updated)
        self.commit(updated)
        self.log(record.job_id, f"Status: {record.status} -> {new}")
        return updated

    def fail(
        self, record: JobRecord | None, code: str, message: str, details: dict[str, Any], retryable: bool
    ) -> None:
        if record is None or record.status in TERMINAL_STATUSES:
            return
        failed_in = record.status

        def mark(r: JobRecord) -> None:
            r.error = error(code, None, message, {"failed_in_status": failed_in, **details}, retryable)
            r.execution.finished_at = r.execution.finished_at or self.clock()
            if r.execution.started_at and r.execution.duration_seconds is None:
                r.execution.duration_seconds = int(
                    (r.execution.finished_at - r.execution.started_at).total_seconds()
                )

        self.transition(record, "failed", mark)
        self.log(record.job_id, f"Failed with {code}: {message}")

    def log(self, job_id: str, text: str) -> None:
        self.logs.append(job_id, "backend", [text])

    def referenced_uploads(self) -> set[str]:
        with self._lock:
            return {i.upload_id for r in self._jobs.values() for i in r.request.inputs}

    def _enqueue(self, record: JobRecord) -> None:
        worker = self._workers.get(record.compute.profile_id)
        if worker is None:
            self.fail(record, "INTERNAL_ERROR", "No worker for this compute profile.", {}, False)
        else:
            worker.enqueue(record.job_id)

    # --- validation and creation -----------------------------------------------------------------------------

    def _lookup(self, retry_source: JobRecord | None):
        records: dict[str, UploadRecord] = {}
        sources: dict[str, Path] = {}

        def lookup(upload_id: str) -> UploadRecord | None:
            staged = self.uploads.get(upload_id)
            if staged is not None:
                records[upload_id], sources[upload_id] = staged.record, staged.path
                return staged.record
            if retry_source is not None:  # a retry may reuse the original job's copied inputs
                item = next((i for i in retry_source.request.inputs if i.upload_id == upload_id), None)
                if item is not None:
                    path = safe_path(self.data_root, item.path)
                    if path.is_file():
                        now = self.clock()
                        record = UploadRecord(
                            contract_version=CONTRACT_VERSION,
                            upload_id=upload_id,
                            filename=item.filename,
                            mime_type=item.mime_type,
                            size_bytes=item.size_bytes,
                            width=item.width,
                            height=item.height,
                            sha256=item.sha256,
                            created_at=now,
                            expires_at=now,
                        )
                        records[upload_id], sources[upload_id] = record, path
                        return record
            return None

        return lookup, records, sources

    def validate(self, raw: object) -> ValidationOutcome:
        lookup, _, _ = self._lookup(None)
        return validate_request(raw, registry=self.registry, client=self.client, lookup=lookup)

    def _new_job_id(self) -> str:
        while True:
            job_id = f"job_{self.clock():%Y%m%dT%H%M%SZ}_{secrets.token_hex(3)}"
            if job_id not in self._jobs:
                return job_id

    def _copy_inputs(self, job_id: str, outcome: ValidationOutcome, records, sources) -> list[InputRecord]:
        copied: list[InputRecord] = []
        directory = self.store.inputs_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(outcome.request.inputs):
            record, source = records[item.upload_id], sources[item.upload_id]
            input_id = f"in_{index + 1:02d}"
            relative = f"inputs/{job_id}/{input_id}_{item.role}.{MIME_EXTENSIONS[record.mime_type]}"
            target = safe_path(self.data_root, relative)
            digest = hashlib.sha256()
            try:
                with source.open("rb") as src, target.open("wb") as dst:
                    while chunk := src.read(1 << 20):
                        digest.update(chunk)
                        dst.write(chunk)
            except FileNotFoundError as exc:
                remove_tree(directory)
                raise api_error(
                    422,
                    "UPLOAD_NOT_FOUND",
                    f"inputs[{index}].upload_id",
                    "This upload no longer exists. Upload the image again.",
                ) from exc
            if digest.hexdigest() != record.sha256:
                remove_tree(directory)
                raise api_error(
                    422,
                    "UPLOAD_CORRUPT",
                    f"inputs[{index}].upload_id",
                    "The stored upload changed on disk and cannot be used.",
                )
            copied.append(
                InputRecord(
                    input_id=input_id,
                    role=item.role,
                    mime_type=record.mime_type,
                    width=record.width,
                    height=record.height,
                    size_bytes=record.size_bytes,
                    sha256=record.sha256,
                    path=relative,
                    upload_id=item.upload_id,
                    filename=record.filename,
                )
            )
        return copied

    def create_job(self, raw: object, retry_source: JobRecord | None = None) -> tuple[JobRecord, bool]:
        """Returns ``(record, created)``. Resending a ``client_request_id`` returns the original job."""
        with self._create_lock:
            parsed, _ = parse_create_job_request(raw)
            if parsed is not None:
                existing = self._by_request.get(str(parsed.client_request_id))
                if existing and (record := self.get_record(existing)) is not None:
                    return record, False
            lookup, records, sources = self._lookup(retry_source)
            outcome = validate_request(raw, registry=self.registry, client=self.client, lookup=lookup)
            if not outcome.report.valid:
                raise ApiError(422, outcome.report.errors, outcome.report.warnings)
            req, caps, plan = outcome.request, outcome.capabilities, outcome.plan
            assert (
                req is not None and caps is not None and plan is not None and plan.accelerator_id is not None
            )
            now = self.clock()
            job_id = self._new_job_id()
            inputs = self._copy_inputs(job_id, outcome, records, sources)
            timeout = run_timeout_seconds(plan) or plan.session_limit_seconds or 0
            deadline = (
                plan.required_seconds * self.settings.job_deadline_factor
                if plan.required_seconds is not None
                else float(plan.session_limit_seconds or timeout)
            )
            record = JobRecord(
                contract_version=CONTRACT_VERSION,
                job_id=job_id,
                status="created",
                status_history=[StatusEntry(status="created", at=now)],
                request=RequestRecord(
                    pipeline_type=req.pipeline_type,
                    asset_category=req.asset_category,
                    model_id=req.model_id,
                    prompt=outcome.model.prompt,
                    output_format=req.output_format,
                    options=normalize_options(caps, req.options),
                    inputs=inputs,
                ),
                compute=ComputeView(
                    profile_id=req.compute.profile_id,
                    accelerator_id=plan.accelerator_id,
                    resource_plan=plan,
                ),
                warnings=outcome.report.warnings,
                execution=Execution(
                    backend=self.client.mode, retry_of=retry_source.job_id if retry_source else None
                ),
                created_at=now,
                updated_at=now,
                internal=InternalState(
                    client_request_id=str(req.client_request_id),
                    original_request=req.model_dump(mode="json"),
                    timeout_seconds=timeout,
                    deadline_seconds=deadline,
                    created_ns=time.time_ns(),
                ),
            )
            with self._lock:
                self._jobs[job_id] = record
                self._by_request[record.internal.client_request_id] = job_id
                self.store.save(record)
            origin = f" (retry of {retry_source.job_id})" if retry_source else ""
            self.log(
                job_id,
                f"Job created{origin}: {req.pipeline_type}/{req.asset_category} with {req.model_id} "
                f"on {req.compute.profile_id}/{plan.accelerator_id}; plan fit {plan.fit}.",
            )
        self._enqueue(record)
        return record.model_copy(deep=True), True

    def retry(self, job_id: str, raw: object) -> tuple[JobRecord, bool]:
        original = self.require(job_id)
        try:
            body = RetryRequest.model_validate(raw)
        except ValidationError as exc:
            raise ApiError(
                422,
                [
                    error(
                        "REQUEST_FIELD_INVALID",
                        ".".join(str(p) for p in e["loc"]) or None,
                        "Invalid retry request.",
                    )
                    for e in exc.errors(include_url=False)
                ],
            ) from exc
        existing = self._by_request.get(str(body.client_request_id))
        if existing and (record := self.get_record(existing)) is not None:
            return record, False
        if original.status != "failed" or original.error is None or not original.error.retryable:
            raise api_error(
                409,
                "JOB_NOT_RETRYABLE",
                None,
                "Only failed jobs with a retryable error can be retried.",
                {"status": original.status, "error_code": original.error.code if original.error else None},
            )
        request = {**original.internal.original_request, "client_request_id": str(body.client_request_id)}
        return self.create_job(request, retry_source=original)

    def delete_job(self, job_id: str) -> None:
        record = self.require(job_id)
        if record.status not in TERMINAL_STATUSES:
            raise api_error(
                409,
                "JOB_NOT_TERMINAL",
                None,
                "Only completed or failed jobs can be deleted.",
                {"status": record.status},
            )
        with self._lock:
            self.store.delete(job_id, [self.logs.log_path(job_id), self.logs.telemetry_path(job_id)])
            self._jobs.pop(job_id, None)
            self._by_request.pop(record.internal.client_request_id, None)
            self.logs.forget(job_id)

    def delete_upload(self, upload_id: str) -> None:
        with self._lock:
            if self.uploads.get(upload_id) is None:
                raise api_error(404, "UPLOAD_NOT_FOUND", "upload_id", "Upload not found or expired.")
            if upload_id in self.referenced_uploads():
                raise api_error(409, "UPLOAD_IN_USE", "upload_id", "A job references this upload.")
            self.uploads.delete(upload_id)

    def list_jobs(self, status: str | None, pipeline_type: str | None, limit: int, cursor: str | None):
        with self._lock:
            records = sorted(self._jobs.values(), key=_creation_order, reverse=True)
        records = [
            r
            for r in records
            if (status is None or r.status == status)
            and (pipeline_type is None or r.request.pipeline_type == pipeline_type)
        ]
        if cursor is not None:
            ids = [r.job_id for r in records]
            if not is_valid_id("job_id", cursor) or cursor not in ids:
                raise api_error(422, "REQUEST_FIELD_INVALID", "cursor", "Unknown or expired cursor.")
            records = records[ids.index(cursor) + 1 :]
        page = records[:limit]
        next_cursor = page[-1].job_id if len(records) > limit else None
        return [r.model_copy(deep=True) for r in page], next_cursor
