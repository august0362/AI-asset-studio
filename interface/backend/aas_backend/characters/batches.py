"""Batch manifests (CONTRACTS §13.4.10, §13.5.6, §13.9): building, grouping, submission as v1 jobs, reconciliation.

A task group becomes one ordinary v1 job; the model is loaded once per job. Task results are reconciled **on read**
from the job records: no hook is added to the job worker.
"""

from __future__ import annotations

import secrets
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from models.contracts import ErrorItem, error

from ..errors import ApiError
from ..schemas import BatchRef
from .contracts import (
    BatchAttempt,
    BatchTask,
    ComputeSelection,
    ProductionTask,
    ReferenceUse,
    StoredManifest,
    TaskGroup,
    TaskResult,
)
from .workflow import task_options

if TYPE_CHECKING:
    from .service import CharacterService

PREVIEW_PURPOSE = "full_body"  # a concept preview shows the whole character
MICRO_BATCH_SIZE = 1  # the M4 models' measured peaks leave no room for two images at once on a T4


def new_manifest_id() -> str:
    return f"bat_{secrets.token_hex(6)}"


def compute_dict(selection: ComputeSelection) -> dict[str, Any]:
    """§13.6.1 ``ComputeSelection``: ``"auto"`` means the planner recommends one (v1 ``accelerator_id: null``)."""
    accelerator = None if selection.accelerator_id == "auto" else selection.accelerator_id
    return {"profile_id": selection.profile_id, "accelerator_id": accelerator}


def derive(manifest: StoredManifest) -> None:
    """``status`` and ``retryable_task_ids`` from the task results (§13.5.6)."""
    statuses = [r.status for r in manifest.results]
    if not manifest.attempts:
        manifest.status = "ready"
    elif "pending" in statuses:
        manifest.status = "submitted"
    elif all(s == "succeeded" for s in statuses):
        manifest.status = "completed"
    elif "succeeded" not in statuses:
        manifest.status = "failed"
    else:
        manifest.status = "partially_completed"
    running = manifest.attempts and "pending" in statuses
    manifest.retryable_task_ids = (
        [] if running else [r.task_id for r in manifest.results if r.status in ("failed", "not_run")]
    )
    manifest.expected_model_loads = len(manifest.groups)


def _task_error(code: str, message: str, details: dict[str, Any]) -> ErrorItem:
    return error(code, None, message, details, retryable=True)


class BatchService:
    def __init__(self, service: CharacterService) -> None:
        self.svc = service

    # --- building -----------------------------------------------------------------------------------------------

    def build(
        self,
        *,
        character_id: str,
        kind: str,
        model_id: str,
        tasks: list[ProductionTask],
        approved_spec_revision: int,
        prompt_set_revision: int | None,
        concept_revision: int | None,
        reference_ids: list[str],
        manifest_id: str | None = None,
    ) -> StoredManifest:
        """Groups tasks by (model, revision, pipeline): one group per model, so one load per job (§13.4.10)."""
        caps = self.svc.registry.get(model_id)
        revision = self.svc.model_revision(model_id)
        per_image = caps.runtime.estimated_runtime_seconds if caps else None
        groups: OrderedDict[tuple, list[str]] = OrderedDict()
        for task in tasks:
            groups.setdefault((model_id, revision, "text_to_2d"), []).append(task.task_id)
        group_rows = []
        group_of: dict[str, str] = {}
        for number, ((gm, gr, _), ids) in enumerate(groups.items(), start=1):
            group_id = f"g{number:02d}"
            group_rows.append(
                TaskGroup(
                    group_id=group_id,
                    model_id=gm,
                    model_revision=gr,
                    task_ids=ids,
                    micro_batch_size=MICRO_BATCH_SIZE,
                    estimated_runtime_seconds=per_image * len(ids) if per_image else None,
                )
            )
            group_of.update(dict.fromkeys(ids, group_id))
        has_image_role = bool(caps and "style_reference" in caps.inputs.supported_image_roles)
        references = [
            ReferenceUse(
                asset_id=ref,
                applied=False,
                reason="batch_image_inputs_not_supported" if has_image_role else "model_has_no_image_role",
            )
            for ref in reference_ids
        ]
        now = self.svc.clock()
        manifest = StoredManifest(
            contract_version="1.1",
            manifest_id=manifest_id or new_manifest_id(),
            character_id=character_id,
            kind=kind,
            status="ready",
            approved_spec_revision=approved_spec_revision,
            prompt_set_revision=prompt_set_revision,
            concept_revision=concept_revision,
            target_model_id=model_id,
            model_revision=revision,
            references=references,
            tasks=[BatchTask(**t.model_dump(), group_id=group_of[t.task_id]) for t in tasks],
            groups=group_rows,
            expected_model_loads=len(group_rows),
            attempts=[],
            results=[
                TaskResult(
                    task_id=t.task_id,
                    status="pending",
                    attempt=None,
                    job_id=None,
                    artifact_id=None,
                    sha256=None,
                    error=None,
                    artifact_missing=False,
                )
                for t in tasks
            ],
            retryable_task_ids=[],
            created_at=now,
            updated_at=now,
        )
        derive(manifest)
        return manifest

    def production_tasks(self, prompt_set) -> list[ProductionTask]:
        """The S4 tasks with the production profile's options folded in (the manifest is self-contained)."""
        base = prompt_set.production_profile.options if prompt_set.production_profile else {}
        return [t.model_copy(update={"options": {**base, **t.options}}) for t in prompt_set.tasks]

    def preview_tasks(self, content) -> list[ProductionTask]:
        profile = content.preview_profile
        return [
            ProductionTask(
                task_id=f"preview_{index:02d}",
                purpose=PREVIEW_PURPOSE,
                prompt=content.preview_prompt,
                negative_prompt=None,
                seed=None,  # previews may use random seeds (OD-05)
                width=profile.width,
                height=profile.height,
                options=dict(profile.options),
            )
            for index in range(1, profile.variations + 1)
        ]

    # --- submission ---------------------------------------------------------------------------------------------

    def job_tasks(self, manifest: StoredManifest, task_ids: list[str]) -> list[tuple[str, str, dict]]:
        by_id = {t.task_id: t for t in manifest.tasks}
        return [(i, by_id[i].prompt, task_options(by_id[i])) for i in task_ids]

    def validate(
        self, manifest: StoredManifest, groups: dict[str, list[str]], compute: dict
    ) -> list[ErrorItem]:
        errors: list[ErrorItem] = []
        models = {g.group_id: g.model_id for g in manifest.groups}
        for group_id, ids in groups.items():
            checked = self.svc.jobs.validate_batch(
                models[group_id], "character", self.job_tasks(manifest, ids), compute
            )
            errors += checked.errors
        return errors

    def launch(
        self, manifest: StoredManifest, groups: dict[str, list[str]], compute: dict, request_id: str
    ) -> StoredManifest:
        """One v1 job per group, for the given tasks only. Validates every group before creating any job."""
        errors = self.validate(manifest, groups, compute)
        if errors:
            raise ApiError(422, errors)
        attempt = max((a.attempt for a in manifest.attempts), default=0) + 1
        models = {g.group_id: g.model_id for g in manifest.groups}
        try:
            for group_id, ids in groups.items():
                record, _ = self.svc.jobs.create_batch_job(
                    client_request_id=f"{request_id}:{group_id}",
                    model_id=models[group_id],
                    asset_category="character",
                    tasks=self.job_tasks(manifest, ids),
                    compute=compute,
                    batch=BatchRef(
                        character_id=manifest.character_id,
                        manifest_id=manifest.manifest_id,
                        group_id=group_id,
                        attempt=attempt,
                        task_ids=ids,
                    ),
                )
                manifest.attempts.append(
                    BatchAttempt(
                        attempt=attempt,
                        group_id=group_id,
                        job_id=record.job_id,
                        task_ids=ids,
                        submitted_at=record.created_at,
                    )
                )
                for result in manifest.results:
                    if result.task_id in ids:
                        result.status = "pending"
                        result.attempt = attempt
                        result.job_id = record.job_id
                        result.artifact_id = None
                        result.sha256 = None
                        result.error = None
                        result.artifact_missing = False
        finally:  # whatever was created is recorded, even if a later group failed
            manifest.request_ids.append(request_id)
            manifest.updated_at = self.svc.clock()
            derive(manifest)
            self.svc.store.write_manifest(manifest)
        return manifest

    # --- reconciliation (§13.5.6) -------------------------------------------------------------------------------

    def reconcile(self, manifest: StoredManifest) -> StoredManifest:
        before = manifest.model_dump(mode="json")
        records: dict[str, Any] = {}

        def job(job_id: str):
            if job_id not in records:
                records[job_id] = self.svc.jobs.get_record(job_id)
            return records[job_id]

        for result in manifest.results:
            if result.job_id is None:
                continue
            record = job(result.job_id)
            if result.status == "pending":
                self._settle(result, record)
            if result.status == "succeeded":
                result.artifact_missing = record is None or not any(
                    a.artifact_id == result.artifact_id for a in record.artifacts
                )
        derive(manifest)
        if manifest.model_dump(mode="json") != before:
            manifest.updated_at = self.svc.clock()
            self.svc.store.write_manifest(manifest)
        return manifest

    @staticmethod
    def _settle(result: TaskResult, record) -> None:
        if record is None:
            result.status = "failed"
            result.error = _task_error(
                "BATCH_TASK_FAILED",
                "The job of this task was deleted before its result was recorded.",
                {"message": "job deleted", "job_id": result.job_id},
            )
            return
        if record.status not in ("completed", "failed"):
            return
        if record.status == "failed":
            result.status = "failed"  # no per-task report: the job's own error (§13.5.6)
            result.error = record.error or _task_error(
                "BATCH_TASK_FAILED", "The job failed.", {"message": None}
            )
            return
        artifact = next((a for a in record.artifacts if a.task_id == result.task_id), None)
        if artifact is not None:
            result.status = "succeeded"
            result.artifact_id = artifact.artifact_id
            result.sha256 = artifact.sha256
            result.error = None
            return
        partial = next((w for w in record.warnings if w.code == "BATCH_PARTIAL"), None)
        entry = (partial.details.get("tasks", {}) if partial else {}).get(result.task_id) or {}
        if entry.get("status") == "not_run":
            result.status = "not_run"
            result.error = _task_error(
                "BATCH_TASK_NOT_RUN",
                entry.get("message") or "The job ended before this task started.",
                {"reason": entry.get("reason") or "job_failed"},
            )
        else:
            result.status = "failed"
            message = entry.get("message") or "The job reported no image for this task."
            result.error = _task_error("BATCH_TASK_FAILED", message, {"message": message})
