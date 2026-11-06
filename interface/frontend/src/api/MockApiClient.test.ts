import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MockApiClient } from "./MockApiClient";
import { HttpApiClient } from "./HttpApiClient";
import { api } from "./client";
import type { CreateJobRequest } from "./types";
import { scenarios } from "./types";
import metadata from "../../tests/fixtures/contracts/artifact-metadata.json";

function textRequest(): CreateJobRequest {
  return {
    contract_version: "1.0",
    client_request_id: crypto.randomUUID(),
    pipeline_type: "text_to_2d",
    asset_category: "character",
    model_id: "mock-t2d-basic",
    prompt: "Cyan box concept",
    inputs: [],
    options: {},
    output_format: "png",
    compute: { profile_id: "default", accelerator_id: null },
  };
}
describe("mock API lifecycle", () => {
  it("D-020: artifact responses wrap full artifacts and job details keep a full resource plan", async () => {
    const client = new MockApiClient();
    const summary = (await client.jobs({ status: "completed" })).jobs[0];
    const job = await client.job(summary.job_id);
    const response = await client.artifacts(job.job_id);
    expect(response).toEqual({
      contract_version: "1.0",
      artifacts: job.artifacts,
    });
    expect(summary.primary_artifact).toEqual(
      job.artifacts.find((a) => a.is_primary),
    );
    expect(job.compute.resource_plan).toMatchObject({
      contract_version: "1.0",
      profile_id: "default",
      selection: "recommended",
      estimate_basis: { safety_factor: 1.5, overhead_seconds: 600 },
      candidates: expect.any(Array),
      warnings: expect.any(Array),
      errors: expect.any(Array),
    });
    const created = await client.createJob(textRequest());
    expect(created.compute.resource_plan).toEqual(
      (await client.validate(textRequest())).resource_plan,
    );
    expect((await client.profiles()).profiles[0].mode).toBe("mock");
  });
  it("D-020: GET upload metadata returns the UploadRecord independently of its bytes", async () => {
    const client = new MockApiClient();
    const record = await client.uploadRecord(`upl_${"a".repeat(32)}`);
    expect(record).toMatchObject({
      contract_version: "1.0",
      filename: "mock.png",
      mime_type: "image/png",
      width: 768,
      height: 768,
    });
    record.filename = "changed locally";
    expect((await client.uploadRecord(record.upload_id)).filename).toBe(
      "mock.png",
    );
  });
  it("defaults to the mock client", () => {
    expect(api).toBeInstanceOf(MockApiClient);
  });
  it("creates, advances, logs, retrieves and deletes a text job without remote calls", async () => {
    let now = Date.now();
    const client = new MockApiClient(100, false, () => now),
      req = textRequest();
    const j = await client.createJob(req);
    expect(j.status).toBe("created");
    expect(j.job_id).toMatch(/^job_\d{8}T\d{6}Z_[0-9a-f]{6}$/);
    expect(j.request.options.width).toBe(1024);
    expect((await client.createJob(req)).job_id).toBe(j.job_id);
    await client.jobStatus(j.job_id);
    for (const expected of ["queued", "running", "downloading", "completed"]) {
      now += 100;
      expect((await client.jobStatus(j.job_id)).status).toBe(expected);
    }
    const done = await client.job(j.job_id);
    expect(done.status_history.map((h) => h.status)).toEqual([
      "created",
      "queued",
      "running",
      "downloading",
      "completed",
    ]);
    expect(done.artifacts[0].sha256).toBe(metadata.png.sha256);
    expect(done.artifacts.filter((a) => a.is_primary)).toHaveLength(1);
    expect((await client.jobStatus(j.job_id)).progress).toBeNull();
    expect((await client.logs(j.job_id)).lines).toHaveLength(5);
    expect((await client.logs(j.job_id, 2, 1)).next_offset).toBe(3);
    await client.deleteJob(j.job_id);
    await expect(client.job(j.job_id)).rejects.toMatchObject({ status: 404 });
  });
  it("image jobs include uploading and profiles execute one job at a time", async () => {
    let now = Date.now();
    const client = new MockApiClient(100, true, () => now),
      r: CreateJobRequest = {
        ...textRequest(),
        pipeline_type: "image_to_3d",
        model_id: "mock-i3d-single",
        prompt: null,
        output_format: "glb",
        inputs: [{ upload_id: `upl_${"a".repeat(32)}`, role: "front" }],
      };
    const one = await client.createJob(r),
      two = await client.createJob({
        ...r,
        client_request_id: crypto.randomUUID(),
      });
    await client.jobs();
    now += 100;
    expect((await client.job(one.job_id)).status).toBe("uploading");
    expect((await client.job(two.job_id)).status).toBe("created");
    now += 400;
    expect((await client.job(one.job_id)).status).toBe("completed");
    expect((await client.job(two.job_id)).status).toBe("created");
    now += 500;
    expect((await client.job(two.job_id)).status).toBe("completed");
    const done = await client.job(one.job_id);
    expect(done.artifacts[0].format).toBe("glb");
    expect(done.preview?.artifact_id).toBe("art_02");
  });
  it("rejects invalid creation, unsafe retries and active deletion", async () => {
    const client = new MockApiClient(100, false),
      r = textRequest();
    r.prompt = "";
    await expect(client.createJob(r)).rejects.toMatchObject({
      response: { errors: [{ code: "MODEL_PROMPT_REQUIRED" }] },
    });
    expect((await client.jobs()).jobs).toHaveLength(0);
    r.prompt = "Valid prompt";
    const j = await client.createJob(r);
    await expect(
      client.retryJob(j.job_id, crypto.randomUUID()),
    ).rejects.toMatchObject({ status: 409 });
    await expect(client.deleteJob(j.job_id)).rejects.toMatchObject({
      response: { errors: [{ code: "JOB_NOT_TERMINAL" }] },
    });
  });
  it("user retry creates a different job and retains the failed record", async () => {
    const client = new MockApiClient();
    const failed = (await client.jobs({ status: "failed" })).jobs[0];
    const retried = await client.retryJob(failed.job_id, crypto.randomUUID());
    expect(retried.job_id).not.toBe(failed.job_id);
    expect(retried.execution.retry_of).toBe(failed.job_id);
    expect((await client.job(failed.job_id)).status).toBe("failed");
  });
  it("serves every scenario and pages history newest first", async () => {
    const client = new MockApiClient();
    for (const s of scenarios) {
      client.setScenario(s);
      expect((await client.snapshot("default")).source.quota).toMatch(
        /mock|none/,
      );
    }
    const a = await client.jobs({ limit: 2 });
    expect(a.jobs).toHaveLength(2);
    const b = await client.jobs({ limit: 2, cursor: a.next_cursor! });
    expect(b.jobs[0].created_at < a.jobs[0].created_at).toBe(true);
  });
});
describe("binary fixtures and content transport", () => {
  it("PNG has a valid signature/dimensions; GLB embeds texture and a complete box", () => {
    const png = readFileSync(resolve("tests/fixtures/artifacts/mock.png"));
    expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(png.readUInt32BE(16)).toBe(768);
    const glb = readFileSync(resolve("tests/fixtures/artifacts/mock.glb"));
    expect(glb.subarray(0, 4).toString()).toBe("glTF");
    expect(glb.readUInt32LE(4)).toBe(2);
    expect(glb.readUInt32LE(8)).toBe(glb.length);
    const doc = JSON.parse(
      glb.subarray(20, 20 + glb.readUInt32LE(12)).toString(),
    );
    expect(doc.accessors[3].count).toBe(36);
    expect(doc.images[0].mimeType).toBe("image/png");
    expect(doc.images[0].uri).toBeUndefined();
  });
  it("retrieves real bytes through artifactContent and checks missing artifact IDs", async () => {
    const blob = new Blob(
      [readFileSync(resolve("tests/fixtures/artifacts/mock.glb"))],
      { type: "model/gltf-binary" },
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, blob: async () => blob })),
    );
    const client = new MockApiClient();
    const j = (await client.jobs()).jobs.find(
      (j) => j.primary_artifact?.format === "glb",
    )!;
    expect((await client.artifactContent(j.job_id, "art_01")).size).toBe(
      metadata.glb.size_bytes,
    );
    await expect(
      client.artifactContent(j.job_id, "missing"),
    ).rejects.toMatchObject({
      response: { errors: [{ code: "ARTIFACT_NOT_FOUND" }] },
    });
    vi.unstubAllGlobals();
  });
  it("HTTP shell uses contract paths, multipart uploads and exact request fields", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ contract_version: "1.0" }),
      blob: async () => new Blob(),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new HttpApiClient("/api/v1"),
      req = textRequest();
    await client.createJob(req);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/jobs",
      expect.objectContaining({ method: "POST", body: JSON.stringify(req) }),
    );
    await client.upload(new File(["a"], "a.png"));
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/uploads",
      expect.objectContaining({ body: expect.any(FormData) }),
    );
    await client.artifactContent("job_id", "art_01");
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/jobs/job_id/artifacts/art_01/content?download=1",
    );
    vi.unstubAllGlobals();
  });
});
