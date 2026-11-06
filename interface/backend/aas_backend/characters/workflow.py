"""Read-side of one character: derived stage state, staleness, approval gates and content rules.

Everything here is computed on read (CONTRACTS §13.5.3, §13.5.4) and never stored, so it cannot drift. A
``CharacterView`` is used under the character's lock; it caches what it reads for the duration of one request.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models.contracts import ErrorItem, error
from models.registry import check_option

from ..orchestrator.records import JobRecord
from ..storage.paths import safe_path
from . import config
from .contracts import (
    STAGE_IDS,
    ApprovalChecklist,
    ApprovedSnapshot,
    AssetSource,
    CharacterSummary,
    ConceptCandidate,
    JobReference,
    ProductionItem,
    ProductionTask,
    PromptSet,
    StageConfig,
    StageDraft,
    StageRevision,
    StageState,
    StaleReason,
    StoredManifest,
)
from .store import StageRecord

if TYPE_CHECKING:
    from .service import CharacterService

API = "/api/v1"
EMPTY_CONTENT: dict[str, dict[str, Any]] = {
    "s1": {"stage_id": "s1"},
    "s2": {"stage_id": "s2"},
    "s3": {"stage_id": "s3"},
    "s4": {"stage_id": "s4"},
    "s5": {"stage_id": "s5"},
    "s6": {"stage_id": "s6"},
    "s7": {"stage_id": "s7"},
}
# S4 approval checks that the batch fits one session; quota and authentication change over time and are checked
# when the batch is submitted instead.
_S4_COMPUTE_CODES = {"COMPUTE_SESSION_LIMIT_EXCEEDED", "COMPUTE_VRAM_INSUFFICIENT"}


def incomplete(field: str | None, message: str, rule: str, **details: Any) -> ErrorItem:
    return error("STAGE_CONTENT_INCOMPLETE", field, message, {"rule": rule, **details})


def task_options(task: ProductionTask, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """The model options of one production task: profile defaults, the task's overrides, then its own fields."""
    options = {**(base or {}), **task.options, "seed": task.seed, "width": task.width, "height": task.height}
    if task.negative_prompt is not None:
        options["negative_prompt"] = task.negative_prompt
    return options


@dataclass
class ImageRef:
    """An image that approval would freeze, or the reason it cannot be used."""

    path: Path | None = None
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    mime_type: str | None = None
    source: AssetSource | None = None
    reference_id: str | None = None
    problem: ErrorItem | None = None


class CharacterView:
    def __init__(self, service: CharacterService, character) -> None:
        self.svc = service
        self.store = service.store
        self.character = character
        self.cid = character.character_id
        self._records: dict[str, StageRecord] = {}
        self._drafts: dict[str, StageDraft] = {}
        self._revisions: dict[tuple[str, int], StageRevision | None] = {}
        self._manifests: dict[str, StoredManifest] | None = None
        self._references = None

    # --- raw reads ----------------------------------------------------------------------------------------------

    def config(self, stage_id: str) -> StageConfig:
        return config.stage_config(stage_id, self.svc.registry)

    def record(self, stage_id: str) -> StageRecord:
        if stage_id not in self._records:
            self._records[stage_id] = self.store.read_stage(self.cid, stage_id)
        return self._records[stage_id]

    def set_record(self, stage_id: str, record: StageRecord) -> None:
        self.store.write_stage(self.cid, stage_id, record)
        self._records[stage_id] = record

    def draft(self, stage_id: str) -> StageDraft:
        if stage_id not in self._drafts:
            self._drafts[stage_id] = self.store.read_draft(self.cid, stage_id) or StageDraft.model_validate(
                {
                    "contract_version": "1.1",
                    "character_id": self.cid,
                    "stage_id": stage_id,
                    "draft_version": 0,
                    "based_on_revision": None,
                    "content": EMPTY_CONTENT[stage_id],
                    "checklist": {"items": []},
                    "updated_at": None,
                }
            )
        return self._drafts[stage_id]

    def set_draft(self, draft: StageDraft) -> None:
        self.store.write_draft(draft)
        self._drafts[draft.stage_id] = draft

    def revision(self, stage_id: str, number: int | None) -> StageRevision | None:
        if number is None:
            return None
        key = (stage_id, number)
        if key not in self._revisions:
            self._revisions[key] = self.store.read_revision(self.cid, stage_id, number)
        return self._revisions[key]

    def forget_revision(self, stage_id: str, number: int) -> None:
        self._revisions.pop((stage_id, number), None)

    def approved(self, stage_id: str) -> StageRevision | None:
        return self.revision(stage_id, self.record(stage_id).approved_revision)

    def pending(self, stage_id: str) -> StageRevision | None:
        return self.revision(stage_id, self.record(stage_id).pending_revision)

    def references(self):
        if self._references is None:
            self._references = {r.reference_id: r for r in self.store.list_references(self.cid)}
        return self._references

    def manifests(self) -> dict[str, StoredManifest]:
        """Every batch of this character, reconciled with its jobs (§13.5.6)."""
        if self._manifests is None:
            self._manifests = {}
            for manifest in self.store.list_manifests(self.cid):
                self._manifests[manifest.manifest_id] = self.svc.batches.reconcile(manifest)
        return self._manifests

    def put_manifest(self, manifest: StoredManifest) -> None:
        self.store.write_manifest(manifest)
        self.manifests()[manifest.manifest_id] = manifest

    # --- derived state (§13.5.3, §13.5.4) -----------------------------------------------------------------------

    def availability(self, stage_id: str) -> str:
        return config.availability(stage_id, self.svc.registry)[0]

    def has_changes(self, stage_id: str) -> bool:
        draft = self.draft(stage_id)
        return (
            draft.draft_version > 0 and draft.draft_version != self.record(stage_id).submitted_draft_version
        )

    def stale_reasons(self, stage_id: str) -> list[StaleReason]:
        approved = self.approved(stage_id)
        if approved is None:
            return []
        reasons = []
        for upstream, _kind in config.dependencies(stage_id):
            used = approved.source_revisions.get(upstream)
            current = self.record(upstream).approved_revision
            if used is not None and current is not None and used != current:
                reasons.append(
                    StaleReason(upstream_stage_id=upstream, used_revision=used, current_revision=current)
                )
        return reasons

    def snapshot(self, stage_id: str) -> ApprovedSnapshot | None:
        approved = self.approved(stage_id)
        if approved is None:
            return None
        reasons = self.stale_reasons(stage_id)
        return ApprovedSnapshot(
            revision=approved.revision,
            approved_at=approved.decided_at or approved.submitted_at,
            source_revisions=approved.source_revisions,
            stale=bool(reasons),
            stale_reasons=reasons,
        )

    def status(self, stage_id: str) -> str:
        record = self.record(stage_id)
        if record.pending_revision is not None:
            return "in_review"
        approved = record.approved_revision is not None
        if record.last_decision == "revision_requested" or (approved and self.stale_reasons(stage_id)):
            return "needs_revision"
        if self.has_changes(stage_id):
            return "draft"
        if approved:
            return "approved"
        if record.latest_revision is None and any(
            self.record(u).approved_revision is None
            for u, kind in config.dependencies(stage_id)
            if kind == "hard"
        ):
            return "blocked"
        return "not_started"

    def state(self, stage_id: str, *, blockers: bool = True) -> StageState:
        record = self.record(stage_id)
        problems: list[ErrorItem] = []
        if blockers:
            pending = self.pending(stage_id)
            if pending is not None:
                problems = self.approval_problems(
                    stage_id, pending.content, pending.checklist, pending.source_revisions
                )
            else:
                draft = self.draft(stage_id)
                problems = self.approval_problems(stage_id, draft.content, draft.checklist, None)
        return StageState(
            stage_id=stage_id,
            editorial_status=self.status(stage_id),
            availability=self.availability(stage_id),
            draft_version=self.draft(stage_id).draft_version,
            has_unsubmitted_changes=self.has_changes(stage_id),
            latest_revision=record.latest_revision,
            pending_revision=record.pending_revision,
            approved=self.snapshot(stage_id),
            last_decision=record.last_decision,
            blockers=problems,
        )

    def summary(self) -> CharacterSummary:
        statuses = {s: self.status(s) for s in STAGE_IDS}
        current = next((s for s in STAGE_IDS if statuses[s] != "approved"), "s7")
        cover = self.character.cover_asset_id
        return CharacterSummary(
            character_id=self.cid,
            name=self.character.name,
            tags=self.character.tags,
            cover_url=f"{API}/characters/{self.cid}/assets/{cover}/content" if cover else None,
            current_stage=current,
            approved_count=sum(1 for s in STAGE_IDS if statuses[s] == "approved"),
            stage_statuses=statuses,
            updated_at=self.character.updated_at,
        )

    def source_revisions(self, stage_id: str) -> dict[str, int]:
        """The approved revision of every dependency, as a submit now would record them."""
        sources = {}
        for upstream, _kind in config.dependencies(stage_id):
            current = self.record(upstream).approved_revision
            if current is not None:
                sources[upstream] = current
        return sources

    # --- approval gate (§13.5.2) --------------------------------------------------------------------------------

    def approval_problems(
        self, stage_id: str, content, checklist: ApprovalChecklist, source_revisions: dict[str, int] | None
    ) -> list[ErrorItem]:
        """Every reason ``approve`` would fail. ``source_revisions`` is ``None`` for a draft (not submitted yet)."""
        problems: list[ErrorItem] = []
        state, reason = config.availability(stage_id, self.svc.registry)
        if state != "available":
            problems.append(
                error(
                    "STAGE_NOT_AVAILABLE",
                    "stage_id",
                    f"Stage {stage_id.upper()} is {state}.",
                    {"availability": state, "reason": reason},
                )
            )
            return problems
        for upstream, kind in config.dependencies(stage_id):
            if kind != "hard":
                continue
            current = self.record(upstream).approved_revision
            if current is None:
                problems.append(
                    error(
                        "STAGE_BLOCKED",
                        "stage_id",
                        f"Stage {upstream.upper()} has no approved revision yet.",
                        {"stage_id": upstream},
                    )
                )
            elif source_revisions is not None and source_revisions.get(upstream) != current:
                problems.append(
                    error(
                        "STAGE_UPSTREAM_CHANGED",
                        "stage_id",
                        f"Stage {upstream.upper()} was approved again after this revision was submitted. Submit again.",
                        {
                            "stage_id": upstream,
                            "used_revision": source_revisions.get(upstream),
                            "current_revision": current,
                        },
                    )
                )
        checked = {item.item_id for item in checklist.items if item.checked}
        missing = [i for i in config.required_checklist(stage_id) if i not in checked]
        if missing:
            problems.append(
                error(
                    "STAGE_CHECKLIST_INCOMPLETE",
                    "checklist",
                    "Required checklist items are not checked.",
                    {"item_ids": missing},
                )
            )
        problems += self.content_problems(stage_id, content)
        return problems

    # --- content rules (CHARACTER_WORKFLOW §3) ------------------------------------------------------------------

    def content_problems(self, stage_id: str, content) -> list[ErrorItem]:
        rules = {
            "s1": self._rules_s1,
            "s2": self._rules_s2,
            "s3": self._rules_s3,
            "s4": self._rules_s4,
            "s5": self._rules_s5,
        }
        return rules[stage_id](content) if stage_id in rules else []

    def _rules_s1(self, c) -> list[ErrorItem]:
        problems = []
        if not (c.idea or "").strip() and not c.references:
            problems.append(
                incomplete("content.idea", "Add an idea or at least one reference.", "idea_or_reference")
            )
        if not c.directions:
            problems.append(
                incomplete("content.directions", "Add at least one design direction.", "direction_required")
            )
        return problems

    def _rules_s2(self, c) -> list[ErrorItem]:
        problems = []
        if not any(a.lock == "locked" for a in c.attributes):
            problems.append(
                incomplete("content.attributes", "Lock at least one attribute.", "locked_attribute_required")
            )
        ids = [a.attribute_id for a in c.attributes]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            problems.append(
                incomplete(
                    "content.attributes",
                    "Attribute IDs must be unique.",
                    "attribute_ids_unique",
                    duplicates=duplicates,
                )
            )
        return problems

    def _rules_s3(self, c) -> list[ErrorItem]:
        selected = [cand for cand in c.candidates if cand.verdict == "selected"]
        if len(selected) != 1 or selected[0].candidate_id != c.selected_candidate_id:
            return [
                incomplete(
                    "content.candidates",
                    "Select exactly one candidate, and set it as the selected candidate.",
                    "one_selected_candidate",
                    selected=len(selected),
                )
            ]
        index = c.candidates.index(selected[0])
        image = self.candidate_image(selected[0], f"content.candidates[{index}]")
        return [image.problem] if image.problem else []

    def _rules_s4(self, c: PromptSet) -> list[ErrorItem]:
        problems = []
        purposes = [e.purpose for e in c.entries]
        repeated = sorted({p for p in purposes if purposes.count(p) > 1})
        if repeated:
            problems.append(
                incomplete(
                    "content.entries",
                    "Use at most one prompt entry per purpose.",
                    "entry_per_purpose",
                    purposes=repeated,
                )
            )
        for purpose in config.REQUIRED_PURPOSES:
            entry = next((e for e in c.entries if e.purpose == purpose), None)
            if entry is None or not entry.canonical_prompt.strip():
                problems.append(
                    incomplete(
                        "content.entries",
                        f"Required purpose '{purpose}' has no canonical prompt.",
                        "required_purpose_prompt",
                        purpose=purpose,
                    )
                )
            if not any(t.purpose == purpose for t in c.tasks):
                problems.append(
                    incomplete(
                        "content.tasks",
                        f"Required purpose '{purpose}' has no production task.",
                        "required_purpose_task",
                        purpose=purpose,
                    )
                )
        ids = [t.task_id for t in c.tasks]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            problems.append(
                incomplete(
                    "content.tasks", "Task IDs must be unique.", "task_ids_unique", duplicates=duplicates
                )
            )
        profile = c.production_profile
        if profile is None:
            problems.append(
                incomplete(
                    "content.production_profile",
                    "Choose the production model.",
                    "production_profile_required",
                )
            )
        elif c.tasks and not duplicates:
            checked = self.svc.validate_tasks(
                profile.target_model_id,
                [(t.task_id, t.prompt, task_options(t, profile.options)) for t in c.tasks],
                field_prefix="content.tasks",
            )
            for item in checked.errors:
                if item.code.startswith("COMPUTE_") and item.code not in _S4_COMPUTE_CODES:
                    continue
                problems.append(item)
        return problems

    def _rules_s5(self, c) -> list[ErrorItem]:
        problems = []
        selected = [item for item in c.items if item.selected]
        for purpose in config.REQUIRED_PURPOSES:
            count = sum(1 for item in selected if item.purpose == purpose)
            if count != 1:
                problems.append(
                    incomplete(
                        "content.items",
                        f"Select exactly one image for the required purpose '{purpose}'.",
                        "required_purpose_selected",
                        purpose=purpose,
                        selected=count,
                    )
                )
        purposes = [item.purpose for item in selected]
        repeated = sorted(
            {p for p in purposes if purposes.count(p) > 1 and p not in config.REQUIRED_PURPOSES}
        )
        for purpose in repeated:
            problems.append(
                incomplete(
                    "content.items",
                    f"Select at most one image for '{purpose}'.",
                    "one_selected_per_purpose",
                    purpose=purpose,
                )
            )
        for index, item in enumerate(c.items):
            if item.selected:
                image = self.item_image(item, f"content.items[{index}]")
                if image.problem:
                    problems.append(image.problem)
        return problems

    # --- images that approval freezes ----------------------------------------------------------------------------

    def candidate_image(self, candidate: ConceptCandidate, field: str) -> ImageRef:
        if candidate.source == "batch_task":
            return self.task_image(candidate.manifest_id, candidate.task_id, field)
        if candidate.source == "job_artifact":
            return self.job_image(candidate.job, f"{field}.job")
        return self.reference_image(candidate.reference_id, f"{field}.reference_id")

    def item_image(self, item: ProductionItem, field: str) -> ImageRef:
        if item.job is not None:
            return self.job_image(item.job, f"{field}.job")
        return self.task_image(item.manifest_id, item.task_id, field)

    def task_image(self, manifest_id: str | None, task_id: str | None, field: str) -> ImageRef:
        manifest = self.manifests().get(manifest_id or "")
        if manifest is None:
            return ImageRef(
                problem=error("BATCH_NOT_FOUND", f"{field}.manifest_id", "This batch does not exist.")
            )
        result = next((r for r in manifest.results if r.task_id == task_id), None)
        if result is None:
            return ImageRef(
                problem=error(
                    "REQUEST_FIELD_INVALID", f"{field}.task_id", "The batch has no task with this ID."
                )
            )
        if result.status != "succeeded":
            return ImageRef(
                problem=incomplete(
                    f"{field}.task_id",
                    "The selected task has no image.",
                    "selected_image_missing",
                    task_id=task_id,
                    task_status=result.status,
                )
            )
        return self.job_image(JobReference(job_id=result.job_id, artifact_id=result.artifact_id), field)

    def job_image(self, ref: JobReference | None, field: str) -> ImageRef:
        if ref is None:
            return ImageRef(problem=error("REQUEST_FIELD_INVALID", field, "A job reference is required."))
        record = self.svc.jobs.get_record(ref.job_id)
        if record is None:
            return ImageRef(
                problem=error(
                    "LINKED_JOB_NOT_FOUND", field, "The linked job no longer exists.", {"job_id": ref.job_id}
                )
            )
        if record.status != "completed":
            return ImageRef(
                problem=error(
                    "LINKED_JOB_NOT_COMPLETED",
                    field,
                    "The linked job has not completed.",
                    {"job_id": ref.job_id, "status": record.status},
                )
            )
        artifact = linked_artifact(record, ref.artifact_id)
        if artifact is None:
            return ImageRef(
                problem=error(
                    "LINKED_JOB_NOT_FOUND",
                    field,
                    "The linked artifact no longer exists.",
                    {"job_id": ref.job_id, "artifact_id": ref.artifact_id},
                )
            )
        if artifact.kind != "image" or artifact.format != "png":
            return ImageRef(
                problem=error(
                    "LINKED_ARTIFACT_INVALID",
                    field,
                    "Only PNG image artifacts can be used.",
                    {"job_id": ref.job_id, "artifact_id": artifact.artifact_id, "kind": artifact.kind},
                )
            )
        return ImageRef(
            path=safe_path(self.svc.data_root, artifact.path),
            sha256=artifact.sha256,
            width=artifact.width,
            height=artifact.height,
            mime_type="image/png",
            source=self.svc.asset_source(record, artifact),
        )

    def reference_image(self, reference_id: str | None, field: str) -> ImageRef:
        reference = self.references().get(reference_id or "")
        if reference is None:
            return ImageRef(problem=error("REFERENCE_NOT_FOUND", field, "This reference does not exist."))
        if reference.kind != "image":
            return ImageRef(
                problem=incomplete(
                    field, "A URL reference has no image to approve.", "reference_has_no_image"
                )
            )
        return ImageRef(
            path=self.svc.reference_file(self.cid, reference),
            sha256=reference.sha256,
            width=reference.width,
            height=reference.height,
            mime_type=reference.mime_type,
            reference_id=reference.reference_id,
        )


def linked_artifact(record: JobRecord, artifact_id: str | None):
    if artifact_id is None:
        return next((a for a in record.artifacts if a.is_primary), None)
    return next((a for a in record.artifacts if a.artifact_id == artifact_id), None)


def check_profile_options(model_id: str, options: dict[str, Any], registry, field: str) -> list[ErrorItem]:
    """Draft-time option check against the model's ``options_schema`` (MODEL_NOT_FOUND / MODEL_OPTION_*)."""
    caps = registry.get(model_id)
    if caps is None:
        return [error("MODEL_NOT_FOUND", f"{field}.model_id", f"Model '{model_id}' does not exist.")]
    if "text_to_2d" not in caps.supported_pipeline_types:
        return []  # reported on approval as MODEL_PIPELINE_INCOMPATIBLE (v1 stage 3)
    problems = []
    for name, value in options.items():
        spec = caps.options_schema.get(name)
        if spec is None:
            problems.append(
                error(
                    "MODEL_OPTION_UNSUPPORTED",
                    f"{field}.options.{name}",
                    f"{caps.display_name} does not support the option '{name}'.",
                    {"option": name, "supported_options": list(caps.options_schema)},
                )
            )
            continue
        problem = check_option(name, spec, value)
        if problem is not None:
            problems.append(problem.model_copy(update={"field": f"{field}.options.{name}"}))
    return problems
