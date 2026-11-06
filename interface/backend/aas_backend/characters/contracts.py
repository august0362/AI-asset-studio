"""Character Production contracts v1.1 (docs/CONTRACTS.md §13.4, §13.6.1).

Every model extends the v1 ``ContractModel`` (``extra = "forbid"``): an unknown field is ``REQUEST_FIELD_INVALID``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import UUID4, Field, StrictBool, StrictFloat, StrictInt, StrictStr, StringConstraints

from models.contracts import ContractModel, ErrorItem, JobStatus, UtcDatetime

from ..schemas import ArtifactView, ResourcePlan  # re-exported: characters/ never imports kaggle_connector

V2_CONTRACT_VERSION = "1.1"
V2Version = Literal["1.1"]

# --- identifiers (§13.2) ----------------------------------------------------------------------------------------

CHARACTER_ID_PATTERN = r"^chr_[0-9a-f]{12}$"
STAGE_ID_PATTERN = r"^s[1-7]$"
REFERENCE_ID_PATTERN = r"^ref_[0-9a-f]{12}$"
ASSET_ID_PATTERN = r"^ast_[0-9a-f]{12}$"
MANIFEST_ID_PATTERN = r"^bat_[0-9a-f]{12}$"
TASK_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{1,39}$"
GROUP_ID_PATTERN = r"^g[0-9]{2}$"
CANDIDATE_ID_PATTERN = r"^cand_[0-9]{2}$"
ITEM_ID_PATTERN = r"^item_[0-9]{3}$"
SLUG_ID_PATTERN = r"^[a-z0-9_]{2,40}$"  # attribute_id and checklist item_id
QUESTION_ID_PATTERN = r"^q_[a-z0-9_]{2,40}$"
JOB_REF_PATTERN = r"^job_\d{8}T\d{6}Z_[0-9a-f]{6}$"
ARTIFACT_REF_PATTERN = r"^art_\d{2}$"

STAGE_IDS = ("s1", "s2", "s3", "s4", "s5", "s6", "s7")

# --- shared aliases (§13.4) -------------------------------------------------------------------------------------

StageId = Literal["s1", "s2", "s3", "s4", "s5", "s6", "s7"]
EditorialStatus = Literal["not_started", "draft", "in_review", "approved", "needs_revision", "blocked"]
FeatureAvailability = Literal["available", "planned", "unavailable"]
AssetPurpose = Literal[
    "full_body", "portrait", "key_visual", "front", "side", "back", "three_quarter", "detail", "chibi"
]
SpecGroup = Literal[
    "identity", "face", "hair", "eyes", "body", "outfit", "accessories", "color", "style", "pose", "other"
]
RevisionDecision = Literal["pending", "approved", "revision_requested", "withdrawn"]
LastDecision = Literal["approved", "revision_requested", "withdrawn"]
TaskStatus = Literal["pending", "succeeded", "failed", "not_run"]
BatchStatus = Literal["ready", "submitted", "completed", "partially_completed", "failed"]
OptionValue = StrictInt | StrictFloat | StrictStr | StrictBool | None
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=8000)]
HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)
    ]


JobId = Annotated[str, StringConstraints(pattern=JOB_REF_PATTERN)]
ArtifactId = Annotated[str, StringConstraints(pattern=ARTIFACT_REF_PATTERN)]
ReferenceId = Annotated[str, StringConstraints(pattern=REFERENCE_ID_PATTERN)]
AssetOrReferenceId = Annotated[str, StringConstraints(pattern=r"^(ast|ref)_[0-9a-f]{12}$")]
ManifestId = Annotated[str, StringConstraints(pattern=MANIFEST_ID_PATTERN)]
TaskId = Annotated[str, StringConstraints(pattern=TASK_ID_PATTERN)]
SlugId = Annotated[str, StringConstraints(pattern=SLUG_ID_PATTERN)]

# --- 13.4.1 JobReference, ResolvedJob, ArtifactReference --------------------------------------------------------


class JobReference(ContractModel):
    job_id: JobId
    artifact_id: ArtifactId | None = None


class ResolvedJob(ContractModel):
    job_id: str
    artifact_id: str | None
    missing: bool
    status: JobStatus | None
    model_id: str | None
    prompt: str | None
    options: dict[str, OptionValue] | None
    task_id: str | None
    artifact: ArtifactView | None


class AssetSource(ContractModel):
    job_id: str
    artifact_id: str
    task_id: str | None
    model_id: str
    model_revision: str | None
    prompt: str | None
    negative_prompt: str | None
    seed: int | None
    width: int
    height: int
    options: dict[str, OptionValue]


class RevisionPointer(ContractModel):
    stage_id: StageId
    revision: int


class ArtifactReference(ContractModel):
    asset_id: str
    purpose: AssetPurpose
    mime_type: Literal["image/png"]
    width: int
    height: int
    size_bytes: int
    sha256: str
    content_url: str
    source: AssetSource | None
    reference_id: str | None
    frozen_in: RevisionPointer
    created_at: UtcDatetime


# --- 13.4.2 Character --------------------------------------------------------------------------------------------


class Character(ContractModel):
    contract_version: V2Version
    character_id: str
    name: Name
    summary: _text(2000) | None
    tags: list[Tag] = Field(max_length=20)
    cover_asset_id: str | None
    version: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class CharacterSummary(ContractModel):
    character_id: str
    name: str
    tags: list[str]
    cover_url: str | None
    current_stage: StageId
    approved_count: int
    stage_statuses: dict[StageId, EditorialStatus]
    updated_at: UtcDatetime


class CharacterList(ContractModel):
    contract_version: V2Version
    characters: list[CharacterSummary]
    next_cursor: str | None


# --- 13.4.3 StageConfig ------------------------------------------------------------------------------------------


class StageDependency(ContractModel):
    stage_id: StageId
    kind: Literal["hard", "soft"]


class ChecklistItemConfig(ContractModel):
    item_id: str
    label_key: str
    required: bool


class GuidedQuestion(ContractModel):
    question_id: str
    label_key: str
    core: bool


class StageConfig(ContractModel):
    stage_id: StageId
    order: int
    title_key: str
    objective_key: str
    availability: FeatureAvailability
    availability_reason: str | None
    dependencies: list[StageDependency]
    checklist: list[ChecklistItemConfig]
    required_purposes: list[AssetPurpose]
    guided_questions: list[GuidedQuestion]


# --- 13.4.4 ApprovalChecklist ------------------------------------------------------------------------------------


class ChecklistItemState(ContractModel):
    item_id: SlugId
    checked: StrictBool
    note: _text(500) | None = None


class ApprovalChecklist(ContractModel):
    items: list[ChecklistItemState] = Field(max_length=40)


# --- 13.4.5 ReferenceAsset ---------------------------------------------------------------------------------------


class ReferenceAsset(ContractModel):
    contract_version: V2Version
    reference_id: str
    character_id: str
    kind: Literal["image", "url"]
    purpose: Literal["moodboard", "sketch", "concept"]
    title: ShortText
    url: _text(2000) | None
    source_note: _text(500) | None
    mime_type: Literal["image/png", "image/jpeg", "image/webp"] | None
    width: int | None
    height: int | None
    size_bytes: int | None
    sha256: str | None
    content_url: str | None
    created_at: UtcDatetime


# --- 13.4.6 Stage content ----------------------------------------------------------------------------------------


class ReferenceNote(ContractModel):
    reference_id: ReferenceId
    aspects: list[SpecGroup] = Field(max_length=11)
    likes: _text(1000) | None = None
    do_not_copy: _text(1000) | None = None


class ConceptContent(ContractModel):
    stage_id: Literal["s1"]
    idea: _text(4000) | None = None
    directions: list[_text(1000, 1)] = Field(default_factory=list, max_length=3)
    notes: LongText | None = None
    palette: list[HexColor] = Field(default_factory=list, max_length=12)
    references: list[ReferenceNote] = Field(default_factory=list, max_length=60)


class SpecAttribute(ContractModel):
    attribute_id: SlugId
    group: SpecGroup
    label: ShortText
    value: _text(1000, 1)
    lock: Literal["locked", "preferred", "flexible"]
    reference_ids: list[ReferenceId] = Field(default_factory=list, max_length=60)


class GuidedAnswer(ContractModel):
    question_id: Annotated[str, StringConstraints(pattern=QUESTION_ID_PATTERN)]
    status: Literal["answered", "unknown", "skipped"]
    answer: _text(2000) | None = None


class CharacterSpecification(ContractModel):
    stage_id: Literal["s2"]
    summary: _text(2000) | None = None
    attributes: list[SpecAttribute] = Field(default_factory=list, max_length=200)
    answers: list[GuidedAnswer] = Field(default_factory=list, max_length=40)
    open_questions: list[ShortText] = Field(default_factory=list, max_length=100)
    rejection_criteria: list[ShortText] = Field(default_factory=list, max_length=100)


class PreviewProfile(ContractModel):
    model_id: StrictStr
    compute_target: Literal["kaggle", "local"]
    variations: int = Field(ge=1, le=8)
    width: StrictInt = Field(ge=1, le=8192)
    height: StrictInt = Field(ge=1, le=8192)
    options: dict[str, OptionValue] = Field(default_factory=dict)


class ConceptCandidate(ContractModel):
    candidate_id: Annotated[str, StringConstraints(pattern=CANDIDATE_ID_PATTERN)]
    source: Literal["batch_task", "job_artifact", "reference"]
    manifest_id: ManifestId | None = None
    task_id: TaskId | None = None
    job: JobReference | None = None
    reference_id: ReferenceId | None = None
    verdict: Literal["undecided", "selected", "rejected"]
    matches: list[SlugId] = Field(default_factory=list, max_length=200)
    mismatches: list[SlugId] = Field(default_factory=list, max_length=200)
    feedback: _text(2000) | None = None


class ConceptValidationContent(ContractModel):
    stage_id: Literal["s3"]
    preview_profile: PreviewProfile | None = None
    preview_prompt: _text(4000) | None = None
    candidates: list[ConceptCandidate] = Field(default_factory=list, max_length=24)
    selected_candidate_id: Annotated[str, StringConstraints(pattern=CANDIDATE_ID_PATTERN)] | None = None
    review_notes: LongText | None = None


class PromptEntry(ContractModel):
    purpose: AssetPurpose
    canonical_prompt: _text(4000)
    negative_prompt: _text(1000) | None = None
    notes: _text(2000) | None = None


class ProductionProfile(ContractModel):
    target_model_id: StrictStr
    compute_target: Literal["kaggle"]
    options: dict[str, OptionValue] = Field(default_factory=dict)


class ProductionTask(ContractModel):
    task_id: TaskId
    purpose: AssetPurpose
    prompt: _text(4000, 1)
    negative_prompt: _text(1000) | None = None
    seed: StrictInt | None = Field(default=None, ge=0, le=4294967295)
    width: StrictInt = Field(ge=1, le=8192)
    height: StrictInt = Field(ge=1, le=8192)
    options: dict[str, OptionValue] = Field(default_factory=dict)


class PromptSet(ContractModel):
    stage_id: Literal["s4"]
    entries: list[PromptEntry] = Field(default_factory=list, max_length=9)
    production_profile: ProductionProfile | None = None
    tasks: list[ProductionTask] = Field(default_factory=list, max_length=60)
    reference_asset_ids: list[AssetOrReferenceId] = Field(default_factory=list, max_length=60)


class ProductionItem(ContractModel):
    item_id: Annotated[str, StringConstraints(pattern=ITEM_ID_PATTERN)]
    purpose: AssetPurpose
    manifest_id: ManifestId | None = None
    task_id: TaskId | None = None
    job: JobReference | None = None
    selected: StrictBool
    note: _text(1000) | None = None


class ProductionReviewContent(ContractModel):
    stage_id: Literal["s5"]
    items: list[ProductionItem] = Field(default_factory=list, max_length=120)
    consistency_notes: LongText | None = None


class PlannedContent(ContractModel):
    stage_id: Literal["s6", "s7"]
    notes: LongText | None = None


StageContent = Annotated[
    ConceptContent
    | CharacterSpecification
    | ConceptValidationContent
    | PromptSet
    | ProductionReviewContent
    | PlannedContent,
    Field(discriminator="stage_id"),
]

# --- 13.4.7-13.4.9 drafts, revisions, state ---------------------------------------------------------------------


class StageDraft(ContractModel):
    contract_version: V2Version
    character_id: str
    stage_id: StageId
    draft_version: int
    based_on_revision: int | None
    content: StageContent
    checklist: ApprovalChecklist
    updated_at: UtcDatetime | None


class StageRevision(ContractModel):
    contract_version: V2Version
    character_id: str
    stage_id: StageId
    revision: int
    content: StageContent
    checklist: ApprovalChecklist
    source_revisions: dict[StageId, int]
    submitted_at: UtcDatetime
    decision: RevisionDecision
    decided_at: UtcDatetime | None
    note: _text(2000) | None
    frozen_assets: list[ArtifactReference]
    batch_manifest_id: str | None


class StaleReason(ContractModel):
    upstream_stage_id: StageId
    used_revision: int
    current_revision: int


class ApprovedSnapshot(ContractModel):
    revision: int
    approved_at: UtcDatetime
    source_revisions: dict[StageId, int]
    stale: bool
    stale_reasons: list[StaleReason]


class StageState(ContractModel):
    stage_id: StageId
    editorial_status: EditorialStatus
    availability: FeatureAvailability
    draft_version: int
    has_unsubmitted_changes: bool
    latest_revision: int | None
    pending_revision: int | None
    approved: ApprovedSnapshot | None
    last_decision: LastDecision | None
    blockers: list[ErrorItem]


# --- 13.4.10 batches ---------------------------------------------------------------------------------------------


class BatchTask(ProductionTask):
    group_id: Annotated[str, StringConstraints(pattern=GROUP_ID_PATTERN)]


class TaskGroup(ContractModel):
    group_id: str
    model_id: str
    model_revision: str | None
    task_ids: list[str]
    micro_batch_size: int
    estimated_runtime_seconds: int | None


class BatchAttempt(ContractModel):
    attempt: int
    group_id: str
    job_id: str
    task_ids: list[str]
    submitted_at: UtcDatetime


class TaskResult(ContractModel):
    task_id: str
    status: TaskStatus
    attempt: int | None
    job_id: str | None
    artifact_id: str | None
    sha256: str | None
    error: ErrorItem | None
    artifact_missing: bool


class ReferenceUse(ContractModel):
    asset_id: str
    applied: bool
    reason: str | None


class BatchManifest(ContractModel):
    contract_version: V2Version
    manifest_id: str
    character_id: str
    kind: Literal["preview", "production"]
    status: BatchStatus
    approved_spec_revision: int
    prompt_set_revision: int | None
    concept_revision: int | None
    target_model_id: str
    model_revision: str | None
    references: list[ReferenceUse]
    tasks: list[BatchTask]
    groups: list[TaskGroup]
    expected_model_loads: int
    attempts: list[BatchAttempt]
    results: list[TaskResult]
    retryable_task_ids: list[str]
    created_at: UtcDatetime
    updated_at: UtcDatetime


class StoredManifest(BatchManifest):
    """``batches/<manifest_id>.json``: the manifest plus the request IDs that created or submitted it (internal)."""

    request_ids: list[str] = Field(default_factory=list)

    def public(self) -> BatchManifest:
        return BatchManifest.model_validate(self.model_dump(exclude={"request_ids"}))


# --- 13.4.11 history ---------------------------------------------------------------------------------------------

HistoryAction = Literal[
    "character_created",
    "character_updated",
    "draft_saved",
    "submitted",
    "approved",
    "revision_requested",
    "withdrawn",
    "reference_added",
    "reference_removed",
    "batch_created",
    "batch_submitted",
    "batch_retried",
]


class StageHistory(ContractModel):
    seq: int
    at: UtcDatetime
    stage_id: StageId | None
    action: HistoryAction
    revision: int | None
    manifest_id: str | None
    affected_stages: list[StageId]
    note: _text(2000) | None


class HistoryPage(ContractModel):
    contract_version: V2Version
    events: list[StageHistory]
    next_cursor: str | None


# --- 13.4.12 envelopes -------------------------------------------------------------------------------------------


class WorkflowStage(ContractModel):
    config: StageConfig
    state: StageState


class CharacterWorkflow(ContractModel):
    contract_version: V2Version
    character: Character
    stages: list[WorkflowStage]
    approved_outputs: list[ArtifactReference]


class RevisionSummary(ContractModel):
    revision: int
    decision: RevisionDecision
    submitted_at: UtcDatetime
    decided_at: UtcDatetime | None


class StageInput(ContractModel):
    stage_id: StageId
    kind: Literal["hard", "soft"]
    revision: int | None
    content: StageContent | None
    frozen_assets: list[ArtifactReference]


class StageDetail(ContractModel):
    contract_version: V2Version
    character: CharacterSummary
    character_version: int
    config: StageConfig
    state: StageState
    draft: StageDraft
    approved_revision: StageRevision | None
    pending_revision: StageRevision | None
    revisions: list[RevisionSummary]
    inputs: list[StageInput]
    references: list[ReferenceAsset]
    resolved_jobs: list[ResolvedJob]
    batches: list[BatchManifest]
    manifest_preview: BatchManifest | None
    resource_plans: list[ResourcePlan]


class OutputList(ContractModel):
    contract_version: V2Version
    outputs: list[ArtifactReference]


# --- 13.6.1 requests ---------------------------------------------------------------------------------------------


class CreateCharacterRequest(ContractModel):
    contract_version: StrictStr
    client_request_id: UUID4
    name: Name
    summary: _text(2000) | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=20)


class UpdateCharacterRequest(ContractModel):
    contract_version: StrictStr
    expected_version: StrictInt
    name: Name | None = None
    summary: _text(2000) | None = None
    tags: list[Tag] | None = Field(default=None, max_length=20)
    cover_asset_id: Annotated[str, StringConstraints(pattern=ASSET_ID_PATTERN)] | None = None


class SaveDraftRequest(ContractModel):
    contract_version: StrictStr
    expected_draft_version: StrictInt
    content: StageContent
    checklist: ApprovalChecklist


class StageDecisionRequest(ContractModel):
    contract_version: StrictStr
    action: Literal["submit", "approve", "request_revision", "withdraw"]
    expected_draft_version: StrictInt
    revision: StrictInt | None = None
    note: _text(2000) | None = None


class CreateReferenceRequest(ContractModel):
    contract_version: StrictStr
    client_request_id: UUID4
    kind: Literal["image", "url"]
    purpose: Literal["moodboard", "sketch", "concept"]
    title: ShortText
    upload_id: StrictStr | None = None
    url: StrictStr | None = None
    source_note: _text(500) | None = None


class ComputeSelection(ContractModel):
    profile_id: StrictStr
    accelerator_id: StrictStr


class CreatePreviewBatchRequest(ContractModel):
    contract_version: StrictStr
    client_request_id: UUID4
    kind: Literal["preview"]
    compute: ComputeSelection


class SubmitBatchRequest(ContractModel):
    contract_version: StrictStr
    client_request_id: UUID4
    compute: ComputeSelection
