import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { MockApiClient } from "./MockApiClient";
import { HttpApiClient } from "./HttpApiClient";
import { emptyContent } from "./MockCharacterApi";
import type {
  CharacterApi,
  StageContent,
  StageId,
  StageConfig,
  SubmitBatchRequest,
} from "./characterTypes";
import configs from "../../tests/fixtures/contracts/v2/stage-configs.json";
import { charactersEn } from "../i18n/characters.en";
import { charactersVi } from "../i18n/characters.vi";
const create = () => ({
  contract_version: "1.1",
  client_request_id: crypto.randomUUID(),
  name: "Demo character",
  tags: ["fantasy"],
});
const batchRequest = (): SubmitBatchRequest => ({
  contract_version: "1.1",
  client_request_id: crypto.randomUUID(),
  compute: { profile_id: "default", accelerator_id: "auto" },
});
const cid = "chr_012345abcdef",
  bid = "bat_012345abcdef";
beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());
describe("V2 HTTP transport uses the approved 19 routes", () => {
  const save = {
    contract_version: "1.1",
    expected_draft_version: 0,
    content: emptyContent("s1"),
    checklist: { items: [] },
  };
  const cases: [
    string,
    string,
    (api: CharacterApi) => Promise<unknown>,
    unknown?,
    boolean?,
  ][] = [
    [
      "GET",
      "/characters?q=Demo&stage=s2&status=draft&limit=10&cursor=next",
      (a) =>
        a.characters({
          q: "Demo",
          stage: "s2",
          status: "draft",
          limit: 10,
          cursor: "next",
        }),
    ],
    [
      "POST",
      "/characters",
      (a) =>
        a.createCharacter({
          contract_version: "1.1",
          client_request_id: "request-id",
          name: "Original name",
        }),
      {
        contract_version: "1.1",
        client_request_id: "request-id",
        name: "Original name",
      },
    ],
    ["GET", `/characters/${cid}`, (a) => a.character(cid)],
    ["DELETE", `/characters/${cid}`, (a) => a.deleteCharacter(cid)],
    [
      "PATCH",
      `/characters/${cid}`,
      (a) =>
        a.updateCharacter(cid, {
          contract_version: "1.1",
          expected_version: 4,
          name: "New name",
        }),
      { contract_version: "1.1", expected_version: 4, name: "New name" },
    ],
    ["GET", `/characters/${cid}/stages/s3`, (a) => a.stage(cid, "s3")],
    [
      "PUT",
      `/characters/${cid}/stages/s1/draft`,
      (a) => a.saveStage(cid, "s1", save),
      save,
    ],
    [
      "POST",
      `/characters/${cid}/stages/s1/decisions`,
      (a) =>
        a.decideStage(cid, "s1", {
          contract_version: "1.1",
          expected_draft_version: 3,
          action: "approve",
          revision: 2,
        }),
      {
        contract_version: "1.1",
        expected_draft_version: 3,
        action: "approve",
        revision: 2,
      },
    ],
    [
      "GET",
      `/characters/${cid}/stages/s2/revisions/2`,
      (a) => a.stageRevision(cid, "s2", 2),
    ],
    [
      "GET",
      `/characters/${cid}/history?limit=30&cursor=x`,
      (a) => a.characterHistory(cid, 30, "x"),
    ],
    [
      "POST",
      `/characters/${cid}/references`,
      (a) =>
        a.createReference(cid, {
          contract_version: "1.1",
          client_request_id: "id",
          kind: "url",
          purpose: "moodboard",
          title: "Board",
          url: "https://example.com",
        }),
      {
        contract_version: "1.1",
        client_request_id: "id",
        kind: "url",
        purpose: "moodboard",
        title: "Board",
        url: "https://example.com",
      },
    ],
    [
      "GET",
      `/characters/${cid}/references/ref_012345abcdef/content`,
      (a) => a.referenceContent(cid, "ref_012345abcdef"),
      undefined,
      true,
    ],
    [
      "DELETE",
      `/characters/${cid}/references/ref_012345abcdef`,
      (a) => a.deleteReference(cid, "ref_012345abcdef"),
    ],
    ["GET", `/characters/${cid}/outputs`, (a) => a.characterOutputs(cid)],
    [
      "GET",
      `/characters/${cid}/assets/ast_012345abcdef/content?download=1`,
      (a) => a.assetContent(cid, "ast_012345abcdef", true),
      undefined,
      true,
    ],
    [
      "POST",
      `/characters/${cid}/batches`,
      (a) =>
        a.createPreviewBatch(cid, {
          ...batchRequest(),
          client_request_id: "id",
          kind: "preview",
        }),
      {
        contract_version: "1.1",
        client_request_id: "id",
        kind: "preview",
        compute: { profile_id: "default", accelerator_id: "auto" },
      },
    ],
    [
      "GET",
      `/characters/${cid}/batches/${bid}`,
      (a) => a.characterBatch(cid, bid),
    ],
    [
      "POST",
      `/characters/${cid}/batches/${bid}/submit`,
      (a) =>
        a.submitCharacterBatch(cid, bid, {
          ...batchRequest(),
          client_request_id: "id",
        }),
      {
        contract_version: "1.1",
        client_request_id: "id",
        compute: { profile_id: "default", accelerator_id: "auto" },
      },
    ],
    [
      "POST",
      `/characters/${cid}/batches/${bid}/retry`,
      (a) =>
        a.retryCharacterBatch(cid, bid, {
          ...batchRequest(),
          client_request_id: "id",
        }),
      {
        contract_version: "1.1",
        client_request_id: "id",
        compute: { profile_id: "default", accelerator_id: "auto" },
      },
    ],
  ];
  it.each(cases)("%s %s", async (method, path, call, body, bytes) => {
    const blob = new Blob(["png"], { type: "image/png" });
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: method === "DELETE" ? 204 : 200,
      json: async () => ({ contract_version: "1.1" }),
      blob: async () => blob,
    });
    vi.stubGlobal("fetch", fetch);
    const value = await call(new HttpApiClient("/api/v1"));
    expect(fetch).toHaveBeenCalledWith(
      `/api/v1${path}`,
      expect.objectContaining({ method }),
    );
    if (body !== undefined)
      expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(body);
    else expect(fetch.mock.calls[0][1].body).toBeUndefined();
    if (bytes) expect(value).toBe(blob);
  });
  it("surfaces 409 errors without retrying or switching to DEMO", async () => {
    const response = {
      contract_version: "1.1",
      errors: [
        {
          code: "STAGE_DRAFT_CONFLICT",
          message: "Conflict",
          severity: "error",
          field: null,
          details: { current_draft_version: 8 },
          retryable: false,
        },
      ],
      warnings: [],
    };
    const fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => response,
    });
    vi.stubGlobal("fetch", fetch);
    await expect(
      new HttpApiClient("/api/v1").saveStage(cid, "s1", save),
    ).rejects.toMatchObject({ status: 409, response });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
describe("V2 DEMO draft, approval and batch lifecycle", () => {
  let time = Date.now();
  const setup = async () => {
    const api = new MockApiClient(1, true, () => time);
    const c = await api.createCharacter(create());
    return { api, id: c.character_id };
  };
  async function approve(
    api: MockApiClient,
    id: string,
    content: StageContent,
  ) {
    const before = await api.stage(id, content.stage_id);
    await api.saveStage(id, content.stage_id, {
      contract_version: "1.1",
      expected_draft_version: before.draft.draft_version,
      content,
      checklist: {
        items: before.config.checklist.map((c) => ({
          item_id: c.item_id,
          checked: true,
          note: null,
        })),
      },
    });
    const review = await api.decideStage(id, content.stage_id, {
      contract_version: "1.1",
      expected_draft_version: before.draft.draft_version + 1,
      action: "submit",
    });
    return api.decideStage(id, content.stage_id, {
      contract_version: "1.1",
      expected_draft_version: review.draft.draft_version,
      action: "approve",
      revision: review.state.pending_revision,
    });
  }
  const s1: StageContent = {
    stage_id: "s1",
    idea: "Moonlit ranger",
    directions: ["Fantasy character"],
    notes: null,
    palette: [],
    references: [],
  };
  const s2: StageContent = {
    stage_id: "s2",
    summary: null,
    attributes: [
      {
        attribute_id: "hair",
        group: "hair",
        label: "Hair",
        value: "Silver",
        lock: "locked",
        reference_ids: [],
      },
    ],
    answers: [],
    open_questions: [],
    rejection_criteria: [],
  };
  function fixtureBlob() {
    const bytes = readFileSync("tests/fixtures/artifacts/mock.png");
    const blob = new Blob([bytes], { type: "image/png" });
    Object.defineProperty(blob, "arrayBuffer", {
      value: async () =>
        bytes.buffer.slice(
          bytes.byteOffset,
          bytes.byteOffset + bytes.byteLength,
        ),
    });
    return blob;
  }
  it("creates, searches, filters and renames without changing IDs; survives reload", async () => {
    const { api, id } = await setup();
    expect((await api.characters({ q: "fantasy" })).characters).toHaveLength(1);
    expect((await api.characters({ q: "missing" })).characters).toHaveLength(0);
    expect((await api.characters({ stage: "s2" })).characters).toHaveLength(0);
    const request = {
      contract_version: "1.1",
      expected_version: 1,
      name: "Changed",
    };
    expect(await api.updateCharacter(id, request)).toMatchObject({
      character_id: id,
      name: "Changed",
      version: 2,
    });
    await expect(api.updateCharacter(id, request)).rejects.toMatchObject({
      status: 409,
    });
    expect((await new MockApiClient().character(id)).character.name).toBe(
      "Changed",
    );
  });
  it("rejects stale draft versions from another browser instance without overwriting text", async () => {
    const { api, id } = await setup(),
      other = new MockApiClient();
    const req = {
      contract_version: "1.1",
      expected_draft_version: 0,
      content: s1,
      checklist: { items: [] },
    };
    await api.saveStage(id, "s1", req);
    await expect(
      other.saveStage(id, "s1", {
        ...req,
        content: { ...s1, idea: "old edit" },
      }),
    ).rejects.toMatchObject({
      status: 409,
      response: {
        errors: [
          {
            code: "STAGE_DRAFT_CONFLICT",
            details: { current_draft_version: 1 },
          },
        ],
      },
    });
    expect((await api.stage(id, "s1")).draft.content).toEqual(s1);
  });
  it.each(["s1", "s2", "s3", "s4", "s5", "s6", "s7"] as StageId[])(
    "returns stage-specific content, dependencies and objective for %s",
    async (sid) => {
      const { api, id } = await setup();
      const detail = await api.stage(id, sid);
      expect(detail.config.title_key).toBe(`stage.${sid}.title`);
      expect(detail.config.objective_key).toBe(`stage.${sid}.objective`);
      expect(detail.draft.content.stage_id).toBe(sid);
      expect(detail.inputs.map((i) => i.stage_id)).toEqual(
        configs
          .find((c) => c.stage_id === sid)!
          .dependencies.map((d) => d.stage_id),
      );
    },
  );
  it.each(["s6", "s7"] as StageId[])(
    "keeps %s planned and rejects all writes",
    async (sid) => {
      const { api, id } = await setup();
      expect((await api.stage(id, sid)).state.availability).toBe("planned");
      await expect(
        api.saveStage(id, sid, {
          contract_version: "1.1",
          expected_draft_version: 0,
          content: emptyContent(sid),
          checklist: { items: [] },
        }),
      ).rejects.toMatchObject({
        response: { errors: [{ code: "STAGE_NOT_AVAILABLE" }] },
      });
      await expect(
        api.decideStage(id, sid, {
          contract_version: "1.1",
          expected_draft_version: 0,
          action: "submit",
        }),
      ).rejects.toMatchObject({
        response: { errors: [{ code: "STAGE_NOT_AVAILABLE" }] },
      });
    },
  );
  it("requires manual review and enforces content and checklist blockers", async () => {
    const { api, id } = await setup();
    const d = await api.saveStage(id, "s1", {
      contract_version: "1.1",
      expected_draft_version: 0,
      content: emptyContent("s1"),
      checklist: { items: [] },
    });
    expect(d.state.editorial_status).toBe("draft");
    const review = await api.decideStage(id, "s1", {
      contract_version: "1.1",
      expected_draft_version: 1,
      action: "submit",
    });
    expect(review.state.editorial_status).toBe("in_review");
    await expect(
      api.decideStage(id, "s1", {
        contract_version: "1.1",
        expected_draft_version: 1,
        action: "approve",
        revision: 1,
      }),
    ).rejects.toMatchObject({
      status: 422,
      response: {
        errors: expect.arrayContaining([
          expect.objectContaining({ code: "STAGE_CHECKLIST_INCOMPLETE" }),
          expect.objectContaining({ code: "STAGE_CONTENT_INCOMPLETE" }),
        ]),
      },
    });
  });
  it("stores URLs as text and never fetches remote pages", async () => {
    const { api, id } = await setup(),
      fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const ref = await api.createReference(id, {
      contract_version: "1.1",
      client_request_id: crypto.randomUUID(),
      kind: "url",
      purpose: "moodboard",
      title: "Board",
      url: "https://example.com/board",
    });
    expect(ref.content_url).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    await expect(
      api.createReference(id, {
        contract_version: "1.1",
        client_request_id: crypto.randomUUID(),
        kind: "url",
        purpose: "moodboard",
        title: "Bad",
        url: "javascript:alert(1)",
      }),
    ).rejects.toMatchObject({
      response: { errors: [{ code: "REFERENCE_URL_INVALID" }] },
    });
  });
  it("completes S1–S5, freezes selected PNGs, runs one job per batch group and marks downstream revisions stale", async () => {
    const { api, id } = await setup();
    vi.spyOn(api, "artifactContent").mockImplementation(async () =>
      fixtureBlob(),
    );
    await approve(api, id, s1);
    await approve(api, id, s2);
    const job = (
      await api.jobs({ status: "completed", pipeline_type: "text_to_2d" })
    ).jobs[0];
    const s3: StageContent = {
      stage_id: "s3",
      preview_profile: null,
      preview_prompt: null,
      candidates: [
        {
          candidate_id: "cand_01",
          source: "job_artifact",
          manifest_id: null,
          task_id: null,
          job: { job_id: job.job_id, artifact_id: null },
          reference_id: null,
          verdict: "selected",
          matches: ["hair"],
          mismatches: [],
          feedback: null,
        },
      ],
      selected_candidate_id: "cand_01",
      review_notes: null,
    };
    await approve(api, id, s3);
    const purposes = ["full_body", "front", "side", "back"] as const;
    const s4: StageContent = {
      stage_id: "s4",
      entries: purposes.map((p) => ({
        purpose: p,
        canonical_prompt: `${p} original prompt`,
        negative_prompt: null,
        notes: null,
      })),
      production_profile: {
        target_model_id: "mock-t2d-basic",
        compute_target: "kaggle",
        options: {},
      },
      tasks: purposes.map((p, i) => ({
        task_id: `${p}_01`,
        purpose: p,
        prompt: `${p} original prompt`,
        negative_prompt: null,
        seed: i + 1,
        width: 768,
        height: 768,
        options: {},
      })),
      reference_asset_ids: [],
    };
    const approved = await approve(api, id, s4);
    const manifest = approved.batches[0];
    expect(manifest.expected_model_loads).toBe(1);
    expect(manifest.prompt_set_revision).toBe(1);
    const createJob = vi.spyOn(api, "createJob");
    const request = batchRequest();
    const batch = await api.submitCharacterBatch(
      id,
      manifest.manifest_id,
      request,
    );
    await api.submitCharacterBatch(id, manifest.manifest_id, request);
    expect(createJob).toHaveBeenCalledTimes(1);
    expect(batch.attempts[0].task_ids).toHaveLength(4);
    await api.characterBatch(id, batch.manifest_id);
    time += 100;
    const done = await api.characterBatch(id, batch.manifest_id);
    expect(done.status).toBe("completed");
    expect(done.results.every((r) => r.status === "succeeded")).toBe(true);
    const resultJob = await api.job(done.attempts[0].job_id);
    expect(resultJob.artifacts.map((a) => a.task_id)).toEqual(
      s4.tasks.map((t) => t.task_id),
    );
    expect(resultJob.request.prompt).toBeNull();
    await expect(
      api.retryJob(resultJob.job_id, crypto.randomUUID()),
    ).rejects.toMatchObject({
      response: { errors: [{ code: "JOB_NOT_RETRYABLE" }] },
    });
    await approve(api, id, {
      stage_id: "s5",
      items: done.tasks.map((t, i) => ({
        item_id: `item_${String(i + 1).padStart(3, "0")}`,
        purpose: t.purpose,
        manifest_id: done.manifest_id,
        task_id: t.task_id,
        job: null,
        selected: true,
        note: null,
      })),
      consistency_notes: "Manually reviewed",
    });
    const outputs = await api.characterOutputs(id);
    expect(outputs.outputs).toHaveLength(5);
    expect(
      outputs.outputs
        .filter((a) => a.frozen_in.stage_id === "s5")
        .map((a) => a.source?.prompt),
    ).toEqual(s4.tasks.map((t) => t.prompt));
    await api.deleteJob(resultJob.job_id);
    expect((await api.characterOutputs(id)).outputs).toHaveLength(5);
    expect(
      (await api.assetContent(id, outputs.outputs[1].asset_id)).size,
    ).toBeGreaterThan(0);
    await approve(api, id, { ...s2, summary: "Updated spec" });
    const workflow = await api.character(id);
    for (const sid of ["s3", "s4", "s5"])
      expect(
        workflow.stages.find((s) => s.config.stage_id === sid)?.state
          .editorial_status,
      ).toBe("needs_revision");
    await expect(
      api.submitCharacterBatch(id, manifest.manifest_id, batchRequest()),
    ).rejects.toMatchObject({
      response: { errors: [{ code: "BATCH_MANIFEST_STALE" }] },
    });
  });
  it("retries only unfinished preview tasks and keeps successful artifacts", async () => {
    const { api, id } = await setup();
    await approve(api, id, s1);
    await approve(api, id, s2);
    await api.saveStage(id, "s3", {
      contract_version: "1.1",
      expected_draft_version: 0,
      content: {
        stage_id: "s3",
        preview_profile: {
          model_id: "mock-t2d-basic",
          compute_target: "kaggle",
          variations: 3,
          width: 768,
          height: 768,
          options: {},
        },
        preview_prompt: "Demo preview",
        candidates: [],
        selected_candidate_id: null,
        review_notes: null,
      },
      checklist: { items: [] },
    });
    const batch = await api.createPreviewBatch(id, {
      ...batchRequest(),
      kind: "preview",
    });
    await api.characterBatch(id, batch.manifest_id);
    time += 100;
    const job = await api.job(batch.attempts[0].job_id);
    const partial = {
      ...job,
      artifacts: job.artifacts.slice(0, 2),
      warnings: [
        {
          code: "BATCH_PARTIAL" as const,
          severity: "warning" as const,
          field: null,
          message: "Demo partial result",
          details: { failed: [], not_run: ["preview_03"] },
          retryable: false,
        },
      ],
    };
    const read = vi.spyOn(api, "job").mockResolvedValue(partial);
    const reconciled = await api.characterBatch(id, batch.manifest_id);
    expect(reconciled.status).toBe("partially_completed");
    expect(reconciled.results.map((r) => r.status)).toEqual([
      "succeeded",
      "succeeded",
      "not_run",
    ]);
    expect(reconciled.retryable_task_ids).toEqual(["preview_03"]);
    read.mockRestore();
    const retried = await api.retryCharacterBatch(
      id,
      batch.manifest_id,
      batchRequest(),
    );
    expect(retried.attempts[1].task_ids).toEqual(["preview_03"]);
    expect(retried.results.slice(0, 2)).toEqual(reconciled.results.slice(0, 2));
    await api.characterBatch(id, batch.manifest_id);
    time += 100;
    expect((await api.characterBatch(id, batch.manifest_id)).status).toBe(
      "completed",
    );
  });
  it("handles unavailable browser storage with real in-memory demo state", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    const { api, id } = await setup();
    expect((await api.character(id)).character.character_id).toBe(id);
  });
});
describe("approved V2 fixture and dictionary parity", () => {
  it("mirrors all seven approved dependency rows and glossary keys", () => {
    const typed: StageConfig[] = configs as StageConfig[];
    expect(typed.map((c) => c.stage_id)).toEqual([
      "s1",
      "s2",
      "s3",
      "s4",
      "s5",
      "s6",
      "s7",
    ]);
    const doc = readFileSync("../../docs/v2/CHARACTER_WORKFLOW.md", "utf8");
    for (const c of typed) {
      const section = doc
        .split(`### ${c.stage_id.toUpperCase()} — `)[1]
        .split("\n### ")[0];
      const row = section.match(
        /\| (?:Future checklist|Checklist) \| (.*?) \|/,
      )![1];
      for (const item of c.checklist) {
        expect(row).toContain("`" + item.item_id + "`");
        expect(charactersEn).toHaveProperty(item.label_key);
        expect(charactersVi).toHaveProperty(item.label_key);
      }
      for (const question of c.guided_questions) {
        expect(charactersEn).toHaveProperty(question.label_key);
        expect(charactersVi).toHaveProperty(question.label_key);
      }
    }
    expect(Object.keys(charactersEn).sort()).toEqual(
      Object.keys(charactersVi).sort(),
    );
  });
});
