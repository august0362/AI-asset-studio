import { beforeEach, describe, expect, it, vi } from "vitest";
import { MockApiClient } from "./MockApiClient";
import { HttpApiClient } from "./HttpApiClient";
import { sharedCharacterFixture as fixture } from "./characterFixtures";

beforeEach(() => localStorage.clear());
describe("character deletion", () => {
  it("accepts HTTP 204 without reading a body", async () => {
    const json = vi.fn();
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, status: 204, json } as unknown as Response);
    await expect(new HttpApiClient("/api/v1").deleteCharacter("chr_012345abcdef")).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith("/api/v1/characters/chr_012345abcdef", expect.objectContaining({ method: "DELETE", body: undefined }));
    expect(json).not.toHaveBeenCalled();
  });
  it.each([404, 409])("preserves the v1.1 HTTP %s envelope and manifest IDs", async (status) => {
    const code = status === 404 ? "CHARACTER_NOT_FOUND" : "BATCH_ATTEMPT_RUNNING";
    const response = { contract_version: "1.1", errors: [{ code, message: "Cannot delete.", severity: "error", field: null, details: { manifest_ids: ["bat_012345abcdef"] }, retryable: false }], warnings: [] };
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, status, json: async () => response } as Response);
    await expect(new HttpApiClient("/api/v1").deleteCharacter("chr_012345abcdef")).rejects.toMatchObject({ status, response });
  });
  it("removes a fixture character permanently across instances and preserves batch jobs", async () => {
    const api = new MockApiClient(), c = fixture("character"), job = fixture("job_batch_partial");
    await api.deleteCharacter(c.character_id);
    const reloaded = new MockApiClient();
    expect((await reloaded.characters()).characters.some((r) => r.character_id === c.character_id)).toBe(false);
    for (const read of [
      () => reloaded.character(c.character_id),
      () => reloaded.stage(c.character_id, "s1"),
      () => reloaded.characterHistory(c.character_id),
      () => reloaded.characterOutputs(c.character_id),
      () => reloaded.stageRevision(c.character_id, "s1", 1),
      () => reloaded.assetContent(c.character_id, "ast_012345abcdef"),
      () => reloaded.referenceContent(c.character_id, "ref_012345abcdef"),
      () => reloaded.characterBatch(c.character_id, "bat_012345abcdef"),
      () => reloaded.deleteCharacter(c.character_id),
    ]) await expect(read()).rejects.toMatchObject({ status: 404, response: { contract_version: "1.1", errors: [expect.objectContaining({ code: "CHARACTER_NOT_FOUND" })] } });
    expect(await reloaded.job(job.job_id)).toEqual(job);
  });
  it("refuses a running fixture attempt, reports manifests and leaves everything intact", async () => {
    const api = new MockApiClient(), c = fixture("character"), batch = fixture("batch_manifest_submitted");
    api.setCharacterBatchScenario("submitted");
    await expect(api.deleteCharacter(c.character_id)).rejects.toMatchObject({ status: 409, response: { contract_version: "1.1", errors: [expect.objectContaining({ code: "BATCH_ATTEMPT_RUNNING", details: { manifest_ids: [batch.manifest_id] } })] } });
    expect((await api.character(c.character_id)).character).toEqual(c);
    expect((await api.characters()).characters.some((r) => r.character_id === c.character_id)).toBe(true);
  });
  it("allows deletion of a ready manifest with pending tasks but no attempt", async () => {
    const api = new MockApiClient(), c = fixture("character");
    api.setCharacterBatchScenario("ready");
    await expect(api.deleteCharacter(c.character_id)).resolves.toBeUndefined();
  });
  it("deletes a newly created character even when storage writes fail", async () => {
    const api = new MockApiClient();
    const c = await api.createCharacter({ contract_version: "1.1", client_request_id: crypto.randomUUID(), name: "Local" });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("Storage blocked"); });
    await expect(api.deleteCharacter(c.character_id)).resolves.toBeUndefined();
    await expect(api.character(c.character_id)).rejects.toMatchObject({ status: 404 });
    expect((await api.characters()).characters.some((r) => r.character_id === c.character_id)).toBe(false);
  });
  it("reports every running manifest without removing local drafts or references", async () => {
    const api = new MockApiClient();
    const c = await api.createCharacter({ contract_version: "1.1", client_request_id: crypto.randomUUID(), name: "Local batches" });
    const records = JSON.parse(localStorage.getItem("aas.characters.demo.v1")!);
    const batch = fixture("batch_manifest_submitted");
    const ids = ["bat_111111111111", "bat_222222222222"];
    records[c.character_id].batches = ids.map((manifest_id) => ({ ...batch, manifest_id, character_id: c.character_id }));
    localStorage.setItem("aas.characters.demo.v1", JSON.stringify(records));
    const before = localStorage.getItem("aas.characters.demo.v1");
    await expect(new MockApiClient().deleteCharacter(c.character_id)).rejects.toMatchObject({ status: 409, response: { errors: [expect.objectContaining({ code: "BATCH_ATTEMPT_RUNNING", details: { manifest_ids: ids } })] } });
    expect(localStorage.getItem("aas.characters.demo.v1")).toBe(before);
  });
  it("does not restore deleted records when a previously open client saves another character", async () => {
    const first = new MockApiClient();
    const c = await first.createCharacter({ contract_version: "1.1", client_request_id: crypto.randomUUID(), name: "Delete in another tab" });
    const otherTab = new MockApiClient();
    await first.deleteCharacter(c.character_id);
    await otherTab.createCharacter({ contract_version: "1.1", client_request_id: crypto.randomUUID(), name: "Keep" });
    const stored = JSON.parse(localStorage.getItem("aas.characters.demo.v1")!);
    expect(stored).not.toHaveProperty(c.character_id);
  });
});
