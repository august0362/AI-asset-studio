import type {
  Artifact,
  JobStatus,
  OptionValue,
  ErrorItem,
  ResourcePlan,
  ApiClient,
} from "./types";
// Shared aliases (TypeScript)
export type StageId = "s1" | "s2" | "s3" | "s4" | "s5" | "s6" | "s7";
export type EditorialStatus =
  | "not_started"
  | "draft"
  | "in_review"
  | "approved"
  | "needs_revision"
  | "blocked";
export type FeatureAvailability = "available" | "planned" | "unavailable";
export type AssetPurpose =
  | "full_body"
  | "portrait"
  | "key_visual"
  | "front"
  | "side"
  | "back"
  | "three_quarter"
  | "detail"
  | "chibi";

export interface JobReference {
  job_id: string;
  artifact_id: string | null;
}
export interface ResolvedJob {
  job_id: string;
  artifact_id: string | null;
  missing: boolean;
  status: JobStatus | null;
  model_id: string | null;
  prompt: string | null;
  options: Record<string, OptionValue> | null;
  task_id: string | null;
  artifact: Artifact | null;
}
export interface AssetSource {
  job_id: string;
  artifact_id: string;
  task_id: string | null;
  model_id: string;
  model_revision: string | null;
  prompt: string | null;
  negative_prompt: string | null;
  seed: number | null;
  width: number;
  height: number;
  options: Record<string, OptionValue>;
}
export interface RevisionPointer {
  stage_id: StageId;
  revision: number;
}
export interface ArtifactReference {
  asset_id: string;
  purpose: AssetPurpose;
  mime_type: "image/png";
  width: number;
  height: number;
  size_bytes: number;
  sha256: string;
  content_url: string;
  source: AssetSource | null;
  reference_id: string | null;
  frozen_in: RevisionPointer;
  created_at: string;
}

export interface Character {
  contract_version: "1.1";
  character_id: string;
  name: string;
  summary: string | null;
  tags: string[];
  cover_asset_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface CharacterSummary {
  character_id: string;
  name: string;
  tags: string[];
  cover_url: string | null;
  current_stage: StageId;
  approved_count: number;
  stage_statuses: Record<StageId, EditorialStatus>;
  updated_at: string;
}

export interface StageDependency {
  stage_id: StageId;
  kind: "hard" | "soft";
}
export interface ChecklistItemConfig {
  item_id: string;
  label_key: string;
  required: boolean;
}
export interface GuidedQuestion {
  question_id: string;
  label_key: string;
  core: boolean;
}
export interface StageConfig {
  stage_id: StageId;
  order: number;
  title_key: string;
  objective_key: string;
  availability: FeatureAvailability;
  availability_reason: string | null;
  dependencies: StageDependency[];
  checklist: ChecklistItemConfig[];
  required_purposes: AssetPurpose[];
  guided_questions: GuidedQuestion[];
}

export interface ChecklistItemState {
  item_id: string;
  checked: boolean;
  note: string | null;
}
export interface ApprovalChecklist {
  items: ChecklistItemState[];
}

export interface ReferenceAsset {
  contract_version: "1.1";
  reference_id: string;
  character_id: string;
  kind: "image" | "url";
  purpose: "moodboard" | "sketch" | "concept";
  title: string;
  url: string | null;
  source_note: string | null;
  mime_type: "image/png" | "image/jpeg" | "image/webp" | null;
  width: number | null;
  height: number | null;
  size_bytes: number | null;
  sha256: string | null;
  content_url: string | null;
  created_at: string;
}

export type SpecGroup =
  | "identity"
  | "face"
  | "hair"
  | "eyes"
  | "body"
  | "outfit"
  | "accessories"
  | "color"
  | "style"
  | "pose"
  | "other";
export interface ReferenceNote {
  reference_id: string;
  aspects: SpecGroup[];
  likes: string | null;
  do_not_copy: string | null;
}
export interface ConceptContent {
  stage_id: "s1";
  idea: string | null;
  directions: string[];
  notes: string | null;
  palette: string[];
  references: ReferenceNote[];
}
export interface SpecAttribute {
  attribute_id: string;
  group: SpecGroup;
  label: string;
  value: string;
  lock: "locked" | "preferred" | "flexible";
  reference_ids: string[];
}
export interface GuidedAnswer {
  question_id: string;
  status: "answered" | "unknown" | "skipped";
  answer: string | null;
}
export interface CharacterSpecification {
  stage_id: "s2";
  summary: string | null;
  attributes: SpecAttribute[];
  answers: GuidedAnswer[];
  open_questions: string[];
  rejection_criteria: string[];
}
export interface PreviewProfile {
  model_id: string;
  compute_target: "kaggle" | "local";
  variations: number;
  width: number;
  height: number;
  options: Record<string, OptionValue>;
}
export interface ConceptCandidate {
  candidate_id: string;
  source: "batch_task" | "job_artifact" | "reference";
  manifest_id: string | null;
  task_id: string | null;
  job: JobReference | null;
  reference_id: string | null;
  verdict: "undecided" | "selected" | "rejected";
  matches: string[];
  mismatches: string[];
  feedback: string | null;
}
export interface ConceptValidationContent {
  stage_id: "s3";
  preview_profile: PreviewProfile | null;
  preview_prompt: string | null;
  candidates: ConceptCandidate[];
  selected_candidate_id: string | null;
  review_notes: string | null;
}
export interface PromptEntry {
  purpose: AssetPurpose;
  canonical_prompt: string;
  negative_prompt: string | null;
  notes: string | null;
}
export interface ProductionProfile {
  target_model_id: string;
  compute_target: "kaggle";
  options: Record<string, OptionValue>;
}
export interface ProductionTask {
  task_id: string;
  purpose: AssetPurpose;
  prompt: string;
  negative_prompt: string | null;
  seed: number | null;
  width: number;
  height: number;
  options: Record<string, OptionValue>;
}
export interface PromptSet {
  stage_id: "s4";
  entries: PromptEntry[];
  production_profile: ProductionProfile | null;
  tasks: ProductionTask[];
  reference_asset_ids: string[];
}
export interface ProductionItem {
  item_id: string;
  purpose: AssetPurpose;
  manifest_id: string | null;
  task_id: string | null;
  job: JobReference | null;
  selected: boolean;
  note: string | null;
}
export interface ProductionReviewContent {
  stage_id: "s5";
  items: ProductionItem[];
  consistency_notes: string | null;
}
export interface PlannedContent {
  stage_id: "s6" | "s7";
  notes: string | null;
}
export type StageContent =
  | ConceptContent
  | CharacterSpecification
  | ConceptValidationContent
  | PromptSet
  | ProductionReviewContent
  | PlannedContent;

export interface StageDraft {
  contract_version: "1.1";
  character_id: string;
  stage_id: StageId;
  draft_version: number;
  based_on_revision: number | null;
  content: StageContent;
  checklist: ApprovalChecklist;
  updated_at: string | null;
}

export interface StageRevision {
  contract_version: "1.1";
  character_id: string;
  stage_id: StageId;
  revision: number;
  content: StageContent;
  checklist: ApprovalChecklist;
  source_revisions: Partial<Record<StageId, number>>;
  submitted_at: string;
  decision: "pending" | "approved" | "revision_requested" | "withdrawn";
  decided_at: string | null;
  note: string | null;
  frozen_assets: ArtifactReference[];
  batch_manifest_id: string | null;
}
export interface StaleReason {
  upstream_stage_id: StageId;
  used_revision: number;
  current_revision: number;
}
export interface ApprovedSnapshot {
  revision: number;
  approved_at: string;
  source_revisions: Partial<Record<StageId, number>>;
  stale: boolean;
  stale_reasons: StaleReason[];
}

export interface StageState {
  stage_id: StageId;
  editorial_status: EditorialStatus;
  availability: FeatureAvailability;
  draft_version: number;
  has_unsubmitted_changes: boolean;
  latest_revision: number | null;
  pending_revision: number | null;
  approved: ApprovedSnapshot | null;
  last_decision: "approved" | "revision_requested" | "withdrawn" | null;
  blockers: ErrorItem[];
}

export interface BatchTask extends ProductionTask {
  group_id: string;
}
export interface TaskGroup {
  group_id: string;
  model_id: string;
  model_revision: string | null;
  task_ids: string[];
  micro_batch_size: number;
  estimated_runtime_seconds: number | null;
}
export interface BatchAttempt {
  attempt: number;
  group_id: string;
  job_id: string;
  task_ids: string[];
  submitted_at: string;
}
export interface TaskResult {
  task_id: string;
  status: "pending" | "succeeded" | "failed" | "not_run";
  attempt: number | null;
  job_id: string | null;
  artifact_id: string | null;
  sha256: string | null;
  error: ErrorItem | null;
  artifact_missing: boolean;
}
export interface ReferenceUse {
  asset_id: string;
  applied: boolean;
  reason: string | null;
}
export interface BatchManifest {
  contract_version: "1.1";
  manifest_id: string;
  character_id: string;
  kind: "preview" | "production";
  status:
    | "ready"
    | "submitted"
    | "completed"
    | "partially_completed"
    | "failed";
  approved_spec_revision: number;
  prompt_set_revision: number | null;
  concept_revision: number | null;
  target_model_id: string;
  model_revision: string | null;
  references: ReferenceUse[];
  tasks: BatchTask[];
  groups: TaskGroup[];
  expected_model_loads: number;
  attempts: BatchAttempt[];
  results: TaskResult[];
  retryable_task_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface StageHistory {
  seq: number;
  at: string;
  stage_id: StageId | null;
  action:
    | "character_created"
    | "character_updated"
    | "draft_saved"
    | "submitted"
    | "approved"
    | "revision_requested"
    | "withdrawn"
    | "reference_added"
    | "reference_removed"
    | "batch_created"
    | "batch_submitted"
    | "batch_retried";
  revision: number | null;
  manifest_id: string | null;
  affected_stages: StageId[];
  note: string | null;
}

export interface WorkflowStage {
  config: StageConfig;
  state: StageState;
}
export interface CharacterWorkflow {
  contract_version: "1.1";
  character: Character;
  stages: WorkflowStage[];
  approved_outputs: ArtifactReference[];
}
export interface RevisionSummary {
  revision: number;
  decision: StageRevision["decision"];
  submitted_at: string;
  decided_at: string | null;
}
export interface StageInput {
  stage_id: StageId;
  kind: "hard" | "soft";
  revision: number | null;
  content: StageContent | null;
  frozen_assets: ArtifactReference[];
}
export interface StageDetail {
  contract_version: "1.1";
  character: CharacterSummary;
  character_version: number;
  config: StageConfig;
  state: StageState;
  draft: StageDraft;
  approved_revision: StageRevision | null;
  pending_revision: StageRevision | null;
  revisions: RevisionSummary[];
  inputs: StageInput[];
  references: ReferenceAsset[];
  resolved_jobs: ResolvedJob[];
  batches: BatchManifest[];
  manifest_preview: BatchManifest | null;
  resource_plans: ResourcePlan[];
}
export interface CharacterFilters {
  q?: string;
  stage?: StageId;
  status?: EditorialStatus;
  limit?: number;
  cursor?: string;
}
export interface CharacterList {
  contract_version: "1.1";
  characters: CharacterSummary[];
  next_cursor: string | null;
}
export interface CreateCharacterRequest {
  contract_version: string;
  client_request_id: string;
  name: string;
  summary?: string | null;
  tags?: string[];
}
export interface UpdateCharacterRequest {
  contract_version: string;
  expected_version: number;
  name?: string | null;
  summary?: string | null;
  tags?: string[] | null;
  cover_asset_id?: string | null;
}
export interface SaveDraftRequest {
  contract_version: string;
  expected_draft_version: number;
  content: StageContent;
  checklist: ApprovalChecklist;
}
export interface StageDecisionRequest {
  contract_version: string;
  action: "submit" | "approve" | "request_revision" | "withdraw";
  expected_draft_version: number;
  revision?: number | null;
  note?: string | null;
}
export interface CreateReferenceRequest {
  contract_version: string;
  client_request_id: string;
  kind: "image" | "url";
  purpose: ReferenceAsset["purpose"];
  title: string;
  upload_id?: string | null;
  url?: string | null;
  source_note?: string | null;
}
export interface SubmitBatchRequest {
  contract_version: string;
  client_request_id: string;
  compute: { profile_id: string; accelerator_id: string };
}
export interface CreatePreviewBatchRequest extends SubmitBatchRequest {
  kind: "preview";
}
export interface CharacterApi {
  deleteCharacter(id: string): Promise<void>;
  characters(filters?: CharacterFilters): Promise<CharacterList>;
  createCharacter(request: CreateCharacterRequest): Promise<Character>;
  character(id: string): Promise<CharacterWorkflow>;
  updateCharacter(
    id: string,
    request: UpdateCharacterRequest,
  ): Promise<Character>;
  stage(id: string, stage: StageId): Promise<StageDetail>;
  saveStage(
    id: string,
    stage: StageId,
    request: SaveDraftRequest,
  ): Promise<StageDetail>;
  decideStage(
    id: string,
    stage: StageId,
    request: StageDecisionRequest,
  ): Promise<StageDetail>;
  stageRevision(
    id: string,
    stage: StageId,
    revision: number,
  ): Promise<StageRevision>;
  characterHistory(
    id: string,
    limit?: number,
    cursor?: string,
  ): Promise<{
    contract_version: "1.1";
    events: StageHistory[];
    next_cursor: string | null;
  }>;
  createReference(
    id: string,
    request: CreateReferenceRequest,
  ): Promise<ReferenceAsset>;
  referenceContent(id: string, reference: string): Promise<Blob>;
  deleteReference(id: string, reference: string): Promise<void>;
  characterOutputs(
    id: string,
  ): Promise<{ contract_version: "1.1"; outputs: ArtifactReference[] }>;
  assetContent(id: string, asset: string, download?: boolean): Promise<Blob>;
  createPreviewBatch(
    id: string,
    request: CreatePreviewBatchRequest,
  ): Promise<BatchManifest>;
  characterBatch(id: string, manifest: string): Promise<BatchManifest>;
  submitCharacterBatch(
    id: string,
    manifest: string,
    request: SubmitBatchRequest,
  ): Promise<BatchManifest>;
  retryCharacterBatch(
    id: string,
    manifest: string,
    request: SubmitBatchRequest,
  ): Promise<BatchManifest>;
}
export type CharacterJobApi = Pick<
  ApiClient,
  | "job"
  | "uploadRecord"
  | "uploadContent"
  | "artifactContent"
  | "models"
  | "validate"
  | "profiles"
>;

export type CharacterErrorCode =
  | "CHARACTER_NOT_FOUND"
  | "CHARACTER_VERSION_CONFLICT"
  | "STAGE_DRAFT_CONFLICT"
  | "STAGE_NOT_AVAILABLE"
  | "STAGE_BLOCKED"
  | "STAGE_UPSTREAM_CHANGED"
  | "STAGE_CHECKLIST_INCOMPLETE"
  | "STAGE_CONTENT_INCOMPLETE"
  | "STAGE_TRANSITION_INVALID"
  | "REVISION_NOT_FOUND"
  | "REFERENCE_NOT_FOUND"
  | "ASSET_NOT_FOUND"
  | "REFERENCE_IN_USE"
  | "REFERENCE_URL_INVALID"
  | "LINKED_JOB_NOT_FOUND"
  | "LINKED_JOB_NOT_COMPLETED"
  | "LINKED_ARTIFACT_INVALID"
  | "BATCH_NOT_FOUND"
  | "BATCH_ALREADY_SUBMITTED"
  | "BATCH_MANIFEST_STALE"
  | "BATCH_NOTHING_TO_RETRY"
  | "BATCH_ATTEMPT_RUNNING"
  | "BATCH_TASK_FAILED"
  | "BATCH_TASK_NOT_RUN"
  | "BATCH_PARTIAL";
