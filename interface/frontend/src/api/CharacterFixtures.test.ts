import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";
import { MockApiClient } from "./MockApiClient";
import { HttpApiClient } from "./HttpApiClient";
import {
  sharedCharacterFixture as fixture,
  sharedCharacterFixtureNames,
  sharedCharacterContent,
} from "./characterFixtures";
import type { ArtifactView, ErrorResponse, GenerationResult } from "./types";
import { isStoredManifest } from "../features/characters/BatchPanel";
const directory = "tests/fixtures/contracts/v2";
const imageIndex = JSON.parse(
  readFileSync(resolve(directory, "files/index.json"), "utf8"),
) as Record<
  string,
  { file: string; mime_type: string; size_bytes: number; sha256: string }
>;
function fileNames(root: string): string[] {
  return readdirSync(root, { withFileTypes: true })
    .flatMap((entry) =>
      entry.isDirectory()
        ? fileNames(resolve(root, entry.name)).map(
            (name) => `${entry.name}/${name}`,
          )
        : [entry.name],
    )
    .sort();
}
beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());
describe("backend-validated V2 fixtures", () => {
  it("copies exactly the shared JSON files and keeps only the mapped stage-configs extra", () => {
    const backend = resolve("../../tests/fixtures/contracts/v2");
    const names = readdirSync(backend)
      .filter((n) => n.endsWith(".json"))
      .sort();
    expect(names).toHaveLength(32);
    expect(sharedCharacterFixtureNames.map((n) => `${n}.json`).sort()).toEqual(
      names,
    );
    expect(
      readdirSync(directory)
        .filter((n) => n.endsWith(".json"))
        .sort(),
    ).toEqual([...names, "stage-configs.json"].sort());
    for (const name of names)
      expect(readFileSync(resolve(directory, name))).toEqual(
        readFileSync(resolve(backend, name)),
      );
  });
  it("copies every indexed image byte-for-byte and verifies its checksum", () => {
    expect(readFileSync(resolve(directory, "files/index.json"))).toEqual(
      readFileSync(
        resolve("../../tests/fixtures/contracts/v2/files/index.json"),
      ),
    );
    expect(fileNames(resolve(directory, "files"))).toEqual(
      [
        ...new Set(Object.values(imageIndex).map((entry) => entry.file)),
        "index.json",
      ].sort(),
    );
    const index = JSON.parse(
      readFileSync(resolve(directory, "files/index.json"), "utf8"),
    ) as Record<string, { file: string; size_bytes: number; sha256: string }>;
    expect(Object.keys(index).length).toBeGreaterThan(0);
    for (const entry of Object.values(index)) {
      const bytes = readFileSync(resolve(directory, "files", entry.file));
      expect(bytes).toEqual(
        readFileSync(
          resolve("../../tests/fixtures/contracts/v2/files", entry.file),
        ),
      );
      expect(bytes.length).toBe(entry.size_bytes);
      expect(createHash("sha256").update(bytes).digest("hex")).toBe(
        entry.sha256,
      );
    }
  });
  it.each(Object.entries(imageIndex))(
    "serves matching indexed bytes for %s",
    async (url, entry) => {
      const bytes = readFileSync(resolve(directory, "files", entry.file));
      const fetch = vi
        .fn()
        .mockResolvedValue({ ok: true, blob: async () => new Blob([bytes]) });
      vi.stubGlobal("fetch", fetch);
      const api = new MockApiClient();
      const parts = url.split("/");
      const blob =
        parts[3] === "jobs"
          ? await api.artifactContent(parts[4], parts[6])
          : parts[5] === "references"
            ? await api.referenceContent(parts[4], parts[6])
            : await api.assetContent(parts[4], parts[6]);
      const loaded = await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as ArrayBuffer);
        reader.onerror = reject;
        reader.readAsArrayBuffer(blob);
      });
      expect(blob.type).toBe(entry.mime_type);
      expect(blob.size).toBe(entry.size_bytes);
      expect(
        createHash("sha256").update(Buffer.from(loaded)).digest("hex"),
      ).toBe(entry.sha256);
      expect(fetch).toHaveBeenCalledOnce();
      expect(fetch.mock.calls[0][0]).not.toContain("/api/v1/");
    },
  );
  it("returns the exact status of every shared batch attempt job", async () => {
    const api = new MockApiClient();
    for (const job of fixture("batch_jobs")) {
      expect(await api.jobStatus(job.job_id)).toEqual({
        job_id: job.job_id,
        status: job.status,
        updated_at: job.updated_at,
        progress: null,
      });
    }
  });
  it.each(["artifact", "reference", "asset", "index"] as const)(
    "rejects an unindexed %s URL with 404 ARTIFACT_NOT_FOUND without fetching placeholders",
    async (kind) => {
      const api = new MockApiClient(),
        fetch = vi.fn();
      vi.stubGlobal("fetch", fetch);
      const cid = fixture("character").character_id;
      const result =
        kind === "artifact"
          ? api.artifactContent(
              fixture("job_batch_partial").job_id,
              "art_missing",
            )
          : kind === "reference"
            ? api.referenceContent(cid, "ref_missing")
            : kind === "asset"
              ? api.assetContent(cid, "ast_missing")
              : sharedCharacterContent(
                  "/api/v1/jobs/job_missing/artifacts/art_missing/content",
                );
      await expect(result).rejects.toMatchObject({
        status: 404,
        response: { errors: [{ code: "ARTIFACT_NOT_FOUND" }] },
      });
      expect(fetch).not.toHaveBeenCalled();
    },
  );
  it("returns 404 ARTIFACT_NOT_FOUND if an indexed binary is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 }),
    );
    await expect(
      sharedCharacterContent(Object.keys(imageIndex)[0]),
    ).rejects.toMatchObject({
      status: 404,
      response: { errors: [{ code: "ARTIFACT_NOT_FOUND" }] },
    });
  });
  it.each(sharedCharacterFixtureNames)(
    "serves the exact %s snapshot without mutable aliases",
    (name) => {
      const api = new MockApiClient(100, false);
      const result = api.characterFixture(name);
      const expected = JSON.parse(
        readFileSync(resolve(directory, `${name}.json`), "utf8"),
      );
      expect(result).toEqual(expected);
      Object.assign(result, { contract_version: "changed" });
      expect(api.characterFixture(name)).toEqual(expected);
    },
  );
  it("serves shared character list, workflows, every complete stage and the in-review variant", async () => {
    const api = new MockApiClient();
    expect(await api.characters()).toEqual(fixture("character_list"));
    const workflow = fixture("character_workflow"),
      pending = fixture("character_workflow_in_progress");
    expect(await api.character(workflow.character.character_id)).toEqual(
      workflow,
    );
    expect(await api.character(pending.character.character_id)).toEqual(
      pending,
    );
    for (const stage of workflow.stages) {
      expect(
        await api.stage(workflow.character.character_id, stage.config.stage_id),
      ).toEqual(fixture(`stage_detail_${stage.config.stage_id}`));
    }
    expect(await api.stage(pending.character.character_id, "s4")).toEqual(
      fixture("stage_detail_s4_in_review"),
    );
    expect(await api.characterHistory(workflow.character.character_id)).toEqual(
      fixture("history_page"),
    );
    expect(await api.characterOutputs(workflow.character.character_id)).toEqual(
      fixture("outputs"),
    );
    expect(
      await api.stageRevision(workflow.character.character_id, "s5", 1),
    ).toEqual(fixture("stage_revision_s5"));
  });
  it.each([
    "ready",
    "submitted",
    "completed",
    "partially_completed",
    "failed",
  ] as const)("serves the shared %s batch scenario", async (status) => {
    const api = new MockApiClient(),
      batch = fixture(`batch_manifest_${status}`);
    api.setCharacterBatchScenario(status);
    expect(
      await api.characterBatch(batch.character_id, batch.manifest_id),
    ).toEqual(batch);
  });
  it("keeps shared job fields including nullable batch/task IDs and loads matching image bytes", async () => {
    const api = new MockApiClient(),
      job = fixture("job_batch_partial");
    const typed: GenerationResult = job;
    const artifact: ArtifactView = typed.artifacts[0];
    expect(artifact.task_id).toBe("fullbody_01");
    expect(typed.request.batch?.task_ids).toContain(artifact.task_id);
    expect(await api.job(job.job_id)).toEqual(job);
    const bytes = readFileSync(
      resolve(
        directory,
        "files",
        "jobs",
        job.job_id,
        "artifacts",
        `${artifact.artifact_id}.png`,
      ),
    );
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob([bytes], { type: "image/png" }),
    });
    vi.stubGlobal("fetch", fetch);
    expect(
      (await api.artifactContent(job.job_id, artifact.artifact_id)).size,
    ).toBe(artifact.size_bytes);
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).not.toContain("/api/v1/");
    for (const batchJob of fixture("batch_jobs"))
      expect(await api.job(batchJob.job_id)).toEqual(batchJob);
    const plain: ArtifactView = { ...artifact, task_id: null };
    const noBatch: GenerationResult = {
      ...typed,
      request: { ...typed.request, batch: null },
    };
    expect(plain.task_id).toBeNull();
    expect(noBatch.request.batch).toBeNull();
  });
  it("never treats a manifest preview as stored or requestable", async () => {
    const api = new MockApiClient(),
      detail = fixture("stage_detail_s4"),
      preview = detail.manifest_preview!;
    expect(preview.manifest_id).toBe("bat_000000000000");
    expect(isStoredManifest(preview)).toBe(false);
    expect(detail.batches.every(isStoredManifest)).toBe(true);
    await expect(
      api.characterBatch(detail.character.character_id, preview.manifest_id),
    ).rejects.toMatchObject({
      status: 404,
      response: {
        contract_version: "1.1",
        errors: [{ code: "BATCH_NOT_FOUND" }],
      },
    });
  });
  it.each(["1.0", "1.1"] as const)(
    "accepts %s character error envelopes without losing code or details",
    async (version) => {
      const body: ErrorResponse = {
        ...fixture("error_approval_blocked"),
        contract_version: version,
      };
      const fetch = vi
        .fn()
        .mockResolvedValue({ ok: false, status: 422, json: async () => body });
      vi.stubGlobal("fetch", fetch);
      await expect(
        new HttpApiClient("/api/v1").decideStage(
          fixture("character").character_id,
          "s4",
          {
            contract_version: "1.1",
            action: "approve",
            expected_draft_version: 1,
            revision: 1,
          },
        ),
      ).rejects.toMatchObject({ status: 422, response: body });
      expect(fetch).toHaveBeenCalledTimes(1);
    },
  );
  it("keeps saves of a shared complete character interactive after loading the snapshot", async () => {
    const api = new MockApiClient(),
      id = fixture("character").character_id;
    const detail = await api.stage(id, "s1");
    const content = {
      ...detail.draft.content,
      ...(detail.draft.content.stage_id === "s1"
        ? { idea: "Edited from shared snapshot" }
        : {}),
    };
    await api.saveStage(id, "s1", {
      contract_version: "1.1",
      expected_draft_version: detail.draft.draft_version,
      content,
      checklist: detail.draft.checklist,
    });
    expect((await api.stage(id, "s1")).draft).toMatchObject({
      draft_version: detail.draft.draft_version + 1,
      content: { idea: "Edited from shared snapshot" },
    });
  });
});
