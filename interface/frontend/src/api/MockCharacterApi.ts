import type {
  CharacterApi,
  CharacterJobApi,
  Character,
  CharacterFilters,
  CharacterSummary,
  CharacterWorkflow,
  StageConfig,
  StageId,
  StageContent,
  StageDraft,
  StageRevision,
  StageHistory,
  StageDetail,
  StageState,
  ReferenceAsset,
  ArtifactReference,
  BatchManifest,
  CreateCharacterRequest,
  UpdateCharacterRequest,
  SaveDraftRequest,
  StageDecisionRequest,
  CreateReferenceRequest,
  CreatePreviewBatchRequest,
  SubmitBatchRequest,
  ProductionTask,
  AssetPurpose,
} from "./characterTypes";
import type { ErrorCode, ErrorItem, GenerationResult } from "./types";
import { ApiError, issue } from "./errors";
import configsJson from "../../tests/fixtures/contracts/v2/stage-configs.json";
import { models, profiles, makeSnapshot } from "./fixtures";
import { planResources } from "../validation/planner";
import {
  sharedCharacterFixture,
  sharedCharacterContent,
  type SharedCharacterFixtureName,
} from "./characterFixtures";
const configs = configsJson as StageConfig[];
const clone = <T>(v: T): T => structuredClone(v);
const stamp = () => new Date().toISOString();
const key = "aas.characters.demo.v1";
const deletedKey = "aas.characters.deleted.v1";
function deletedCharacters(): Set<string> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(deletedKey) ?? "[]");
    return new Set(Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []);
  } catch {
    return new Set();
  }
}
const id = (prefix: string) =>
  `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
function fail(
  code: ErrorCode,
  message: string,
  status = 422,
  details: Record<string, unknown> = {},
): never {
  throw new ApiError(
    {
      contract_version: "1.1",
      errors: [issue(code, null, message, "error", details)],
      warnings: [],
    },
    status,
  );
}
export function emptyContent(stage: StageId): StageContent {
  switch (stage) {
    case "s1":
      return {
        stage_id: stage,
        idea: null,
        directions: [],
        notes: null,
        palette: [],
        references: [],
      };
    case "s2":
      return {
        stage_id: stage,
        summary: null,
        attributes: [],
        answers: [],
        open_questions: [],
        rejection_criteria: [],
      };
    case "s3":
      return {
        stage_id: stage,
        preview_profile: null,
        preview_prompt: null,
        candidates: [],
        selected_candidate_id: null,
        review_notes: null,
      };
    case "s4":
      return {
        stage_id: stage,
        entries: [],
        production_profile: null,
        tasks: [],
        reference_asset_ids: [],
      };
    case "s5":
      return { stage_id: stage, items: [], consistency_notes: null };
    default:
      return { stage_id: stage, notes: null };
  }
}
interface StoredStage {
  draft: StageDraft;
  revisions: StageRevision[];
  submittedVersion: number;
  last: StageState["last_decision"];
}
interface StoredCharacter {
  sharedFixture?: boolean;
  character: Character;
  stages: Record<StageId, StoredStage>;
  references: ReferenceAsset[];
  blobs: Record<string, string>;
  batches: BatchManifest[];
  history: StageHistory[];
  requests: Record<string, string>;
}
function load(): Record<string, StoredCharacter> {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "{}");
  } catch {
    return {};
  }
}
async function dataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = reject;
    r.readAsDataURL(blob);
  });
}
async function fromDataUrl(url: string): Promise<Blob> {
  const [header, data] = url.split(",");
  return new Blob([Uint8Array.from(atob(data), (c) => c.charCodeAt(0))], {
    type: header.slice(5).split(";")[0],
  });
}
async function checksum(blob: Blob) {
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
    ),
    (v) => v.toString(16).padStart(2, "0"),
  ).join("");
}
async function pngImage(blob: Blob) {
  if (blob.type === "image/png") return blob;
  const bitmap = await createImageBitmap(blob),
    canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    fail("INTERNAL_ERROR", "Image conversion is unavailable.", 500);
  }
  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (value) =>
        value ? resolve(value) : reject(new Error("PNG conversion failed.")),
      "image/png",
    ),
  );
}
/** Local DEMO adapter only. Production state and status derivation belong to the backend. */
export abstract class MockCharacterApi implements CharacterApi {
  /** Read-only access to every named request/response snapshot, including error and batch variants. */
  characterFixture<N extends SharedCharacterFixtureName>(name: N) {
    return sharedCharacterFixture(name);
  }
  private fixtureBatchStatus: BatchManifest["status"] = "completed";
  setCharacterBatchScenario(status: BatchManifest["status"]) {
    this.fixtureBatchStatus = status;
  }
  private fixtureWorkflow(cid: string): CharacterWorkflow | undefined {
    this.assertNotDeleted(cid);
    if (this.characterRecords[cid]?.sharedFixture === false) return undefined;
    return [
      sharedCharacterFixture("character_workflow"),
      sharedCharacterFixture("character_workflow_in_progress"),
    ].find((w) => w.character.character_id === cid);
  }
  private fixtureStage(cid: string, sid: StageId): StageDetail | undefined {
    if (!this.fixtureWorkflow(cid)) return undefined;
    if (cid === sharedCharacterFixture("character").character_id)
      return sharedCharacterFixture(`stage_detail_${sid}`);
    if (sid === "s4")
      return sharedCharacterFixture("stage_detail_s4_in_review");
    throw new Error(
      "This partial workflow snapshot has no stage detail fixture. Create a DEMO character to edit all stages.",
    );
  }
  private hydrateFixture(cid: string) {
    if (
      this.characterRecords[cid] ||
      cid !== sharedCharacterFixture("character").character_id
    )
      return;
    const details = configs.map((c) =>
      sharedCharacterFixture(`stage_detail_${c.stage_id}`),
    );
    const revisions = (d: StageDetail) =>
      [d.pending_revision, d.approved_revision].filter(
        (r): r is StageRevision => r !== null,
      );
    this.characterRecords[cid] = {
      sharedFixture: true,
      character: sharedCharacterFixture("character"),
      stages: Object.fromEntries(
        details.map((d) => [
          d.config.stage_id,
          {
            draft: clone(d.draft),
            revisions: revisions(d),
            submittedVersion: d.state.has_unsubmitted_changes
              ? d.draft.draft_version - 1
              : d.draft.draft_version,
            last: d.state.last_decision,
          },
        ]),
      ) as Record<StageId, StoredStage>,
      references: clone(details[0].references),
      blobs: {},
      batches: [
        ...new Map(
          details
            .flatMap((d) => d.batches)
            .map((b) => [b.manifest_id, clone(b)]),
        ).values(),
      ],
      history: sharedCharacterFixture("history_page").events.slice().reverse(),
      requests: {},
    };
  }
  private characterRecords = load();
  private deletedCharacters = deletedCharacters();
  private assertNotDeleted(cid: string) {
    for (const id of deletedCharacters()) this.deletedCharacters.add(id);
    if (this.deletedCharacters.has(cid))
      fail("CHARACTER_NOT_FOUND", "Character not found.", 404);
  }
  private createRequests: Record<string, string> = {};
  protected abstract characterJobs(): CharacterJobApi;
  protected abstract enqueueCharacterTasks(
    character: string,
    manifest: BatchManifest,
    tasks: ProductionTask[],
    request: SubmitBatchRequest,
  ): Promise<GenerationResult>;
  private persist() {
    try {
      localStorage.setItem(key, JSON.stringify(this.characterRecords));
    } catch {
      /* DEMO remains usable in memory when browser storage is unavailable. */
    }
  }
  private getCharacter(id: string) {
    this.assertNotDeleted(id);
    this.sync();
    this.hydrateFixture(id);
    if (!/^chr_[0-9a-f]{12}$/.test(id))
      fail("PATH_INVALID", "Invalid character ID.", 400);
    return (
      this.characterRecords[id] ??
      fail("CHARACTER_NOT_FOUND", "Character not found.", 404)
    );
  }
  private sync() {
    for (const id of deletedCharacters()) this.deletedCharacters.add(id);
    for (const id of this.deletedCharacters) delete this.characterRecords[id];
    for (const [request, id] of Object.entries(this.createRequests))
      if (this.deletedCharacters.has(id)) delete this.createRequests[request];
    const stored = load();
    for (const [id, value] of Object.entries(stored)) {
      if (this.deletedCharacters.has(id)) continue;
      const local = this.characterRecords[id];
      if (!local || value.history.length > local.history.length)
        this.characterRecords[id] = value;
    }
  }
  private event(
    r: StoredCharacter,
    stage: StageId | null,
    action: StageHistory["action"],
    revision: number | null = null,
    note: string | null = null,
    manifest_id: string | null = null,
  ) {
    r.sharedFixture = false;
    r.character.updated_at = stamp();
    r.history.push({
      seq: r.history.length + 1,
      at: stamp(),
      stage_id: stage,
      action,
      revision,
      manifest_id,
      affected_stages: [],
      note,
    });
    this.persist();
  }
  private approved(r: StoredCharacter, s: StageId) {
    return r.stages[s].revisions.find((v) => v.decision === "approved") ?? null;
  }
  private state(r: StoredCharacter, c: StageConfig): StageState {
    const s = r.stages[c.stage_id],
      approved = this.approved(r, c.stage_id),
      pending = s.revisions.find((v) => v.decision === "pending");
    const reasons = approved
      ? c.dependencies.flatMap((d) => {
          const current = this.approved(r, d.stage_id);
          const used = approved.source_revisions[d.stage_id];
          return current && used !== current.revision
            ? [
                {
                  upstream_stage_id: d.stage_id,
                  used_revision: used ?? 0,
                  current_revision: current.revision,
                },
              ]
            : [];
        })
      : [];
    const hasChanges = s.draft.draft_version > s.submittedVersion;
    const missing = c.dependencies.some(
      (d) => d.kind === "hard" && !this.approved(r, d.stage_id),
    );
    const status = pending
      ? "in_review"
      : reasons.length || s.last === "revision_requested"
        ? "needs_revision"
        : hasChanges
          ? "draft"
          : approved
            ? "approved"
            : missing
              ? "blocked"
              : "not_started";
    return {
      stage_id: c.stage_id,
      editorial_status: status,
      availability: c.availability,
      draft_version: s.draft.draft_version,
      has_unsubmitted_changes: hasChanges,
      latest_revision: s.revisions[0]?.revision ?? null,
      pending_revision: pending?.revision ?? null,
      approved: approved
        ? {
            revision: approved.revision,
            approved_at: approved.decided_at!,
            source_revisions: approved.source_revisions,
            stale: !!reasons.length,
            stale_reasons: reasons,
          }
        : null,
      last_decision: s.last,
      blockers: this.blockers(r, c, pending ?? s.draft),
    };
  }
  private blockers(
    r: StoredCharacter,
    c: StageConfig,
    d: StageDraft | StageRevision,
  ): ErrorItem[] {
    const errors: ErrorItem[] = [];
    const add = (
      code: ErrorCode,
      message: string,
      details: Record<string, unknown> = {},
    ) => errors.push(issue(code, null, message, "error", details));
    if (c.availability !== "available")
      add("STAGE_NOT_AVAILABLE", "This stage is planned or unavailable.");
    for (const dep of c.dependencies.filter((v) => v.kind === "hard")) {
      const a = this.approved(r, dep.stage_id);
      if (!a)
        add("STAGE_BLOCKED", "Approve the required upstream stage first.", {
          stage_id: dep.stage_id,
        });
      else if (
        "source_revisions" in d &&
        d.source_revisions[dep.stage_id] !== a.revision
      )
        add(
          "STAGE_UPSTREAM_CHANGED",
          "The upstream revision changed. Submit again.",
        );
    }
    const unchecked = c.checklist.filter(
      (i) =>
        i.required &&
        !d.checklist.items.some((v) => v.item_id === i.item_id && v.checked),
    );
    if (unchecked.length)
      add("STAGE_CHECKLIST_INCOMPLETE", "Complete the required checklist.", {
        item_ids: unchecked.map((i) => i.item_id),
      });
    const v = d.content;
    let complete = true;
    if (v.stage_id === "s1")
      complete =
        !!(v.idea?.trim() || v.references.length) &&
        v.directions.some((t) => t.trim());
    if (v.stage_id === "s2")
      complete =
        v.attributes.some((a) => a.lock === "locked") &&
        v.attributes.every((a) => a.value.trim());
    if (v.stage_id === "s3")
      complete =
        v.candidates.filter((a) => a.verdict === "selected").length === 1 &&
        v.candidates.some(
          (a) =>
            a.candidate_id === v.selected_candidate_id &&
            a.verdict === "selected",
        );
    if (v.stage_id === "s4")
      complete =
        !!v.production_profile &&
        c.required_purposes.every(
          (p) =>
            v.entries.some(
              (e) => e.purpose === p && e.canonical_prompt.trim(),
            ) &&
            v.tasks.some(
              (t) => t.purpose === p && t.prompt.trim() && t.seed !== null,
            ),
        );
    if (v.stage_id === "s5")
      complete =
        c.required_purposes.every(
          (p) =>
            v.items.filter((i) => i.purpose === p && i.selected).length === 1,
        ) &&
        v.items
          .filter((i) => i.selected)
          .every(
            (i) =>
              v.items.filter((j) => j.purpose === i.purpose && j.selected)
                .length === 1,
          );
    if (!complete)
      add("STAGE_CONTENT_INCOMPLETE", "Required stage content is incomplete.", {
        rule: c.stage_id,
      });
    return errors;
  }
  private summary(r: StoredCharacter): CharacterSummary {
    const states = configs.map((c) => this.state(r, c));
    return {
      character_id: r.character.character_id,
      name: r.character.name,
      tags: r.character.tags,
      cover_url: r.character.cover_asset_id
        ? `/api/v1/characters/${r.character.character_id}/assets/${r.character.cover_asset_id}/content`
        : null,
      current_stage:
        states.find((s) => s.editorial_status !== "approved")?.stage_id ?? "s7",
      approved_count: states.filter((s) => s.editorial_status === "approved")
        .length,
      stage_statuses: Object.fromEntries(
        states.map((s) => [s.stage_id, s.editorial_status]),
      ) as CharacterSummary["stage_statuses"],
      updated_at: r.character.updated_at,
    };
  }
  async characters(filters: CharacterFilters = {}) {
    this.sync();
    const fixtureRows = sharedCharacterFixture(
      "character_list",
    ).characters.filter(
      (c) =>
        !this.deletedCharacters.has(c.character_id) &&
        (!this.characterRecords[c.character_id] ||
        this.characterRecords[c.character_id].sharedFixture),
    );
    const rows = [
      ...fixtureRows,
      ...Object.values(this.characterRecords)
        .filter((r) => !r.sharedFixture && !this.deletedCharacters.has(r.character.character_id))
        .map((r) => this.summary(r)),
    ]
      .filter(
        (c) =>
          (!filters.q ||
            [c.name, c.character_id, ...c.tags]
              .join(" ")
              .toLowerCase()
              .includes(filters.q.toLowerCase())) &&
          (!filters.stage || c.current_stage === filters.stage) &&
          (!filters.status ||
            c.stage_statuses[c.current_stage] === filters.status),
      )
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    const offset = Number(filters.cursor) || 0,
      limit = filters.limit ?? 50;
    return clone({
      contract_version: "1.1" as const,
      characters: rows.slice(offset, offset + limit),
      next_cursor: offset + limit < rows.length ? String(offset + limit) : null,
    });
  }
  async createCharacter(req: CreateCharacterRequest) {
    this.sync();
    const old =
      this.createRequests[req.client_request_id] ??
      Object.values(this.characterRecords).find(
        (r) => r.requests[req.client_request_id] === r.character.character_id,
      )?.character.character_id;
    if (old) return clone(this.getCharacter(old).character);
    if (!req.name.trim() || req.name.trim().length > 80)
      fail(
        "REQUEST_FIELD_INVALID",
        "Enter a character name of 1–80 characters.",
      );
    const cid = id("chr"),
      now = stamp();
    const character: Character = {
      contract_version: "1.1",
      character_id: cid,
      name: req.name.trim(),
      summary: req.summary ?? null,
      tags: req.tags ?? [],
      cover_asset_id: null,
      version: 1,
      created_at: now,
      updated_at: now,
    };
    const stages = Object.fromEntries(
      configs.map((c) => [
        c.stage_id,
        {
          draft: {
            contract_version: "1.1",
            character_id: cid,
            stage_id: c.stage_id,
            draft_version: 0,
            based_on_revision: null,
            content: emptyContent(c.stage_id),
            checklist: {
              items: c.checklist.map((i) => ({
                item_id: i.item_id,
                checked: false,
                note: null,
              })),
            },
            updated_at: null,
          },
          revisions: [],
          submittedVersion: 0,
          last: null,
        },
      ]),
    ) as unknown as StoredCharacter["stages"];
    this.characterRecords[cid] = {
      character,
      stages,
      references: [],
      blobs: {},
      batches: [],
      history: [],
      requests: { [req.client_request_id]: cid },
    };
    this.createRequests[req.client_request_id] = cid;
    this.event(this.characterRecords[cid], null, "character_created");
    return clone(character);
  }
  async character(cid: string): Promise<CharacterWorkflow> {
    this.sync();
    const fixture = this.fixtureWorkflow(cid);
    if (fixture) return fixture;
    const r = this.getCharacter(cid);
    return clone({
      contract_version: "1.1",
      character: r.character,
      stages: configs.map((config) => ({
        config,
        state: this.state(r, config),
      })),
      approved_outputs: configs.flatMap(
        (c) => this.approved(r, c.stage_id)?.frozen_assets ?? [],
      ),
    });
  }
  async deleteCharacter(cid: string): Promise<void> {
    await this.character(cid);
    const fixture = this.fixtureWorkflow(cid);
    const manifests = fixture
      ? cid === sharedCharacterFixture("character").character_id
        ? configs.flatMap((c) => sharedCharacterFixture(`stage_detail_${c.stage_id}`).batches)
        : sharedCharacterFixture("stage_detail_s4_in_review").batches
      : this.getCharacter(cid).batches;
    const current = fixture ? await Promise.all(
      [...new Set(manifests.map((b) => b.manifest_id))].map((bid) => this.characterBatch(cid, bid)),
    ) : manifests;
    const running = current.filter((b) => b.results.some((r) => r.status === "pending" && r.attempt !== null));
    if (running.length)
      fail("BATCH_ATTEMPT_RUNNING", "Wait for the running attempt to finish.", 409, {
        manifest_ids: running.map((b) => b.manifest_id),
      });
    this.deletedCharacters.add(cid);
    delete this.characterRecords[cid];
    for (const [request, id] of Object.entries(this.createRequests))
      if (id === cid) delete this.createRequests[request];
    this.persist();
    try {
      localStorage.setItem(deletedKey, JSON.stringify([...this.deletedCharacters]));
    } catch {
      /* Deletion remains effective in memory without storage. */
    }
  }
  async updateCharacter(cid: string, req: UpdateCharacterRequest) {
    const r = this.getCharacter(cid);
    if (req.expected_version !== r.character.version)
      fail(
        "CHARACTER_VERSION_CONFLICT",
        "The character changed. Reload before saving.",
        409,
        { current_version: r.character.version },
      );
    if (req.name !== undefined && req.name !== null) {
      if (!req.name.trim() || req.name.trim().length > 80)
        fail(
          "REQUEST_FIELD_INVALID",
          "Enter a character name of 1–80 characters.",
        );
      r.character.name = req.name.trim();
    }
    if (req.tags) r.character.tags = req.tags;
    if (req.summary !== undefined && req.summary !== null)
      r.character.summary = req.summary;
    if (req.cover_asset_id) {
      const outputs = await this.characterOutputs(cid);
      if (!outputs.outputs.some((a) => a.asset_id === req.cover_asset_id))
        fail("ASSET_NOT_FOUND", "Frozen image not found.");
      r.character.cover_asset_id = req.cover_asset_id;
    }
    r.character.version++;
    this.event(r, null, "character_updated");
    return clone(r.character);
  }
  async stage(cid: string, sid: StageId): Promise<StageDetail> {
    this.sync();
    const fixture = this.fixtureStage(cid, sid);
    if (fixture) return fixture;
    const r = this.getCharacter(cid),
      config =
        configs.find((c) => c.stage_id === sid) ??
        fail("PATH_INVALID", "Invalid stage ID.", 400),
      s = r.stages[sid];
    const batches = await Promise.all(
      r.batches
        .filter((b) =>
          sid === "s3"
            ? b.kind === "preview"
            : ["s4", "s5"].includes(sid) && b.kind === "production",
        )
        .map((b) => this.characterBatch(cid, b.manifest_id)),
    );
    const linked =
      s.draft.content.stage_id === "s3"
        ? s.draft.content.candidates.flatMap((c) => (c.job ? [c.job] : []))
        : s.draft.content.stage_id === "s5"
          ? s.draft.content.items.flatMap((c) => (c.job ? [c.job] : []))
          : [];
    const resolved = await Promise.all(
      linked.map(async (ref) => {
        try {
          const job = await this.characterJobs().job(ref.job_id),
            artifact = ref.artifact_id
              ? job.artifacts.find((a) => a.artifact_id === ref.artifact_id)
              : job.artifacts.find((a) => a.is_primary);
          return {
            job_id: ref.job_id,
            artifact_id: ref.artifact_id,
            missing: job.status === "completed" && !artifact,
            status: job.status,
            model_id: job.request.model_id,
            prompt: job.request.prompt,
            options: job.request.options,
            task_id: artifact?.task_id ?? null,
            artifact: artifact ?? null,
          };
        } catch {
          return {
            job_id: ref.job_id,
            artifact_id: ref.artifact_id,
            missing: true,
            status: null,
            model_id: null,
            prompt: null,
            options: null,
            task_id: null,
            artifact: null,
          };
        }
      }),
    );
    const preview = sid === "s4" ? this.manifest(r, false) : null;
    const manifest = preview ?? batches[0];
    const resource_plans =
      manifest && ["s4", "s5"].includes(sid)
        ? manifest.groups.flatMap((g) => {
            const m = models.find((m) => m.model_id === g.model_id),
              p = profiles.find((p) => p.enabled);
            return m && p
              ? [
                  planResources(
                    {
                      ...m,
                      runtime: {
                        ...m.runtime,
                        estimated_runtime_seconds: g.estimated_runtime_seconds,
                      },
                    },
                    p,
                    makeSnapshot("fresh"),
                    null,
                  ),
                ]
              : [];
          })
        : [];
    return clone({
      contract_version: "1.1",
      character: this.summary(r),
      character_version: r.character.version,
      config,
      state: this.state(r, config),
      draft: s.draft,
      approved_revision: this.approved(r, sid),
      pending_revision:
        s.revisions.find((v) => v.decision === "pending") ?? null,
      revisions: s.revisions.map(
        ({ revision, decision, submitted_at, decided_at }) => ({
          revision,
          decision,
          submitted_at,
          decided_at,
        }),
      ),
      inputs: config.dependencies.map((d) => {
        const a = this.approved(r, d.stage_id);
        return {
          ...d,
          revision: a?.revision ?? null,
          content: a?.content ?? null,
          frozen_assets: a?.frozen_assets ?? [],
        };
      }),
      references: r.references,
      resolved_jobs: resolved,
      batches,
      manifest_preview: preview,
      resource_plans,
    });
  }
  async saveStage(cid: string, sid: StageId, req: SaveDraftRequest) {
    const r = this.getCharacter(cid),
      s = r.stages[sid];
    if (!s) fail("PATH_INVALID", "Invalid stage ID.", 400);
    if (configs.find((c) => c.stage_id === sid)!.availability !== "available")
      fail("STAGE_NOT_AVAILABLE", "This stage is planned.");
    this.version(s, req.expected_draft_version);
    if (req.content.stage_id !== sid)
      fail("REQUEST_FIELD_INVALID", "Content does not match the stage.");
    const refs = JSON.stringify(req.content);
    for (const ref of refs.matchAll(/ref_[0-9a-f]{12}/g))
      if (!r.references.some((v) => v.reference_id === ref[0]))
        fail("REFERENCE_NOT_FOUND", "Reference not found.");
    s.draft = {
      ...s.draft,
      content: clone(req.content),
      checklist: clone(req.checklist),
      draft_version: s.draft.draft_version + 1,
      based_on_revision: this.approved(r, sid)?.revision ?? null,
      updated_at: stamp(),
    };
    this.event(r, sid, "draft_saved");
    return this.stage(cid, sid);
  }
  private version(s: StoredStage, version: number) {
    if (s.draft.draft_version !== version)
      fail(
        "STAGE_DRAFT_CONFLICT",
        "The draft changed. Reload before saving.",
        409,
        { current_draft_version: s.draft.draft_version },
      );
  }
  async decideStage(cid: string, sid: StageId, req: StageDecisionRequest) {
    const r = this.getCharacter(cid),
      s = r.stages[sid],
      c = configs.find((c) => c.stage_id === sid)!;
    if (c.availability !== "available")
      fail("STAGE_NOT_AVAILABLE", "This stage is planned.");
    this.version(s, req.expected_draft_version);
    const pending = s.revisions.find((v) => v.decision === "pending");
    if (req.action === "submit") {
      if (pending || !s.draft.draft_version)
        fail(
          "STAGE_TRANSITION_INVALID",
          "Save a draft and close the pending review first.",
          409,
        );
      const revision = (s.revisions[0]?.revision ?? 0) + 1;
      s.revisions.unshift({
        contract_version: "1.1",
        character_id: cid,
        stage_id: sid,
        revision,
        content: clone(s.draft.content),
        checklist: clone(s.draft.checklist),
        source_revisions: Object.fromEntries(
          c.dependencies.flatMap((d) => {
            const a = this.approved(r, d.stage_id);
            return a ? [[d.stage_id, a.revision]] : [];
          }),
        ),
        submitted_at: stamp(),
        decision: "pending",
        decided_at: null,
        note: req.note ?? null,
        frozen_assets: [],
        batch_manifest_id: null,
      });
      s.submittedVersion = s.draft.draft_version;
      s.last = null;
      this.event(r, sid, "submitted", revision);
    } else {
      const target = pending ?? this.approved(r, sid);
      if (
        !target ||
        (pending && req.revision !== pending.revision) ||
        (!pending && req.action !== "request_revision")
      )
        fail(
          "STAGE_TRANSITION_INVALID",
          "This decision is not valid for the current revision.",
          409,
        );
      if (req.action === "approve") {
        const blockers = this.blockers(r, c, target);
        if (blockers.length)
          throw new ApiError({
            contract_version: "1.1",
            errors: blockers,
            warnings: [],
          });
        const frozen = await this.freeze(r, sid, target);
        target.frozen_assets = frozen;
        if (sid === "s4") {
          const manifest =
            this.manifest(r, true, target.revision) ??
            fail("STAGE_CONTENT_INCOMPLETE", "Production setup is incomplete.");
          r.batches.unshift(manifest);
          target.batch_manifest_id = manifest.manifest_id;
        }
        target.decision = "approved";
        s.last = "approved";
      } else {
        target.decision =
          req.action === "withdraw" ? "withdrawn" : "revision_requested";
        s.last = target.decision;
      }
      target.decided_at = stamp();
      target.note = req.note ?? null;
      this.event(r, sid, target.decision, target.revision, target.note);
      if (req.action === "approve")
        r.history.at(-1)!.affected_stages = configs
          .filter((v) => this.state(r, v).approved?.stale)
          .map((v) => v.stage_id);
      this.persist();
    }
    return this.stage(cid, sid);
  }
  private async freeze(r: StoredCharacter, sid: StageId, v: StageRevision) {
    const sources: {
      purpose: AssetPurpose;
      job?: { job_id: string; artifact_id: string | null };
      reference?: string;
      manifest?: string;
      task?: string;
    }[] = [];
    if (v.content.stage_id === "s3") {
      const content = v.content;
      const c = content.candidates.find(
        (c) => c.candidate_id === content.selected_candidate_id,
      )!;
      sources.push({
        purpose: "key_visual",
        job: c.job ?? undefined,
        reference: c.reference_id ?? undefined,
        manifest: c.manifest_id ?? undefined,
        task: c.task_id ?? undefined,
      });
    }
    if (v.content.stage_id === "s5")
      for (const i of v.content.items.filter((i) => i.selected))
        sources.push({
          purpose: i.purpose,
          job: i.job ?? undefined,
          manifest: i.manifest_id ?? undefined,
          task: i.task_id ?? undefined,
        });
    const frozen: ArtifactReference[] = [];
    const frozenBlobs: Record<string, string> = {};
    for (const source of sources) {
      const aid = id("ast");
      let blob: Blob;
      let asset: ArtifactReference;
      const ref = r.references.find((v) => v.reference_id === source.reference);
      if (ref) {
        if (!ref.mime_type?.startsWith("image/"))
          fail("LINKED_ARTIFACT_INVALID", "Select an image reference.");
        blob = await this.referenceContent(
          r.character.character_id,
          ref.reference_id,
        );
        if ((await checksum(blob)) !== ref.sha256)
          fail(
            "LINKED_ARTIFACT_INVALID",
            "The reference checksum does not match.",
          );
        blob = await pngImage(blob);
        asset = {
          asset_id: aid,
          purpose: source.purpose,
          mime_type: "image/png",
          width: ref.width!,
          height: ref.height!,
          size_bytes: blob.size,
          sha256: await checksum(blob),
          content_url: `/api/v1/characters/${r.character.character_id}/assets/${aid}/content`,
          source: null,
          reference_id: ref.reference_id,
          frozen_in: { stage_id: sid, revision: v.revision },
          created_at: stamp(),
        };
      } else {
        const result = r.batches
          .find((b) => b.manifest_id === source.manifest)
          ?.results.find((t) => t.task_id === source.task);
        const jobId =
          source.job?.job_id ??
          result?.job_id ??
          fail("LINKED_JOB_NOT_FOUND", "Link a completed job.");
        const job = await this.characterJobs().job(jobId);
        const task = r.batches
          .find((b) => b.manifest_id === source.manifest)
          ?.tasks.find((t) => t.task_id === source.task);
        if (job.status !== "completed")
          fail("LINKED_JOB_NOT_COMPLETED", "Wait for the job to complete.");
        const artifact =
          job.artifacts.find(
            (a) =>
              a.artifact_id ===
              (source.job?.artifact_id ?? result?.artifact_id),
          ) ?? job.artifacts.find((a) => a.is_primary);
        if (!artifact || artifact.format !== "png")
          fail("LINKED_ARTIFACT_INVALID", "Select a PNG artifact.");
        blob = await this.characterJobs().artifactContent(
          jobId,
          artifact.artifact_id,
        );
        asset = {
          asset_id: aid,
          purpose: source.purpose,
          mime_type: "image/png",
          width: artifact.width!,
          height: artifact.height!,
          size_bytes: artifact.size_bytes,
          sha256: artifact.sha256,
          content_url: `/api/v1/characters/${r.character.character_id}/assets/${aid}/content`,
          source: {
            job_id: jobId,
            artifact_id: artifact.artifact_id,
            task_id: artifact.task_id ?? null,
            model_id: job.request.model_id,
            model_revision: null,
            prompt: task?.prompt ?? job.request.prompt,
            negative_prompt: task
              ? task.negative_prompt
              : typeof job.request.options.negative_prompt === "string"
                ? job.request.options.negative_prompt
                : null,
            seed: task
              ? task.seed
              : typeof job.request.options.seed === "number"
                ? job.request.options.seed
                : null,
            width: artifact.width!,
            height: artifact.height!,
            options: task
              ? {
                  ...task.options,
                  width: task.width,
                  height: task.height,
                  seed: task.seed,
                }
              : job.request.options,
          },
          reference_id: null,
          frozen_in: { stage_id: sid, revision: v.revision },
          created_at: stamp(),
        };
      }
      const hash = Array.from(
        new Uint8Array(
          await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()),
        ),
        (v) => v.toString(16).padStart(2, "0"),
      ).join("");
      if (hash !== asset.sha256)
        fail("LINKED_ARTIFACT_INVALID", "The image checksum does not match.");
      frozenBlobs[aid] = await dataUrl(blob);
      frozen.push(asset);
    }
    Object.assign(r.blobs, frozenBlobs);
    return frozen;
  }
  async stageRevision(cid: string, sid: StageId, revision: number) {
    const fixture = this.fixtureStage(cid, sid);
    const snapshot =
      fixture &&
      [fixture.approved_revision, fixture.pending_revision].find(
        (r) => r?.revision === revision,
      );
    if (snapshot) return clone(snapshot);
    return clone(
      this.getCharacter(cid).stages[sid].revisions.find(
        (v) => v.revision === revision,
      ) ?? fail("REVISION_NOT_FOUND", "Revision not found.", 404),
    );
  }
  async characterHistory(cid: string, limit = 100, cursor = "") {
    if (
      this.fixtureWorkflow(cid) &&
      cid === sharedCharacterFixture("character").character_id
    ) {
      const page = sharedCharacterFixture("history_page");
      return cursor
        ? { contract_version: "1.1" as const, events: [], next_cursor: null }
        : { ...page, events: page.events.slice(0, limit) };
    }
    const r = this.getCharacter(cid),
      offset = Number(cursor) || 0;
    const rows = [...r.history].reverse();
    return clone({
      contract_version: "1.1" as const,
      events: rows.slice(offset, offset + limit),
      next_cursor: offset + limit < rows.length ? String(offset + limit) : null,
    });
  }
  async createReference(cid: string, req: CreateReferenceRequest) {
    const r = this.getCharacter(cid);
    const existing = r.requests[req.client_request_id];
    if (existing)
      return clone(r.references.find((v) => v.reference_id === existing)!);
    if (
      req.kind === "url" &&
      (!req.url || !/^https?:\/\//i.test(req.url) || req.url.length > 2000)
    )
      fail("REFERENCE_URL_INVALID", "Enter an HTTP or HTTPS URL.");
    const rid = id("ref"),
      u =
        req.kind === "image"
          ? await this.characterJobs().uploadRecord(req.upload_id ?? "")
          : null;
    if (u)
      r.blobs[rid] = await dataUrl(
        await this.characterJobs().uploadContent(u.upload_id),
      );
    const ref: ReferenceAsset = {
      contract_version: "1.1",
      reference_id: rid,
      character_id: cid,
      kind: req.kind,
      purpose: req.purpose,
      title: req.title,
      url: req.url ?? null,
      source_note: req.source_note ?? null,
      mime_type: (u?.mime_type as ReferenceAsset["mime_type"]) ?? null,
      width: u?.width ?? null,
      height: u?.height ?? null,
      size_bytes: u?.size_bytes ?? null,
      sha256: u?.sha256 ?? null,
      content_url: u
        ? `/api/v1/characters/${cid}/references/${rid}/content`
        : null,
      created_at: stamp(),
    };
    r.references.push(ref);
    r.requests[req.client_request_id] = rid;
    this.event(r, null, "reference_added");
    return clone(ref);
  }
  async referenceContent(cid: string, rid: string) {
    this.assertNotDeleted(cid);
    const local = this.characterRecords[cid]?.blobs[rid];
    if (local) return fromDataUrl(local);
    return sharedCharacterContent(
      `/api/v1/characters/${cid}/references/${rid}/content`,
    );
  }
  async deleteReference(cid: string, rid: string) {
    const r = this.getCharacter(cid);
    if (
      JSON.stringify(r.stages).includes(rid) ||
      JSON.stringify(r.batches).includes(rid)
    )
      fail("REFERENCE_IN_USE", "A stage uses this reference.", 409, {
        used_by: configs
          .filter((c) => JSON.stringify(r.stages[c.stage_id]).includes(rid))
          .map((c) => c.stage_id),
      });
    r.references = r.references.filter((v) => v.reference_id !== rid);
    delete r.blobs[rid];
    this.event(r, null, "reference_removed");
  }
  async characterOutputs(cid: string) {
    if (
      this.fixtureWorkflow(cid) &&
      cid === sharedCharacterFixture("character").character_id
    )
      return sharedCharacterFixture("outputs");
    return {
      contract_version: "1.1" as const,
      outputs: (await this.character(cid)).approved_outputs,
    };
  }
  async assetContent(cid: string, aid: string) {
    this.assertNotDeleted(cid);
    const local = this.characterRecords[cid]?.blobs[aid];
    if (local) return fromDataUrl(local);
    return sharedCharacterContent(
      `/api/v1/characters/${cid}/assets/${aid}/content`,
    );
  }
  private manifest(
    r: StoredCharacter,
    store: boolean,
    revision: number | null = null,
  ): BatchManifest | null {
    const v = r.stages.s4.draft.content;
    if (v.stage_id !== "s4" || !v.production_profile) return null;
    const model = models.find(
        (m) => m.model_id === v.production_profile!.target_model_id,
      ),
      tasks = v.tasks.map((t) => ({
        ...clone(t),
        options: { ...v.production_profile!.options, ...t.options },
        group_id: "g01",
      }));
    return {
      contract_version: "1.1",
      manifest_id: store ? id("bat") : "bat_000000000000",
      character_id: r.character.character_id,
      kind: "production",
      status: "ready",
      approved_spec_revision: this.approved(r, "s2")?.revision ?? 0,
      prompt_set_revision: revision,
      concept_revision: this.approved(r, "s3")?.revision ?? null,
      target_model_id: v.production_profile.target_model_id,
      model_revision: null,
      references: v.reference_asset_ids.map((asset_id) => ({
        asset_id,
        applied: false,
        reason: "model_has_no_image_role",
      })),
      tasks,
      groups: tasks.length
        ? [
            {
              group_id: "g01",
              model_id: v.production_profile.target_model_id,
              model_revision: null,
              task_ids: tasks.map((t) => t.task_id),
              micro_batch_size: 1,
              estimated_runtime_seconds:
                model?.runtime.estimated_runtime_seconds == null
                  ? null
                  : Math.round(
                      model.runtime.estimated_runtime_seconds * tasks.length,
                    ),
            },
          ]
        : [],
      expected_model_loads: tasks.length ? 1 : 0,
      attempts: [],
      results: tasks.map((t) => ({
        task_id: t.task_id,
        status: "pending",
        attempt: null,
        job_id: null,
        artifact_id: null,
        sha256: null,
        error: null,
        artifact_missing: false,
      })),
      retryable_task_ids: [],
      created_at: stamp(),
      updated_at: stamp(),
    };
  }
  async createPreviewBatch(cid: string, req: CreatePreviewBatchRequest) {
    const r = this.getCharacter(cid),
      old = r.requests[req.client_request_id];
    if (old) return this.characterBatch(cid, old);
    if (!this.approved(r, "s2"))
      fail("STAGE_BLOCKED", "Approve S2 before generating previews.");
    const c = r.stages.s3.draft.content;
    if (c.stage_id !== "s3" || !c.preview_profile || !c.preview_prompt?.trim())
      fail(
        "STAGE_CONTENT_INCOMPLETE",
        "Save a preview profile and prompt first.",
      );
    if (c.preview_profile.compute_target !== "kaggle")
      fail("STAGE_NOT_AVAILABLE", "Local inference is planned.");
    const model =
      models.find((m) => m.model_id === c.preview_profile!.model_id) ??
      fail("MODEL_NOT_FOUND", "Preview model not found.");
    const tasks = Array.from(
      { length: c.preview_profile.variations },
      (_, i) => ({
        task_id: `preview_${String(i + 1).padStart(2, "0")}`,
        purpose: "full_body" as const,
        prompt: c.preview_prompt!,
        negative_prompt: null,
        seed: null,
        width: c.preview_profile!.width,
        height: c.preview_profile!.height,
        options: c.preview_profile!.options,
        group_id: "g01",
      }),
    );
    const manifest: BatchManifest = {
      contract_version: "1.1",
      manifest_id: id("bat"),
      character_id: cid,
      kind: "preview",
      status: "ready",
      approved_spec_revision: this.approved(r, "s2")!.revision,
      prompt_set_revision: null,
      concept_revision: null,
      target_model_id: model.model_id,
      model_revision: null,
      references: [],
      tasks,
      groups: [
        {
          group_id: "g01",
          model_id: model.model_id,
          model_revision: null,
          task_ids: tasks.map((t) => t.task_id),
          micro_batch_size: 1,
          estimated_runtime_seconds:
            model.runtime.estimated_runtime_seconds === null
              ? null
              : model.runtime.estimated_runtime_seconds * tasks.length,
        },
      ],
      expected_model_loads: 1,
      attempts: [],
      results: tasks.map((t) => ({
        task_id: t.task_id,
        status: "pending",
        attempt: null,
        job_id: null,
        artifact_id: null,
        sha256: null,
        error: null,
        artifact_missing: false,
      })),
      retryable_task_ids: [],
      created_at: stamp(),
      updated_at: stamp(),
    };
    await this.run(r, manifest, req, false);
    r.batches.unshift(manifest);
    r.requests[req.client_request_id] = manifest.manifest_id;
    this.event(r, "s3", "batch_created", null, null, manifest.manifest_id);
    return clone(manifest);
  }
  async characterBatch(cid: string, bid: string) {
    this.assertNotDeleted(cid);
    if (bid === "bat_000000000000")
      fail("BATCH_NOT_FOUND", "Manifest previews are not stored.", 404);
    if (this.fixtureWorkflow(cid)) {
      const selected = sharedCharacterFixture(
        `batch_manifest_${this.fixtureBatchStatus}`,
      );
      if (selected.character_id === cid && selected.manifest_id === bid)
        return selected;
      const existing = sharedCharacterFixture("batch_manifest_failed");
      if (existing.character_id === cid && existing.manifest_id === bid)
        return existing;
      const nested = configs
        .flatMap((c) =>
          cid === sharedCharacterFixture("character").character_id
            ? sharedCharacterFixture(`stage_detail_${c.stage_id}`).batches
            : [],
        )
        .find((b) => b.manifest_id === bid);
      if (nested) return nested;
    }
    const r = this.getCharacter(cid),
      b =
        r.batches.find((b) => b.manifest_id === bid) ??
        fail("BATCH_NOT_FOUND", "Batch not found.", 404);
    for (const result of b.results) {
      if (result.status === "succeeded" && result.job_id) {
        try {
          const job = await this.characterJobs().job(result.job_id);
          result.artifact_missing = !job.artifacts.some(
            (a) => a.artifact_id === result.artifact_id,
          );
        } catch {
          result.artifact_missing = true;
        }
      }
      if (result.status !== "pending" || !result.job_id) continue;
      try {
        const job = await this.characterJobs().job(result.job_id);
        if (job.status === "completed" || job.status === "failed") {
          const a = job.artifacts.find((a) => a.task_id === result.task_id);
          const skipped = job.warnings.some(
            (w) =>
              w.code === "BATCH_PARTIAL" &&
              Array.isArray(w.details.not_run) &&
              w.details.not_run.includes(result.task_id),
          );
          Object.assign(
            result,
            a
              ? {
                  status: "succeeded",
                  artifact_id: a.artifact_id,
                  sha256: a.sha256,
                  error: null,
                }
              : {
                  status: skipped ? "not_run" : "failed",
                  error:
                    job.error ??
                    issue(
                      skipped ? "BATCH_TASK_NOT_RUN" : "BATCH_TASK_FAILED",
                      null,
                      "No output was produced.",
                      "error",
                      {},
                      true,
                    ),
                },
          );
        }
      } catch {
        Object.assign(result, {
          status: "failed",
          artifact_missing: true,
          error: issue(
            "LINKED_JOB_NOT_FOUND",
            null,
            "The demo job no longer exists.",
          ),
        });
      }
    }
    b.status = !b.attempts.length
      ? "ready"
      : b.results.some((t) => t.status === "pending")
        ? "submitted"
        : b.results.every((t) => t.status === "succeeded")
          ? "completed"
          : b.results.some((t) => t.status === "succeeded")
            ? "partially_completed"
            : "failed";
    b.retryable_task_ids =
      b.status === "submitted"
        ? []
        : b.results
            .filter((t) => ["failed", "not_run"].includes(t.status))
            .map((t) => t.task_id);
    this.persist();
    return clone(b);
  }
  private async run(
    r: StoredCharacter,
    b: BatchManifest,
    req: SubmitBatchRequest,
    retry: boolean,
  ) {
    const tasks = retry
      ? b.tasks.filter((t) => b.retryable_task_ids.includes(t.task_id))
      : b.tasks;
    if (!tasks.length)
      fail("BATCH_NOTHING_TO_RETRY", "There are no unfinished tasks.", 409);
    const job = await this.enqueueCharacterTasks(
      r.character.character_id,
      b,
      tasks,
      req,
    );
    const attempt = b.attempts.length + 1;
    b.attempts.push({
      attempt,
      group_id: "g01",
      job_id: job.job_id,
      task_ids: tasks.map((t) => t.task_id),
      submitted_at: stamp(),
    });
    for (const result of b.results.filter((t) =>
      tasks.some((v) => v.task_id === t.task_id),
    ))
      Object.assign(result, {
        status: "pending",
        attempt,
        job_id: job.job_id,
        artifact_id: null,
        sha256: null,
        error: null,
        artifact_missing: false,
      });
    b.status = "submitted";
    b.retryable_task_ids = [];
    b.updated_at = stamp();
    r.requests[req.client_request_id] = b.manifest_id;
  }
  async submitCharacterBatch(
    cid: string,
    bid: string,
    req: SubmitBatchRequest,
  ) {
    const r = this.getCharacter(cid);
    if (r.requests[req.client_request_id]) return this.characterBatch(cid, bid);
    const b =
      r.batches.find((b) => b.manifest_id === bid) ??
      fail("BATCH_NOT_FOUND", "Batch not found.", 404);
    if (
      b.kind !== "production" ||
      b.approved_spec_revision !== this.approved(r, "s2")?.revision ||
      b.prompt_set_revision !== this.approved(r, "s4")?.revision ||
      this.state(r, configs[3]).approved?.stale
    )
      fail("BATCH_MANIFEST_STALE", "Review S2 and S4 before production.", 409);
    if (b.attempts.length)
      fail("BATCH_ALREADY_SUBMITTED", "This batch was submitted already.", 409);
    await this.run(r, b, req, false);
    this.event(r, "s5", "batch_submitted", null, null, bid);
    return clone(b);
  }
  async retryCharacterBatch(cid: string, bid: string, req: SubmitBatchRequest) {
    const r = this.getCharacter(cid);
    if (r.requests[req.client_request_id]) return this.characterBatch(cid, bid);
    await this.characterBatch(cid, bid);
    const b = r.batches.find((b) => b.manifest_id === bid)!;
    if (b.status === "submitted")
      fail("BATCH_ATTEMPT_RUNNING", "Wait for the running attempt.", 409);
    await this.run(r, b, req, true);
    this.event(r, "s5", "batch_retried", null, null, bid);
    return clone(b);
  }
}
