"""Job orchestration: creation (idempotent), retry, run control and run groups (§14), deletion, listing,
reconciliation and upload sweeps."""

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
    GenerationTask,
    RetryRequest,
    UploadRecord,
    error,
    utc_now,
)
from models.registry import ModelRegistry, normalize_options, parse_create_job_request

from ..errors import ApiError, api_error
from ..schemas import (
    AutoRunBody,
    BatchRef,
    BulkDeleteResult,
    ComputeView,
    Execution,
    GenerationResult,
    JobIdsBody,
    JobSummary,
    RefusedDelete,
    RunGroup,
    Scheduling,
    StatusEntry,
)
from ..settings import Settings
from ..storage.files import remove_tree
from ..storage.jobs import JobStore
from ..storage.logs import JobLogs, Redactor
from ..storage.paths import is_valid_id, safe_path
from ..storage.uploads import MIME_EXTENSIONS, UploadStore
from .records import (
    InputRecord,
    InternalState,
    JobRecord,
    RequestRecord,
    SchedulingRecord,
    to_result,
    to_summary,
)
from .scheduler import Entry, Scheduler, fifo_key
from .state_machine import apply_transition
from .validation import BatchValidation, ValidationOutcome, validate_batch, validate_request

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
        self.redact = Redactor(secrets=client.redaction_terms(), paths=[self.data_root])
        self.store = JobStore(self.data_root)
        self.uploads = UploadStore(self.data_root, timedelta(hours=settings.upload_ttl_hours), clock)
        self.logs = JobLogs(self.data_root / "logs", self.redact, clock)
        self.stopping = threading.Event()
        self._lock = threading.RLock()
        self._create_lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._by_request: dict[str, str] = {}
        self._scheduler: Scheduler | None = None
        self._sweeper: threading.Thread | None = None

    # --- lifecycle -------------------------------------------------------------------------------------------

    def start(self) -> None:
        for record in self.store.load_all():
            self._jobs[record.job_id] = record
            self._by_request[record.internal.client_request_id] = record.job_id
        self.sweep_uploads()
        resume = self._reconcile()
        if any(profile.enabled for profile in self.client.profiles()):
            self._scheduler = Scheduler(self)
            self._scheduler.resume(self._resume_entries(resume))
            self._scheduler.start()
        else:
            for job_id in resume:
                self.fail(
                    self._jobs[job_id], "INTERNAL_ERROR", "No worker for this compute profile.", {}, False
                )
        self._sweeper = threading.Thread(target=self._sweep_loop, name="aas-upload-sweeper", daemon=True)
        self._sweeper.start()

    def stop(self) -> None:
        self.stopping.set()
        if self._scheduler:
            self._scheduler.join(timeout=10)
            self._scheduler.join_sessions(timeout=10)
        if self._sweeper:
            self._sweeper.join(timeout=2)

    def _reconcile(self) -> list[str]:
        """§4 rule 6: a job with a remote reference resumes polling; a held or waiting ``created`` job keeps its
        place (v1.2); any other non-terminal job fails."""
        resume = []
        for record in sorted(self._jobs.values(), key=_creation_order):
            if record.status in TERMINAL_STATUSES:
                continue
            if (
                record.status == "created"
                and not record.scheduling.slot_taken
                and not record.execution.remote_ref
            ):
                state = "waiting" if record.scheduling.auto_run else "held"
                self.log(record.job_id, f"Backend restarted; the job is still {state}.")
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
        """Wakes the scheduler. An auto-run job waits in the FIFO; a held job waits for the owner (§14.2)."""
        if self._scheduler is None or not self.profile_enabled(record.compute.profile_id):
            self.fail(record, "INTERNAL_ERROR", "No worker for this compute profile.", {}, False)
        else:
            self._scheduler.notify()

    # --- scheduling (§14.2, §14.3) ---------------------------------------------------------------------------

    def profile_enabled(self, profile_id: str) -> bool:
        return any(p.enabled and p.profile_id == profile_id for p in self.client.profiles())

    def _accelerator(self, profile_id: str, accelerator_id: str | None):
        for profile in self.client.profiles():
            if profile.profile_id == profile_id:
                return next((a for a in profile.accelerators if a.accelerator_id == accelerator_id), None)
        return None

    @staticmethod
    def queue_state(record: JobRecord) -> str | None:
        if record.status != "created":
            return None
        if record.scheduling.slot_taken:
            return "starting"
        return "waiting" if record.scheduling.auto_run else "held"

    def _members(self, record: JobRecord) -> list[JobRecord]:
        """The job and its run-group partner, in GPU order (call with the lock held)."""
        if record.scheduling.group_id is None:
            return [record]
        return [self._jobs[j] for j in record.scheduling.group_job_ids if j in self._jobs]

    def _entry(self, records: list[JobRecord]) -> Entry:
        first = records[0]
        accelerator = self._accelerator(first.compute.profile_id, first.compute.accelerator_id)
        required = [r.compute.resource_plan.required_seconds for r in records]
        return Entry(
            key=first.scheduling.group_id or first.job_id,
            job_ids=tuple(r.job_id for r in records),
            profile_id=first.compute.profile_id,
            gpu=accelerator is not None and accelerator.kind == "gpu_cuda",
            required_seconds=None if any(v is None for v in required) else float(max(required)),
        )

    def fifo(self) -> list[Entry]:
        """Waiting entries in FIFO order: ``run_requested_at``, then ``created_at``, then ``job_id``."""
        with self._lock:
            waiting = sorted(
                (r for r in self._jobs.values() if self.queue_state(r) == "waiting"), key=fifo_key
            )
            entries, seen = [], set()
            for record in waiting:
                key = record.scheduling.group_id or record.job_id
                if key in seen:
                    continue
                seen.add(key)
                members = [m for m in self._members(record) if self.queue_state(m) == "waiting"] or [record]
                entries.append(self._entry(members))
            return entries

    def take_slot(self, entry: Entry) -> None:
        """The job (or group) takes a session slot: ``starting`` until its first transition."""
        with self._lock:
            for job_id in entry.job_ids:
                record = self._jobs[job_id].model_copy(deep=True)
                record.scheduling.slot_taken = True
                self.commit(record)
                self.log(job_id, "Session slot taken; starting.")

    def gpu_quota_remaining_seconds(self, profile_id: str) -> float | None:
        """The profile's cached GPU quota (never a Kaggle call here); ``None`` when it is unknown."""
        try:
            hours = self.client.snapshot(profile_id).gpu_quota_remaining_hours
        except Exception:
            return None
        return None if hours is None else hours * 3600

    def _resume_entries(self, job_ids: list[str]) -> list[Entry]:
        entries, seen = [], set()
        for job_id in job_ids:
            record = self._jobs[job_id]
            key = record.scheduling.group_id or job_id
            if key in seen:
                continue
            seen.add(key)
            members = [m for m in self._members(record) if m.job_id in job_ids] or [record]
            entries.append(self._entry(members))
        return entries

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
            timeout, deadline = self._time_limits(plan)
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
                scheduling=SchedulingRecord(
                    auto_run=req.auto_run,
                    run_requested_at=now if req.auto_run else None,
                    requested_ns=time.time_ns(),
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
                f"on {req.compute.profile_id}/{plan.accelerator_id}; plan fit {plan.fit}; "
                + ("auto-run on." if req.auto_run else "auto-run off, held until run."),
            )
            # Enqueue under the same creation lock as persistence: concurrent requests
            # cannot reverse FIFO order, including v1 jobs and V2 batch groups.
            self._enqueue(record)
        return record.model_copy(deep=True), True

    def _time_limits(self, plan) -> tuple[int, float]:
        timeout = run_timeout_seconds(plan) or plan.session_limit_seconds or 0
        deadline = (
            plan.required_seconds * self.settings.job_deadline_factor
            if plan.required_seconds is not None
            else float(plan.session_limit_seconds or timeout)
        )
        return timeout, deadline

    # --- batch jobs (§13.9) ----------------------------------------------------------------------------------

    def validate_batch(
        self, model_id: str, asset_category: str, tasks: list[tuple[str, str, dict]], compute: dict
    ) -> BatchValidation:
        return validate_batch(
            model_id=model_id,
            asset_category=asset_category,
            tasks=tasks,
            compute=compute,
            registry=self.registry,
            client=self.client,
        )

    def find_by_request(self, client_request_id: str) -> JobRecord | None:
        with self._lock:
            job_id = self._by_request.get(client_request_id)
        return self.get_record(job_id) if job_id else None

    def create_batch_job(
        self,
        *,
        client_request_id: str,
        model_id: str,
        asset_category: str,
        tasks: list[tuple[str, str, dict]],
        compute: dict,
        batch: BatchRef,
    ) -> tuple[JobRecord, bool]:
        """One ordinary job for one batch group: the model is loaded once for every task (§13.9).

        ``tasks`` = ``(task_id, prompt, options)``. Idempotent on ``client_request_id``. Raises ``ApiError`` (422)
        with every validation error; nothing is stored then.
        """
        with self._create_lock:
            existing = self.find_by_request(client_request_id)
            if existing is not None:
                return existing, False
            checked = self.validate_batch(model_id, asset_category, tasks, compute)
            if checked.errors:
                raise ApiError(422, checked.errors, checked.warnings)
            caps, plan = checked.capabilities, checked.plan
            assert caps is not None and plan is not None and plan.accelerator_id is not None
            now = self.clock()
            job_id = self._new_job_id()
            timeout, deadline = self._time_limits(plan)
            record = JobRecord(
                contract_version=CONTRACT_VERSION,
                job_id=job_id,
                status="created",
                status_history=[StatusEntry(status="created", at=now)],
                request=RequestRecord(
                    pipeline_type="text_to_2d",
                    asset_category=asset_category,
                    model_id=model_id,
                    prompt=None,
                    output_format="png",
                    options={},
                    inputs=[],
                    tasks=[
                        GenerationTask(
                            task_id=task_id, prompt=prompt, options=normalize_options(caps, options)
                        )
                        for (task_id, _, options), prompt in zip(tasks, checked.prompts, strict=True)
                    ],
                    batch=batch,
                ),
                compute=ComputeView(
                    profile_id=compute["profile_id"], accelerator_id=plan.accelerator_id, resource_plan=plan
                ),
                warnings=checked.warnings,
                execution=Execution(backend=self.client.mode),
                created_at=now,
                updated_at=now,
                internal=InternalState(
                    client_request_id=client_request_id,
                    original_request={"batch": batch.model_dump(mode="json"), "model_id": model_id},
                    timeout_seconds=timeout,
                    deadline_seconds=deadline,
                    created_ns=time.time_ns(),
                ),
                scheduling=SchedulingRecord(  # always auto-run (§14.1)
                    auto_run=True, run_requested_at=now, requested_ns=time.time_ns()
                ),
            )
            with self._lock:
                self._jobs[job_id] = record
                self._by_request[client_request_id] = job_id
                self.store.save(record)
            self.log(
                job_id,
                f"Batch job created: {len(tasks)} task(s) of {batch.manifest_id}/{batch.group_id} "
                f"(attempt {batch.attempt}) with {model_id} on {compute['profile_id']}/{plan.accelerator_id}; "
                f"plan fit {plan.fit}.",
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
        if original.request.batch is not None:  # OD-10: a batch retry must update its manifest
            raise api_error(
                409,
                "JOB_NOT_RETRYABLE",
                None,
                "This job belongs to a character batch. Retry its failed tasks from the batch instead.",
                {"reason": "use_batch_retry", "manifest_id": original.request.batch.manifest_id},
            )
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
        # A retry is a new, ungrouped job that runs by itself (§14.4).
        request = {
            **original.internal.original_request,
            "client_request_id": str(body.client_request_id),
            "auto_run": True,
        }
        return self.create_job(request, retry_source=original)

    # --- run control and run groups (§14.4, §14.5) ------------------------------------------------------------

    @staticmethod
    def _parse(model: type, raw: object, what: str):
        try:
            return model.model_validate(raw)
        except ValidationError as exc:
            raise ApiError(
                422,
                [
                    error(
                        "REQUEST_FIELD_INVALID",
                        ".".join(str(p) for p in e["loc"]) or None,
                        f"Invalid {what} request.",
                    )
                    for e in exc.errors(include_url=False)
                ],
            ) from exc

    def _hold(self, record: JobRecord, note: str) -> None:
        """Back to held: auto-run off, out of the FIFO and out of any group (call with the lock held)."""
        record = record.model_copy(deep=True)
        record.scheduling = SchedulingRecord(auto_run=False, run_requested_at=None)
        record.updated_at = self.clock()
        self.commit(record)
        self.log(record.job_id, note)

    def _release_partner(self, record: JobRecord, note: str) -> None:
        """A group cannot change once created (§14.4): the other waiting job is held again."""
        for partner in self._members(record):
            if partner.job_id != record.job_id and self.queue_state(partner) in ("held", "waiting"):
                self._hold(partner, note)

    def set_auto_run(self, job_id: str, raw: object) -> JobRecord:
        """``PATCH /jobs/{id}``: only held or waiting jobs; idempotent."""
        body = self._parse(AutoRunBody, raw, "auto-run")
        with self._lock:
            record = self.require(job_id)
            state = self.queue_state(record)
            if state not in ("held", "waiting"):
                raise api_error(
                    409,
                    "JOB_ALREADY_STARTED",
                    None,
                    "This job has already started, so its auto-run setting can no longer change.",
                    {"status": record.status},
                )
            if body.auto_run and state == "held":
                record.scheduling.auto_run = True
                record.scheduling.run_requested_at = self.clock()
                record.scheduling.requested_ns = time.time_ns()
                record.updated_at = self.clock()
                self.commit(record)
                self.log(job_id, "Auto-run turned on: the job joined the end of the run queue.")
            elif not body.auto_run and state == "waiting":
                grouped = record.scheduling.group_id is not None
                self._release_partner(
                    record, "Auto-run was turned off on the other job of its run group; held."
                )
                self._hold(
                    record,
                    "Auto-run turned off: the job is held"
                    + (" and its run group is dissolved." if grouped else "."),
                )
        if self._scheduler is not None:
            self._scheduler.notify()
        return self.require(job_id)

    def _group_invalid(self, reason: str, message: str, job_id: str | None = None) -> ApiError:
        details = {"reason": reason, **({"job_id": job_id} if job_id else {})}
        return api_error(422, "JOB_GROUP_INVALID", "job_ids", message, details)

    def create_group(self, raw: object) -> RunGroup:
        """``POST /jobs/groups``: two held Text→2D jobs in one Kaggle session, one per T4 (§14.4)."""
        body = self._parse(JobIdsBody, raw, "run group")
        ids = body.job_ids
        with self._lock:
            records = []
            for job_id in ids:
                record = self._jobs.get(job_id) if is_valid_id("job_id", job_id) else None
                if record is None:
                    raise api_error(404, "JOB_NOT_FOUND", "job_ids", "Job not found.", {"job_id": job_id})
                records.append(record)
            for record in records:
                state = self.queue_state(record)
                if state == "waiting":
                    raise self._group_invalid(
                        "not_held", "Only held jobs can be grouped. Turn auto-run off first.", record.job_id
                    )
                if state != "held":
                    raise api_error(
                        409,
                        "JOB_ALREADY_STARTED",
                        "job_ids",
                        "This job has already started and cannot be grouped.",
                        {"job_id": record.job_id, "status": record.status},
                    )
            if len(ids) != 2 or len(set(ids)) != 2:
                raise self._group_invalid("count", "A run group has exactly two different jobs.")
            for record in records:
                if record.request.pipeline_type != "text_to_2d":
                    raise self._group_invalid("pipeline", "Only Text→2D jobs can be grouped.", record.job_id)
                if record.request.batch is not None or record.request.tasks is not None:
                    raise self._group_invalid(
                        "batch", "Character batch jobs cannot be grouped.", record.job_id
                    )
            first, second = records
            if first.compute.profile_id != second.compute.profile_id:
                raise self._group_invalid("profile", "Both jobs must use the same compute profile.")
            for record in records:
                if record.compute.accelerator_id != "gpu_t4x2":
                    raise self._group_invalid(
                        "accelerator", "Both jobs must run on GPU T4 ×2 (one job per T4).", record.job_id
                    )
            accelerator = self._accelerator(first.compute.profile_id, "gpu_t4x2")
            per_gpu = accelerator.vram_bytes_per_device if accelerator is not None else None
            for record in records:
                caps = self.registry.get(record.request.model_id)
                if caps is None or caps.runtime.multi_gpu != "unsupported":
                    raise self._group_invalid(
                        "multi_gpu", "Only models that use a single GPU can be grouped.", record.job_id
                    )
                need = caps.runtime.minimum_gpu_vram_bytes
                if need is None or per_gpu is None or need > per_gpu:
                    raise self._group_invalid(
                        "vram",
                        "The model's GPU memory need is unknown or larger than one GPU of the accelerator.",
                        record.job_id,
                    )
            used = {r.scheduling.group_id for r in self._jobs.values()}
            group_id = f"grp_{secrets.token_hex(6)}"
            while group_id in used:
                group_id = f"grp_{secrets.token_hex(6)}"
            now, now_ns = self.clock(), time.time_ns()
            for index, record in enumerate(records):
                record = record.model_copy(deep=True)
                record.scheduling = SchedulingRecord(
                    auto_run=True,
                    run_requested_at=now,
                    requested_ns=now_ns,
                    group_id=group_id,
                    group_job_ids=list(ids),
                    gpu_index=index,
                )
                record.updated_at = now
                self.commit(record)
                partner = ids[1 - index]
                self.log(record.job_id, f"Run group {group_id} with {partner} (GPU {index}): waiting to run.")
        if self._scheduler is not None:
            self._scheduler.notify()
        return RunGroup(
            contract_version=CONTRACT_VERSION, group_id=group_id, job_ids=list(ids), run_requested_at=now
        )

    # --- deletion (§14.6) --------------------------------------------------------------------------------------

    def delete_job(self, job_id: str) -> None:
        """Terminal, held or waiting jobs. Uses the same lock as taking a session slot."""
        with self._lock:
            record = self.require(job_id)
            state = self.queue_state(record)
            terminal = record.status in TERMINAL_STATUSES
            if not terminal and state != "held" and not (state == "waiting" and record.request.batch is None):
                batch = state == "waiting"
                raise api_error(
                    409,
                    "JOB_NOT_TERMINAL",
                    None,
                    "A waiting character batch job cannot be deleted."
                    if batch
                    else "Only completed, failed, held or waiting jobs can be deleted.",
                    {"status": record.status, "queue_state": state},
                )
            if not terminal:
                self._release_partner(record, "The other job of its run group was deleted; held.")
            self.store.delete(job_id, [self.logs.log_path(job_id), self.logs.telemetry_path(job_id)])
            self._jobs.pop(job_id, None)
            self._by_request.pop(record.internal.client_request_id, None)
            self.logs.forget(job_id)

    def delete_jobs(self, raw: object) -> BulkDeleteResult:
        """``POST /jobs/delete``: each ID exactly as ``DELETE /jobs/{id}``, with a result per ID."""
        ids = self._parse(JobIdsBody, raw, "bulk delete").job_ids
        if not 1 <= len(ids) <= 200 or len(set(ids)) != len(ids):
            raise api_error(422, "REQUEST_FIELD_INVALID", "job_ids", "Send 1 to 200 different job IDs.")
        deleted, refused = [], []
        for job_id in ids:
            if not is_valid_id("job_id", job_id):
                refused.append(RefusedDelete(job_id=job_id, code="JOB_NOT_FOUND"))
                continue
            try:
                self.delete_job(job_id)
            except ApiError as exc:
                code = exc.errors[0].code if exc.errors else "JOB_NOT_TERMINAL"
                refused.append(RefusedDelete(job_id=job_id, code=code))
            else:
                deleted.append(job_id)
        if deleted and self._scheduler is not None:
            self._scheduler.notify()
        return BulkDeleteResult(contract_version=CONTRACT_VERSION, deleted=deleted, refused=refused)

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

    # --- public views (§14.1) --------------------------------------------------------------------------------

    def _positions(self) -> dict[str, int]:
        return {job_id: index + 1 for index, entry in enumerate(self.fifo()) for job_id in entry.job_ids}

    def scheduling(self, record: JobRecord, positions: dict[str, int] | None = None) -> Scheduling:
        state = self.queue_state(record)
        if state == "waiting" and positions is None:
            positions = self._positions()
        sched = record.scheduling
        return Scheduling(
            auto_run=sched.auto_run,
            queue_state=state,
            queue_position=(positions or {}).get(record.job_id) if state == "waiting" else None,
            run_requested_at=sched.run_requested_at if sched.auto_run else None,
            group_id=sched.group_id,
            group_job_ids=list(sched.group_job_ids),
            gpu_index=sched.gpu_index if sched.gpu_index in (0, 1) else None,
        )

    def result(self, record: JobRecord) -> GenerationResult:
        return to_result(record, self.scheduling(record))

    def summaries(self, records: list[JobRecord]) -> list[JobSummary]:
        positions = self._positions()
        return [to_summary(r, self.scheduling(r, positions)) for r in records]
