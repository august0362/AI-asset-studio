"""Character Production service (CONTRACTS §13.5, §13.6.3). Owns every workflow rule; the routes only map HTTP.

It calls the v1 job service and upload store; it never calls the Kaggle CLI, imports ``kaggle_connector`` clients or
changes job records. Writes to one character are serialized by its lock.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import secrets
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import urlsplit

from PIL import Image
from pydantic import BaseModel, ValidationError

from models.contracts import ErrorItem, error

from ..errors import ApiError, api_error
from ..orchestrator.records import artifact_view
from ..storage.files import atomic_write_bytes
from ..storage.uploads import MIME_EXTENSIONS, PILLOW_FORMATS, sniff_mime
from . import config
from .batches import BatchService, compute_dict
from .contracts import (
    STAGE_IDS,
    V2_CONTRACT_VERSION,
    ArtifactReference,
    AssetSource,
    Character,
    CharacterList,
    CharacterWorkflow,
    CreateCharacterRequest,
    CreatePreviewBatchRequest,
    CreateReferenceRequest,
    HistoryPage,
    JobReference,
    OutputList,
    ReferenceAsset,
    ResolvedJob,
    RevisionPointer,
    RevisionSummary,
    SaveDraftRequest,
    StageDecisionRequest,
    StageDetail,
    StageDraft,
    StageHistory,
    StageInput,
    StageRevision,
    StoredManifest,
    SubmitBatchRequest,
    UpdateCharacterRequest,
    WorkflowStage,
)
from .store import CharacterStore, RevisionExists
from .workflow import CharacterView, ImageRef, check_profile_options, linked_artifact, task_options

if TYPE_CHECKING:
    from ..orchestrator.service import JobService

log = logging.getLogger("aas_backend")
M = TypeVar("M", bound=BaseModel)
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")
CONCEPT_PURPOSE = "key_visual"  # the frozen S3 concept image
PREVIEW_MANIFEST_ID = "bat_000000000000"  # manifest_preview is never stored; its ID is a fixed placeholder
DRAFT_HISTORY_SECONDS = 60


def _field_path(loc: tuple) -> str | None:
    parts: list[str] = []
    for index, part in enumerate(loc):
        if isinstance(part, int):
            parts[-1:] = [f"{parts[-1]}[{part}]"] if parts else [f"[{part}]"]
        elif index > 0 and loc[index - 1] == "content" and part in (*STAGE_IDS, "s6", "s7"):
            continue  # the discriminator tag of StageContent
        else:
            parts.append(str(part))
    return ".".join(parts) or None


def parse(model: type[M], raw: Any) -> M:
    """Schema check of a request body: ``REQUEST_FIELD_INVALID`` per problem, ``CONTRACT_VERSION_UNSUPPORTED`` for
    another major version (§13.1)."""
    if not isinstance(raw, dict):
        raise api_error(422, "REQUEST_FIELD_INVALID", None, "The request body must be a JSON object.")
    version = raw.get("contract_version")
    if isinstance(version, str):
        match = _VERSION_RE.match(version)
        if match and match.group(1) != "1":
            raise api_error(
                422,
                "CONTRACT_VERSION_UNSUPPORTED",
                "contract_version",
                f"Contract version {version} is not supported. This server implements 1.x.",
                {"supported_major": 1, "provided": version},
            )
        if not match:
            raise api_error(
                422, "REQUEST_FIELD_INVALID", "contract_version", "contract_version must look like '1.1'."
            )
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ApiError(
            422,
            [
                error(
                    "REQUEST_FIELD_INVALID",
                    _field_path(tuple(item["loc"])),
                    "Unknown field. Remove it; unknown fields are rejected."
                    if item["type"] == "extra_forbidden"
                    else f"Invalid value: {item['msg']}.",
                    {"type": item["type"]},
                )
                for item in exc.errors(include_url=False)
            ],
        ) from exc


def _field_error(field: str, message: str) -> ErrorItem:
    return error("REQUEST_FIELD_INVALID", field, message)


class CharacterService:
    def __init__(self, jobs: JobService) -> None:
        self.jobs = jobs
        self.registry = jobs.registry
        self.clock = jobs.clock
        self.data_root = jobs.data_root
        self.store = CharacterStore(self.data_root)
        self.batches = BatchService(self)
        swept = self.store.sweep_temp()
        if swept:
            log.info("swept %d interrupted character write(s)", swept)
        deleted = self.store.sweep_deleted()
        if deleted:
            log.info("removed %d interrupted character deletion(s)", deleted)
        self._index_lock = threading.Lock()
        self._requests: dict[str, tuple[str, str, str]] = {}
        for character_id in self.store.character_ids():
            for request_id, entry in self.store.read_requests(character_id).items():
                self._requests[request_id] = (character_id, entry.get("kind", ""), entry.get("id", ""))

    # --- helpers ------------------------------------------------------------------------------------------------

    def model_revision(self, model_id: str) -> str | None:
        caps = self.registry.get(model_id)
        if caps is None or not caps.accepts_jobs:
            return None
        return self.registry.adapter(model_id).model_revision()

    def default_compute(self) -> dict[str, Any]:
        enabled = [p for p in self.jobs.client.profiles() if p.enabled]
        return {"profile_id": enabled[0].profile_id if enabled else "default", "accelerator_id": None}

    def validate_tasks(self, model_id: str, tasks, field_prefix: str):
        from ..orchestrator.validation import validate_batch

        return validate_batch(
            model_id=model_id,
            asset_category="character",
            tasks=tasks,
            compute=self.default_compute(),
            registry=self.registry,
            client=self.jobs.client,
            field_prefix=field_prefix,
        )

    def asset_source(self, record, artifact) -> AssetSource:
        task = next((t for t in record.request.tasks or [] if t.task_id == artifact.task_id), None)
        prompt = task.prompt if task else record.request.prompt
        options = dict(task.options if task else record.request.options)
        seed = options.get("seed")
        return AssetSource(
            job_id=record.job_id,
            artifact_id=artifact.artifact_id,
            task_id=artifact.task_id,
            model_id=record.request.model_id,
            model_revision=self.model_revision(record.request.model_id),
            prompt=prompt,
            negative_prompt=options.get("negative_prompt"),
            seed=seed if isinstance(seed, int) and not isinstance(seed, bool) else None,
            width=artifact.width or 0,
            height=artifact.height or 0,
            options={
                k: v for k, v in options.items() if v is None or isinstance(v, int | float | str | bool)
            },
        )

    def reference_file(self, character_id: str, reference: ReferenceAsset) -> Path:
        extension = MIME_EXTENSIONS[reference.mime_type]
        return self.store.path(character_id, "references", f"{reference.reference_id}.{extension}")

    def _view(self, character_id: str) -> CharacterView:
        character = self.store.read_character(character_id)
        if character is None:
            raise api_error(404, "CHARACTER_NOT_FOUND", None, "Character not found.")
        return CharacterView(self, character)

    def _touch(self, view: CharacterView) -> None:
        view.character = view.character.model_copy(update={"updated_at": self.clock()})
        self.store.write_character(view.character)

    def _history(self, character_id: str, action: str, stage_id: str | None = None, **fields: Any) -> None:
        events = self.store.read_history(character_id)
        now = self.clock()
        if action == "draft_saved":
            last = next(
                (e for e in reversed(events) if e.action == "draft_saved" and e.stage_id == stage_id), None
            )
            if last is not None and (now - last.at).total_seconds() < DRAFT_HISTORY_SECONDS:
                return  # at most one draft_saved per stage per minute (§13.4.11)
        event = StageHistory(
            seq=(events[-1].seq + 1) if events else 1,
            at=now,
            stage_id=stage_id,
            action=action,
            revision=fields.get("revision"),
            manifest_id=fields.get("manifest_id"),
            affected_stages=fields.get("affected_stages", []),
            note=fields.get("note"),
        )
        self.store.append_history(character_id, event)

    def _remember(self, request_id: str, character_id: str, kind: str, item_id: str) -> None:
        with self._index_lock:
            self._requests[request_id] = (character_id, kind, item_id)
            data = self.store.read_requests(character_id)
            data[request_id] = {"kind": kind, "id": item_id}
            self.store.write_requests(character_id, data)

    def _known(self, request_id: str, kind: str) -> tuple[str, str] | None:
        with self._index_lock:
            entry = self._requests.get(request_id)
        if entry is None or entry[1] != kind:
            return None
        return entry[0], entry[2]

    # --- characters (routes 1-4) --------------------------------------------------------------------------------

    def list_characters(
        self, q: str | None, stage: str | None, status: str | None, limit: int, cursor: str | None
    ):
        rows = []
        for character_id in self.store.character_ids():
            with self.store.lock(character_id):
                character = self.store.read_character(character_id)
                if character is None:
                    continue
                summary = CharacterView(self, character).summary()
            if (
                q
                and q.lower() not in summary.name.lower()
                and not any(q.lower() in t.lower() for t in summary.tags)
            ):
                continue
            if stage is not None and summary.current_stage != stage:
                continue
            if status is not None and summary.stage_statuses[summary.current_stage] != status:
                continue
            rows.append(summary)
        rows.sort(key=lambda s: (s.updated_at, s.character_id), reverse=True)
        if cursor is not None:
            ids = [r.character_id for r in rows]
            if cursor not in ids:
                raise api_error(422, "REQUEST_FIELD_INVALID", "cursor", "Unknown or expired cursor.")
            rows = rows[ids.index(cursor) + 1 :]
        page = rows[:limit]
        return CharacterList(
            contract_version=V2_CONTRACT_VERSION,
            characters=page,
            next_cursor=page[-1].character_id if len(rows) > limit else None,
        )

    def create_character(self, raw: Any) -> Character:
        req = parse(CreateCharacterRequest, raw)
        known = self._known(str(req.client_request_id), "character")
        if known is not None and (existing := self.store.read_character(known[0])) is not None:
            return existing
        if len(set(req.tags)) != len(req.tags):
            raise api_error(422, "REQUEST_FIELD_INVALID", "tags", "Tags must be unique.")
        while True:
            character_id = f"chr_{secrets.token_hex(6)}"
            if not self.store.path(character_id).exists():
                break
        now = self.clock()
        character = Character(
            contract_version=V2_CONTRACT_VERSION,
            character_id=character_id,
            name=req.name,
            summary=req.summary,
            tags=req.tags,
            cover_asset_id=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        with self.store.lock(character_id):
            self.store.path(character_id).mkdir(parents=True)
            self.store.write_character(character)
            self._remember(str(req.client_request_id), character_id, "character", character_id)
            self._history(character_id, "character_created")
        return character

    def workflow(self, character_id: str) -> CharacterWorkflow:
        with self.store.lock(character_id):
            view = self._view(character_id)
            return CharacterWorkflow(
                contract_version=V2_CONTRACT_VERSION,
                character=view.character,
                stages=[WorkflowStage(config=view.config(s), state=view.state(s)) for s in STAGE_IDS],
                approved_outputs=self._approved_outputs(view),
            )

    def update_character(self, character_id: str, raw: Any) -> Character:
        req = parse(UpdateCharacterRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            current = view.character
            if req.expected_version != current.version:
                raise api_error(
                    409,
                    "CHARACTER_VERSION_CONFLICT",
                    None,
                    "The character changed since it was loaded. Reload it.",
                    {"current_version": current.version},
                )
            if req.tags is not None and len(set(req.tags)) != len(req.tags):
                raise api_error(422, "REQUEST_FIELD_INVALID", "tags", "Tags must be unique.")
            if (
                req.cover_asset_id is not None
                and self.store.read_asset(character_id, req.cover_asset_id) is None
            ):
                raise api_error(422, "ASSET_NOT_FOUND", "cover_asset_id", "This frozen asset does not exist.")
            changes = {
                k: v
                for k, v in {
                    "name": req.name,
                    "summary": req.summary,
                    "tags": req.tags,
                    "cover_asset_id": req.cover_asset_id,
                }.items()
                if v is not None
            }
            updated = current.model_copy(
                update={**changes, "version": current.version + 1, "updated_at": self.clock()}
            )
            updated = Character.model_validate(updated.model_dump())
            self.store.write_character(updated)
            self._history(character_id, "character_updated", note=", ".join(sorted(changes)) or None)
            return updated

    # --- stages (routes 5-9) ------------------------------------------------------------------------------------

    def delete_character(self, character_id: str) -> None:
        """Route 19 (D-038): remove the character's folder; the v1 jobs of its batches are kept."""
        with self.store.lock(character_id):
            view = self._view(character_id)
            running = sorted(
                manifest_id
                for manifest_id, manifest in view.manifests().items()
                if any(r.status == "pending" and r.attempt is not None for r in manifest.results)
            )
            if running:
                raise api_error(
                    409,
                    "BATCH_ATTEMPT_RUNNING",
                    None,
                    "A batch of this character is still running.",
                    {"manifest_ids": running},
                )
            self.store.delete_character(character_id)
            with self._index_lock:
                for request_id in [k for k, v in self._requests.items() if v[0] == character_id]:
                    del self._requests[request_id]
            log.info("deleted character %s", character_id)

    def stage_detail(self, character_id: str, stage_id: str) -> StageDetail:
        with self.store.lock(character_id):
            return self._detail(self._view(character_id), stage_id)

    def save_draft(self, character_id: str, stage_id: str, raw: Any) -> StageDetail:
        req = parse(SaveDraftRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            self._require_available(stage_id)
            draft = view.draft(stage_id)
            if req.expected_draft_version != draft.draft_version:
                raise api_error(
                    409,
                    "STAGE_DRAFT_CONFLICT",
                    None,
                    "This stage was saved elsewhere since it was loaded. Reload it.",
                    {"current_draft_version": draft.draft_version},
                )
            problems = self._draft_problems(view, stage_id, req)
            if problems:
                raise ApiError(422, problems)
            based_on = (
                draft.based_on_revision
                if view.has_changes(stage_id)
                else view.record(stage_id).latest_revision
            )
            view.set_draft(
                StageDraft(
                    contract_version=V2_CONTRACT_VERSION,
                    character_id=character_id,
                    stage_id=stage_id,
                    draft_version=draft.draft_version + 1,
                    based_on_revision=based_on,
                    content=req.content,
                    checklist=req.checklist,
                    updated_at=self.clock(),
                )
            )
            self._touch(view)
            self._history(character_id, "draft_saved", stage_id)
            return self._detail(view, stage_id)

    def decide(self, character_id: str, stage_id: str, raw: Any) -> StageDetail:
        req = parse(StageDecisionRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            self._require_available(stage_id)
            draft = view.draft(stage_id)
            if req.expected_draft_version != draft.draft_version:
                raise api_error(
                    409,
                    "STAGE_DRAFT_CONFLICT",
                    None,
                    "This stage was saved elsewhere since it was loaded. Reload it.",
                    {"current_draft_version": draft.draft_version},
                )
            handler = {
                "submit": self._submit,
                "approve": self._approve,
                "request_revision": self._request_revision,
                "withdraw": self._withdraw,
            }[req.action]
            handler(view, stage_id, req)
            self._touch(view)
            return self._detail(view, stage_id)

    def revision(self, character_id: str, stage_id: str, number: int) -> StageRevision:
        with self.store.lock(character_id):
            view = self._view(character_id)
            revision = view.revision(stage_id, number)
            if revision is None:
                raise api_error(404, "REVISION_NOT_FOUND", None, "Revision not found.")
            return revision

    def history(self, character_id: str, limit: int, cursor: str | None) -> HistoryPage:
        with self.store.lock(character_id):
            self._view(character_id)
            events = list(reversed(self.store.read_history(character_id)))
        if cursor is not None:
            if not cursor.isdigit():
                raise api_error(422, "REQUEST_FIELD_INVALID", "cursor", "Unknown or expired cursor.")
            events = [e for e in events if e.seq < int(cursor)]
        page = events[:limit]
        return HistoryPage(
            contract_version=V2_CONTRACT_VERSION,
            events=page,
            next_cursor=str(page[-1].seq) if len(events) > limit else None,
        )

    def _require_available(self, stage_id: str) -> None:
        state, reason = config.availability(stage_id, self.registry)
        if state != "available":
            raise api_error(
                422,
                "STAGE_NOT_AVAILABLE",
                "stage_id",
                f"Stage {stage_id.upper()} is {state} and cannot be edited.",
                {"availability": state, "reason": reason},
            )

    def _transition_invalid(self, message: str, **details: Any) -> ApiError:
        return api_error(409, "STAGE_TRANSITION_INVALID", "action", message, details)

    def _submit(self, view: CharacterView, stage_id: str, req: StageDecisionRequest) -> None:
        record = view.record(stage_id)
        draft = view.draft(stage_id)
        if record.pending_revision is not None:
            raise self._transition_invalid(
                "A revision is already waiting for a decision.", pending_revision=record.pending_revision
            )
        if draft.draft_version == 0:
            raise self._transition_invalid("Save a draft before submitting.")
        if not view.has_changes(stage_id) and view.status(stage_id) == "approved":
            raise self._transition_invalid("Nothing changed since the approved revision.")
        number = (record.latest_revision or 0) + 1
        revision = StageRevision(
            contract_version=V2_CONTRACT_VERSION,
            character_id=view.cid,
            stage_id=stage_id,
            revision=number,
            content=draft.content,
            checklist=draft.checklist,
            source_revisions=view.source_revisions(stage_id),
            submitted_at=self.clock(),
            decision="pending",
            decided_at=None,
            note=req.note,
            frozen_assets=[],
            batch_manifest_id=None,
        )
        try:
            self.store.create_revision(revision)
        except RevisionExists as exc:
            raise self._transition_invalid("This revision already exists.", revision=number) from exc
        view.set_record(
            stage_id,
            record.model_copy(
                update={
                    "latest_revision": number,
                    "pending_revision": number,
                    "submitted_draft_version": draft.draft_version,
                }
            ),
        )
        self._history(view.cid, "submitted", stage_id, revision=number, note=req.note)

    def _pending_for(self, view: CharacterView, stage_id: str, req: StageDecisionRequest) -> StageRevision:
        record = view.record(stage_id)
        if record.pending_revision is None or req.revision != record.pending_revision:
            raise self._transition_invalid(
                "This revision is not waiting for a decision.",
                revision=req.revision,
                pending_revision=record.pending_revision,
            )
        revision = view.pending(stage_id)
        assert revision is not None
        return revision

    def _decided(self, view: CharacterView, revision: StageRevision, **changes: Any) -> StageRevision:
        updated = revision.model_copy(update={"decided_at": self.clock(), **changes})
        self.store.update_revision(updated)
        view.forget_revision(revision.stage_id, revision.revision)
        return updated

    def _approve(self, view: CharacterView, stage_id: str, req: StageDecisionRequest) -> None:
        revision = self._pending_for(view, stage_id, req)
        problems = view.approval_problems(
            stage_id, revision.content, revision.checklist, revision.source_revisions
        )
        images: list[tuple[str, ImageRef]] = []
        if not problems:
            images, problems = self._freeze_plan(view, stage_id, revision)
        if problems:
            raise ApiError(422, problems)
        frozen = self._freeze(view, stage_id, revision, images)
        manifest_id = None
        try:
            if stage_id == "s4":
                manifest_id = self._freeze_manifest(view, revision)
            self._decided(
                view,
                revision,
                decision="approved",
                note=req.note or revision.note,
                frozen_assets=frozen,
                batch_manifest_id=manifest_id,
            )
        except Exception:
            for asset in frozen:
                self.store.remove_asset(view.cid, asset.asset_id)
            raise
        record = view.record(stage_id)
        view.set_record(
            stage_id,
            record.model_copy(
                update={
                    "pending_revision": None,
                    "approved_revision": revision.revision,
                    "last_decision": "approved",
                }
            ),
        )
        affected = [
            d
            for d in config.downstream(stage_id)
            if (approved := view.approved(d)) is not None
            and approved.source_revisions.get(stage_id) not in (None, revision.revision)
        ]
        self._history(
            view.cid,
            "approved",
            stage_id,
            revision=revision.revision,
            manifest_id=manifest_id,
            affected_stages=affected,
            note=req.note,
        )

    def _request_revision(self, view: CharacterView, stage_id: str, req: StageDecisionRequest) -> None:
        record = view.record(stage_id)
        if record.pending_revision is not None:
            revision = self._pending_for(view, stage_id, req)
            self._decided(view, revision, decision="revision_requested", note=req.note or revision.note)
            view.set_record(
                stage_id,
                record.model_copy(update={"pending_revision": None, "last_decision": "revision_requested"}),
            )
            number = revision.revision
        elif record.approved_revision is not None and req.revision in (None, record.approved_revision):
            view.set_record(stage_id, record.model_copy(update={"last_decision": "revision_requested"}))
            number = record.approved_revision
        else:
            raise self._transition_invalid("There is no pending or approved revision to send back.")
        self._history(view.cid, "revision_requested", stage_id, revision=number, note=req.note)

    def _withdraw(self, view: CharacterView, stage_id: str, req: StageDecisionRequest) -> None:
        revision = self._pending_for(view, stage_id, req)
        self._decided(view, revision, decision="withdrawn", note=req.note or revision.note)
        record = view.record(stage_id)
        view.set_record(
            stage_id,
            record.model_copy(
                update={
                    "pending_revision": None,
                    "last_decision": "withdrawn",
                    "submitted_draft_version": None,
                }
            ),
        )
        self._history(view.cid, "withdrawn", stage_id, revision=revision.revision, note=req.note)

    # --- freezing (§13.5.5) -------------------------------------------------------------------------------------

    def _freeze_plan(
        self, view: CharacterView, stage_id: str, revision: StageRevision
    ) -> tuple[list[tuple[str, ImageRef]], list[ErrorItem]]:
        content = revision.content
        targets: list[tuple[str, str, ImageRef]] = []
        if stage_id == "s3":
            index, candidate = next(
                (i, c)
                for i, c in enumerate(content.candidates)
                if c.candidate_id == content.selected_candidate_id
            )
            field = f"content.candidates[{index}]"
            targets.append((CONCEPT_PURPOSE, field, view.candidate_image(candidate, field)))
        elif stage_id == "s5":
            for index, item in enumerate(content.items):
                if item.selected:
                    field = f"content.items[{index}]"
                    targets.append((item.purpose, field, view.item_image(item, field)))
        problems, images = [], []
        for purpose, field, image in targets:
            if image.problem:
                problems.append(image.problem)
                continue
            data = image.path.read_bytes() if image.path and image.path.is_file() else None
            if data is None or hashlib.sha256(data).hexdigest() != image.sha256:
                problems.append(
                    error(
                        "LINKED_ARTIFACT_INVALID",
                        field,
                        "The stored image is missing or does not match its recorded SHA-256.",
                        {"reason": "missing" if data is None else "sha256_mismatch"},
                    )
                )
                continue
            images.append((purpose, image))
        return images, problems

    def _freeze(
        self, view: CharacterView, stage_id: str, revision: StageRevision, images: list[tuple[str, ImageRef]]
    ) -> list[ArtifactReference]:
        frozen: list[ArtifactReference] = []
        try:
            for purpose, image in images:
                data = image.path.read_bytes()
                if image.mime_type != "image/png":  # a sketch reference in JPEG/WebP is stored as PNG
                    with Image.open(io.BytesIO(data)) as source:
                        buffer = io.BytesIO()
                        source.convert("RGBA" if source.mode in ("RGBA", "LA", "P") else "RGB").save(
                            buffer, format="PNG"
                        )
                        data = buffer.getvalue()
                with Image.open(io.BytesIO(data)) as decoded:
                    width, height = decoded.size
                asset_id = f"ast_{secrets.token_hex(6)}"
                asset = ArtifactReference(
                    asset_id=asset_id,
                    purpose=purpose,
                    mime_type="image/png",
                    width=width,
                    height=height,
                    size_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    content_url=f"/api/v1/characters/{view.cid}/assets/{asset_id}/content",
                    source=image.source,
                    reference_id=image.reference_id,
                    frozen_in=RevisionPointer(stage_id=stage_id, revision=revision.revision),
                    created_at=self.clock(),
                )
                self.store.write_asset(view.cid, asset, data)
                frozen.append(asset)
        except Exception:
            for asset in frozen:
                self.store.remove_asset(view.cid, asset.asset_id)
            raise
        return frozen

    def _freeze_manifest(self, view: CharacterView, revision: StageRevision) -> str:
        """Approving S4 freezes the production batch manifest (``ready``), bound to the S2/S3/S4 revisions."""
        content = revision.content
        manifest = self.batches.build(
            character_id=view.cid,
            kind="production",
            model_id=content.production_profile.target_model_id,
            tasks=self.batches.production_tasks(content),
            approved_spec_revision=revision.source_revisions["s2"],
            prompt_set_revision=revision.revision,
            concept_revision=revision.source_revisions.get("s3"),
            reference_ids=list(content.reference_asset_ids),
        )
        view.put_manifest(manifest)
        self._history(
            view.cid, "batch_created", "s4", revision=revision.revision, manifest_id=manifest.manifest_id
        )
        return manifest.manifest_id

    def _approved_outputs(self, view: CharacterView) -> list[ArtifactReference]:
        outputs = []
        for stage_id in STAGE_IDS:
            approved = view.approved(stage_id)
            if approved is not None:
                outputs += approved.frozen_assets
        return outputs

    # --- draft validation (route 6) -----------------------------------------------------------------------------

    def _draft_problems(self, view: CharacterView, stage_id: str, req: SaveDraftRequest) -> list[ErrorItem]:
        content, problems = req.content, []
        if content.stage_id != stage_id:
            return [
                _field_error("content.stage_id", f"The content is for {content.stage_id}, not {stage_id}.")
            ]
        allowed = config.checklist_ids(stage_id)
        seen: set[str] = set()
        for index, item in enumerate(req.checklist.items):
            if item.item_id not in allowed:
                problems.append(_field_error(f"checklist.items[{index}].item_id", "Unknown checklist item."))
            elif item.item_id in seen:
                problems.append(
                    _field_error(f"checklist.items[{index}].item_id", "Checklist item listed twice.")
                )
            seen.add(item.item_id)
        references = view.references()

        def reference(ref_id: str, field: str) -> None:
            if ref_id not in references:
                problems.append(error("REFERENCE_NOT_FOUND", field, "This reference does not exist."))

        if stage_id == "s1":
            for i, note in enumerate(content.references):
                reference(note.reference_id, f"content.references[{i}].reference_id")
        elif stage_id == "s2":
            for i, attribute in enumerate(content.attributes):
                for j, ref_id in enumerate(attribute.reference_ids):
                    reference(ref_id, f"content.attributes[{i}].reference_ids[{j}]")
            for i, answer in enumerate(content.answers):
                if answer.question_id not in config.QUESTION_IDS:
                    problems.append(
                        _field_error(f"content.answers[{i}].question_id", "Unknown guided question.")
                    )
                if (answer.answer is not None) != (answer.status == "answered"):
                    problems.append(
                        _field_error(
                            f"content.answers[{i}].answer",
                            "An answer is required exactly when the status is 'answered'.",
                        )
                    )
        elif stage_id == "s3":
            problems += self._s3_problems(view, content, reference)
        elif stage_id == "s4":
            problems += self._s4_problems(view, content, reference)
        elif stage_id == "s5":
            problems += self._s5_problems(view, content)
        return problems

    def _job_ref_problems(self, ref: JobReference, field: str) -> list[ErrorItem]:
        record = self.jobs.get_record(ref.job_id)
        if record is None:
            return [error("LINKED_JOB_NOT_FOUND", field, "This job does not exist.", {"job_id": ref.job_id})]
        if ref.artifact_id is not None and linked_artifact(record, ref.artifact_id) is None:
            return [
                error(
                    "LINKED_JOB_NOT_FOUND",
                    field,
                    "This job has no such artifact.",
                    {"job_id": ref.job_id, "artifact_id": ref.artifact_id},
                )
            ]
        return []

    def _task_ref_problems(self, view: CharacterView, manifest_id, task_id, field: str) -> list[ErrorItem]:
        manifest = view.manifests().get(manifest_id)
        if manifest is None:
            return [error("BATCH_NOT_FOUND", f"{field}.manifest_id", "This batch does not exist.")]
        if not any(t.task_id == task_id for t in manifest.tasks):
            return [_field_error(f"{field}.task_id", "The batch has no task with this ID.")]
        return []

    def _s3_problems(self, view: CharacterView, content, reference) -> list[ErrorItem]:
        problems: list[ErrorItem] = []
        needs = {
            "batch_task": ("manifest_id", "task_id"),
            "job_artifact": ("job",),
            "reference": ("reference_id",),
        }
        attributes = set()
        for revision in (view.draft("s2"), view.approved("s2")):
            if revision is not None:
                attributes |= {a.attribute_id for a in revision.content.attributes}
        ids = [c.candidate_id for c in content.candidates]
        for i, candidate in enumerate(content.candidates):
            field = f"content.candidates[{i}]"
            if ids.count(candidate.candidate_id) > 1:
                problems.append(_field_error(f"{field}.candidate_id", "Candidate IDs must be unique."))
            for name in ("manifest_id", "task_id", "job", "reference_id"):
                present = getattr(candidate, name) is not None
                if present != (name in needs[candidate.source]):
                    problems.append(
                        _field_error(
                            f"{field}.{name}",
                            f"A '{candidate.source}' candidate {'needs' if not present else 'must not have'} '{name}'.",
                        )
                    )
            if candidate.source == "batch_task" and candidate.manifest_id and candidate.task_id:
                problems += self._task_ref_problems(view, candidate.manifest_id, candidate.task_id, field)
            if candidate.source == "job_artifact" and candidate.job is not None:
                problems += self._job_ref_problems(candidate.job, f"{field}.job")
            if candidate.source == "reference" and candidate.reference_id:
                reference(candidate.reference_id, f"{field}.reference_id")
            for name in ("matches", "mismatches"):
                for j, attribute_id in enumerate(getattr(candidate, name)):
                    if attribute_id not in attributes:
                        problems.append(_field_error(f"{field}.{name}[{j}]", "Unknown S2 attribute_id."))
        if content.selected_candidate_id is not None and content.selected_candidate_id not in ids:
            problems.append(_field_error("content.selected_candidate_id", "No candidate has this ID."))
        profile = content.preview_profile
        if profile is not None:
            options = {**profile.options, "width": profile.width, "height": profile.height}
            problems += check_profile_options(
                profile.model_id, options, self.registry, "content.preview_profile"
            )
        return problems

    def _s4_problems(self, view: CharacterView, content, reference) -> list[ErrorItem]:
        problems: list[ErrorItem] = []
        for i, item_id in enumerate(content.reference_asset_ids):
            field = f"content.reference_asset_ids[{i}]"
            if item_id.startswith("ref_"):
                reference(item_id, field)
            elif self.store.read_asset(view.cid, item_id) is None:
                problems.append(error("ASSET_NOT_FOUND", field, "This frozen asset does not exist."))
        profile = content.production_profile
        if profile is not None:
            found = check_profile_options(
                profile.target_model_id, profile.options, self.registry, "content.production_profile"
            )
            for item in found:
                if item.code == "MODEL_NOT_FOUND":
                    item = item.model_copy(update={"field": "content.production_profile.target_model_id"})
                problems.append(item)
            if not any(p.code == "MODEL_NOT_FOUND" for p in found):
                for i, task in enumerate(content.tasks):
                    problems += [
                        p
                        for p in check_profile_options(
                            profile.target_model_id,
                            task_options(task, profile.options),
                            self.registry,
                            f"content.tasks[{i}]",
                        )
                        if p.code != "MODEL_NOT_FOUND"
                    ]
        return problems

    def _s5_problems(self, view: CharacterView, content) -> list[ErrorItem]:
        problems: list[ErrorItem] = []
        ids = [item.item_id for item in content.items]
        for i, item in enumerate(content.items):
            field = f"content.items[{i}]"
            if ids.count(item.item_id) > 1:
                problems.append(_field_error(f"{field}.item_id", "Item IDs must be unique."))
            from_task = item.manifest_id is not None and item.task_id is not None
            if from_task == (item.job is not None) or (
                item.job is not None and (item.manifest_id is not None or item.task_id is not None)
            ):
                problems.append(_field_error(field, "An item needs either manifest_id + task_id, or job."))
                continue
            if from_task:
                problems += self._task_ref_problems(view, item.manifest_id, item.task_id, field)
            else:
                problems += self._job_ref_problems(item.job, f"{field}.job")
        return problems

    # --- stage detail -------------------------------------------------------------------------------------------

    def _resolved(self, ref: JobReference) -> ResolvedJob:
        record = self.jobs.get_record(ref.job_id)
        artifact = linked_artifact(record, ref.artifact_id) if record else None
        return ResolvedJob(
            job_id=ref.job_id,
            artifact_id=ref.artifact_id,
            missing=record is None or artifact is None,
            status=record.status if record else None,
            model_id=record.request.model_id if record else None,
            prompt=record.request.prompt if record else None,
            options=dict(record.request.options) if record else None,
            task_id=artifact.task_id if artifact else None,
            artifact=artifact_view(record.job_id, artifact) if artifact else None,
        )

    def _manifest_preview(self, view: CharacterView) -> StoredManifest | None:
        source = view.pending("s4") or view.draft("s4")
        content = source.content
        spec = view.record("s2").approved_revision
        if content.production_profile is None or spec is None or not content.tasks:
            return None
        if self.registry.get(content.production_profile.target_model_id) is None:
            return None
        ids = [t.task_id for t in content.tasks]
        if len(set(ids)) != len(ids):
            return None
        return self.batches.build(
            character_id=view.cid,
            kind="production",
            model_id=content.production_profile.target_model_id,
            tasks=self.batches.production_tasks(content),
            approved_spec_revision=spec,
            prompt_set_revision=source.revision if isinstance(source, StageRevision) else None,
            concept_revision=view.record("s3").approved_revision,
            reference_ids=list(content.reference_asset_ids),
            manifest_id=PREVIEW_MANIFEST_ID,
        )

    def _plans(self, manifest: StoredManifest | None) -> list:
        if manifest is None:
            return []
        plans = []
        for group in manifest.groups:
            checked = self.jobs.validate_batch(
                group.model_id,
                "character",
                self.batches.job_tasks(manifest, group.task_ids),
                self.default_compute(),
            )
            if checked.plan is not None:
                plans.append(checked.plan)
        return plans

    def _current_production(self, view: CharacterView) -> StoredManifest | None:
        approved = view.approved("s4")
        if approved is None or approved.batch_manifest_id is None:
            return None
        return view.manifests().get(approved.batch_manifest_id)

    def _detail(self, view: CharacterView, stage_id: str) -> StageDetail:
        record = view.record(stage_id)
        revisions = []
        for number in range(record.latest_revision or 0, 0, -1):
            item = view.revision(stage_id, number)
            if item is not None:
                revisions.append(
                    RevisionSummary(
                        revision=number,
                        decision=item.decision,
                        submitted_at=item.submitted_at,
                        decided_at=item.decided_at,
                    )
                )
        inputs = []
        for upstream, kind in config.dependencies(stage_id):
            approved = view.approved(upstream)
            inputs.append(
                StageInput(
                    stage_id=upstream,
                    kind=kind,
                    revision=approved.revision if approved else None,
                    content=approved.content if approved else None,
                    frozen_assets=approved.frozen_assets if approved else [],
                )
            )
        refs: dict[tuple[str, str | None], JobReference] = {}
        for source in (view.draft(stage_id), view.pending(stage_id), view.approved(stage_id)):
            if source is None:
                continue
            for item in getattr(source.content, "candidates", []) + getattr(source.content, "items", []):
                if item.job is not None:
                    refs[(item.job.job_id, item.job.artifact_id)] = item.job
        manifests = list(view.manifests().values())
        kind = "preview" if stage_id == "s3" else "production"
        batches = [m.public() for m in manifests if stage_id in ("s3", "s4", "s5") and m.kind == kind]
        batches.sort(key=lambda m: m.created_at, reverse=True)
        preview = self._manifest_preview(view) if stage_id == "s4" else None
        if stage_id == "s4":
            plans = self._plans(preview)
        elif stage_id == "s5":
            plans = self._plans(self._current_production(view))
        else:
            plans = []
        return StageDetail(
            contract_version=V2_CONTRACT_VERSION,
            character=view.summary(),
            character_version=view.character.version,
            config=view.config(stage_id),
            state=view.state(stage_id),
            draft=view.draft(stage_id),
            approved_revision=view.approved(stage_id),
            pending_revision=view.pending(stage_id),
            revisions=revisions,
            inputs=inputs,
            references=list(view.references().values()),
            resolved_jobs=[self._resolved(ref) for ref in refs.values()],
            batches=batches,
            manifest_preview=preview.public() if preview else None,
            resource_plans=plans,
        )

    # --- references (routes 10-12) ------------------------------------------------------------------------------

    def create_reference(self, character_id: str, raw: Any) -> ReferenceAsset:
        req = parse(CreateReferenceRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            known = self._known(str(req.client_request_id), "reference")
            if (
                known is not None
                and (existing := self.store.read_reference(character_id, known[1])) is not None
            ):
                return existing
            reference_id = f"ref_{secrets.token_hex(6)}"
            now = self.clock()
            values: dict[str, Any] = {
                "contract_version": "1.1",
                "reference_id": reference_id,
                "character_id": character_id,
                "kind": req.kind,
                "purpose": req.purpose,
                "title": req.title,
                "url": None,
                "source_note": req.source_note,
                "mime_type": None,
                "width": None,
                "height": None,
                "size_bytes": None,
                "sha256": None,
                "content_url": None,
                "created_at": now,
            }
            if req.kind == "url":
                if req.upload_id is not None:
                    raise api_error(
                        422, "REQUEST_FIELD_INVALID", "upload_id", "A URL reference has no upload."
                    )
                values["url"] = self._checked_url(req.url)
            else:
                if req.url is not None:
                    raise api_error(422, "REQUEST_FIELD_INVALID", "url", "An image reference has no URL.")
                values.update(self._promote(character_id, reference_id, req.upload_id))
            reference = ReferenceAsset.model_validate(values)
            self.store.write_reference(reference)
            self._remember(str(req.client_request_id), character_id, "reference", reference_id)
            self._touch(view)
            self._history(character_id, "reference_added", note=reference_id)
            return reference

    @staticmethod
    def _checked_url(url: str | None) -> str:
        """Stored as text and never fetched (§13.4.5)."""
        if url is None:
            raise api_error(422, "REQUEST_FIELD_INVALID", "url", "A URL reference needs 'url'.")
        url = url.strip()
        parts = urlsplit(url) if len(url) <= 2000 else None
        if (
            parts is None
            or parts.scheme not in ("http", "https")
            or not parts.netloc
            or any(c.isspace() for c in url)
        ):
            raise api_error(
                422, "REFERENCE_URL_INVALID", "url", "Use an http or https URL of at most 2000 characters."
            )
        return url

    def _promote(self, character_id: str, reference_id: str, upload_id: str | None) -> dict[str, Any]:
        """Copy a live staged upload into the character (uploads expire after 24 h). The bytes are re-sniffed."""
        from ..storage.paths import is_valid_id

        if upload_id is None:
            raise api_error(
                422, "REQUEST_FIELD_INVALID", "upload_id", "An image reference needs 'upload_id'."
            )
        staged = self.jobs.uploads.get(upload_id) if is_valid_id("upload_id", upload_id) else None
        if staged is None:
            raise api_error(422, "UPLOAD_NOT_FOUND", "upload_id", "Upload not found or expired.")
        data = staged.path.read_bytes()
        mime = sniff_mime(data[:16])
        corrupt = api_error(
            422, "UPLOAD_CORRUPT", "upload_id", "The stored upload changed on disk and cannot be used."
        )
        if mime != staged.record.mime_type or hashlib.sha256(data).hexdigest() != staged.record.sha256:
            raise corrupt
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != PILLOW_FORMATS[mime]:
                    raise ValueError("format mismatch")
                image.verify()
        except Exception as exc:
            raise corrupt from exc
        target = self.store.path(character_id, "references", f"{reference_id}.{MIME_EXTENSIONS[mime]}")
        atomic_write_bytes(target, data)
        return {
            "mime_type": mime,
            "width": staged.record.width,
            "height": staged.record.height,
            "size_bytes": len(data),
            "sha256": staged.record.sha256,
            "content_url": f"/api/v1/characters/{character_id}/references/{reference_id}/content",
        }

    def reference_content(self, character_id: str, reference_id: str) -> tuple[str, str, str]:
        with self.store.lock(character_id):
            self._view(character_id)
            reference = self.store.read_reference(character_id, reference_id)
            if reference is None or reference.kind != "image":
                raise api_error(404, "REFERENCE_NOT_FOUND", None, "Reference not found.")
            extension = MIME_EXTENSIONS[reference.mime_type]
            relative = self.store.relative(character_id, "references", f"{reference_id}.{extension}")
            return relative, reference.mime_type, f"{character_id}_{reference_id}.{extension}"

    def delete_reference(self, character_id: str, reference_id: str) -> None:
        with self.store.lock(character_id):
            view = self._view(character_id)
            reference = self.store.read_reference(character_id, reference_id)
            if reference is None:
                raise api_error(404, "REFERENCE_NOT_FOUND", None, "Reference not found.")
            used_by = self._reference_users(view, reference_id)
            if used_by:
                raise api_error(
                    409,
                    "REFERENCE_IN_USE",
                    None,
                    "A draft, revision or batch uses this reference.",
                    {"used_by": used_by},
                )
            extension = MIME_EXTENSIONS.get(reference.mime_type) if reference.kind == "image" else None
            self.store.delete_reference(character_id, reference, extension)
            self._touch(view)
            self._history(character_id, "reference_removed", note=reference_id)

    def _reference_users(self, view: CharacterView, reference_id: str) -> list[str]:
        used = []
        for stage_id in STAGE_IDS:
            sources = [("draft", view.draft(stage_id))]
            for number in range(1, (view.record(stage_id).latest_revision or 0) + 1):
                sources.append((f"r{number}", view.revision(stage_id, number)))
            for label, source in sources:
                if source is not None and reference_id in source.model_dump_json():
                    used.append(f"{stage_id}:{label}")
        for manifest in view.manifests().values():
            if any(r.asset_id == reference_id for r in manifest.references):
                used.append(manifest.manifest_id)
        return used

    # --- outputs and assets (routes 13-14) ----------------------------------------------------------------------

    def outputs(self, character_id: str) -> OutputList:
        with self.store.lock(character_id):
            return OutputList(
                contract_version=V2_CONTRACT_VERSION, outputs=self._approved_outputs(self._view(character_id))
            )

    def asset_content(self, character_id: str, asset_id: str) -> tuple[str, str]:
        with self.store.lock(character_id):
            self._view(character_id)
            if self.store.read_asset(character_id, asset_id) is None:
                raise api_error(404, "ASSET_NOT_FOUND", None, "Asset not found.")
            return self.store.relative(
                character_id, "assets", f"{asset_id}.png"
            ), f"{character_id}_{asset_id}.png"

    # --- batches (routes 15-18) ---------------------------------------------------------------------------------

    def create_preview_batch(self, character_id: str, raw: Any) -> StoredManifest:
        req = parse(CreatePreviewBatchRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            known = self._known(str(req.client_request_id), "batch")
            if known is not None and (existing := view.manifests().get(known[1])) is not None:
                return existing
            spec = view.record("s2").approved_revision
            if spec is None:
                raise api_error(
                    422,
                    "STAGE_BLOCKED",
                    "stage_id",
                    "Approve S2 before generating previews.",
                    {"stage_id": "s2"},
                )
            content = view.draft("s3").content
            profile = content.preview_profile
            if profile is None or not (content.preview_prompt or "").strip():
                raise api_error(
                    422,
                    "STAGE_CONTENT_INCOMPLETE",
                    "content.preview_profile" if profile is None else "content.preview_prompt",
                    "Save a preview profile and a preview prompt in the S3 draft first.",
                    {"rule": "preview_profile_required" if profile is None else "preview_prompt_required"},
                )
            if profile.compute_target == "local":
                raise api_error(
                    422,
                    "STAGE_NOT_AVAILABLE",
                    "content.preview_profile.compute_target",
                    "Local previews are planned, not available yet (OD-09).",
                    {"availability": "planned", "reason": "local_compute_planned"},
                )
            manifest = self.batches.build(
                character_id=character_id,
                kind="preview",
                model_id=profile.model_id,
                tasks=self.batches.preview_tasks(content),
                approved_spec_revision=spec,
                prompt_set_revision=None,
                concept_revision=None,
                reference_ids=[],
            )
            compute = compute_dict(req.compute)
            groups = {g.group_id: g.task_ids for g in manifest.groups}
            errors = self.batches.validate(manifest, groups, compute)
            if errors:
                raise ApiError(422, errors)
            self.store.write_manifest(manifest)
            self._history(character_id, "batch_created", "s3", manifest_id=manifest.manifest_id)
            self._remember(str(req.client_request_id), character_id, "batch", manifest.manifest_id)
            manifest = self.batches.launch(manifest, groups, compute, str(req.client_request_id))
            self._history(character_id, "batch_submitted", "s3", manifest_id=manifest.manifest_id)
            self._touch(view)
            return manifest

    def batch(self, character_id: str, manifest_id: str) -> StoredManifest:
        with self.store.lock(character_id):
            view = self._view(character_id)
            manifest = view.manifests().get(manifest_id)
            if manifest is None:
                raise api_error(404, "BATCH_NOT_FOUND", None, "Batch not found.")
            return manifest

    def submit_batch(self, character_id: str, manifest_id: str, raw: Any) -> StoredManifest:
        req = parse(SubmitBatchRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            manifest = view.manifests().get(manifest_id)
            if manifest is None:
                raise api_error(404, "BATCH_NOT_FOUND", None, "Batch not found.")
            if str(req.client_request_id) in manifest.request_ids:
                return manifest
            if manifest.kind != "production":
                raise api_error(
                    409, "BATCH_ALREADY_SUBMITTED", None, "A preview batch is submitted when it is created."
                )
            if manifest.attempts:
                raise api_error(409, "BATCH_ALREADY_SUBMITTED", None, "This batch was already submitted.")
            self._require_current(view, manifest)
            groups = {g.group_id: g.task_ids for g in manifest.groups}
            manifest = self.batches.launch(
                manifest, groups, compute_dict(req.compute), str(req.client_request_id)
            )
            view.manifests()[manifest_id] = manifest
            self._history(character_id, "batch_submitted", "s5", manifest_id=manifest_id)
            self._touch(view)
            return manifest

    def _require_current(self, view: CharacterView, manifest: StoredManifest) -> None:
        """Production may start only from the manifest of the current, non-stale S2 and S4 approvals (§13.6.3)."""
        reasons = []
        s2, s4 = view.record("s2"), view.record("s4")
        if s2.approved_revision != manifest.approved_spec_revision:
            reasons.append("s2_reapproved")
        elif view.stale_reasons("s2"):
            reasons.append("s2_stale")
        if s4.approved_revision != manifest.prompt_set_revision:
            reasons.append("s4_reapproved")
        elif view.stale_reasons("s4"):
            reasons.append("s4_stale")
        if s4.pending_revision is not None:
            reasons.append("s4_pending")
        if reasons:
            raise api_error(
                409,
                "BATCH_MANIFEST_STALE",
                None,
                "This manifest no longer matches the current approved S2/S4 revisions.",
                {
                    "reasons": reasons,
                    "approved_spec_revision": manifest.approved_spec_revision,
                    "prompt_set_revision": manifest.prompt_set_revision,
                    "current_spec_revision": s2.approved_revision,
                    "current_prompt_set_revision": s4.approved_revision,
                },
            )

    def retry_batch(self, character_id: str, manifest_id: str, raw: Any) -> StoredManifest:
        req = parse(SubmitBatchRequest, raw)
        with self.store.lock(character_id):
            view = self._view(character_id)
            manifest = view.manifests().get(manifest_id)
            if manifest is None:
                raise api_error(404, "BATCH_NOT_FOUND", None, "Batch not found.")
            if str(req.client_request_id) in manifest.request_ids:
                return manifest
            if any(r.status == "pending" and r.attempt is not None for r in manifest.results):
                raise api_error(
                    409, "BATCH_ATTEMPT_RUNNING", None, "An attempt of this batch is still running."
                )
            if not manifest.retryable_task_ids:
                raise api_error(
                    409, "BATCH_NOTHING_TO_RETRY", None, "No task of this batch failed or was not run."
                )
            retry = set(manifest.retryable_task_ids)
            groups = {
                g.group_id: [t for t in g.task_ids if t in retry]
                for g in manifest.groups
                if any(t in retry for t in g.task_ids)
            }
            manifest = self.batches.launch(
                manifest, groups, compute_dict(req.compute), str(req.client_request_id)
            )
            view.manifests()[manifest_id] = manifest
            self._history(
                character_id,
                "batch_retried",
                "s3" if manifest.kind == "preview" else "s5",
                manifest_id=manifest_id,
                note=", ".join(sorted(retry)),
            )
            self._touch(view)
            return manifest
