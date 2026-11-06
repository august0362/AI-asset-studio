import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpApiClient } from "./HttpApiClient";
import { MockApiClient } from "./MockApiClient";
import { issue } from "./errors";
import type { CreateJobRequest, ErrorCode, ValidationReport } from "./types";

afterEach(() => vi.unstubAllGlobals());
function respond(body: unknown, status = 200) {
  const fetchMock = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => structuredClone(body),
  }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
describe("D-020 HTTP transport", () => {
  it("reads the versioned artifact-list wrapper with full artifacts", async () => {
    const mock = new MockApiClient(),
      summary = (await mock.jobs({ status: "completed" })).jobs[0];
    const response = await mock.artifacts(summary.job_id);
    const fetchMock = respond(response);
    const result = await new HttpApiClient("/api/v1").artifacts(summary.job_id);
    expect(result).toEqual(response);
    expect(result.contract_version).toBe("1.0");
    expect(result.artifacts[0]).toMatchObject({
      artifact_id: "art_01",
      sha256: expect.any(String),
      content_url: expect.any(String),
      is_primary: true,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/jobs/${summary.job_id}/artifacts`,
      expect.objectContaining({ method: "GET" }),
    );
  });
  it("retrieves upload metadata without requesting image bytes", async () => {
    const mock = new MockApiClient(),
      record = await mock.uploadRecord(`upl_${"a".repeat(32)}`);
    const fetchMock = respond(record);
    expect(
      await new HttpApiClient("/api/v1").uploadRecord(record.upload_id),
    ).toEqual(record);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/uploads/${record.upload_id}`,
      expect.objectContaining({ method: "GET" }),
    );
  });
  it("preserves the full job ResourcePlan and full JobSummary primary artifact", async () => {
    const mock = new MockApiClient(),
      list = await mock.jobs({ status: "completed" }),
      job = await mock.job(list.jobs[0].job_id);
    respond(job);
    const client = new HttpApiClient("/api/v1");
    expect((await client.job(job.job_id)).compute.resource_plan).toEqual(
      job.compute.resource_plan,
    );
    respond(list);
    expect((await client.jobs()).jobs[0].primary_artifact).toEqual(
      job.artifacts.find((a) => a.is_primary),
    );
  });
  it.each([400, 404, 405])(
    "preserves a structured %i error rather than inferring status from the code",
    async (status) => {
      const code: ErrorCode =
        status === 405 ? "REQUEST_FIELD_INVALID" : "PATH_INVALID";
      const response = {
        contract_version: "1.0",
        errors: [issue(code, "job_id", "Check the requested path or ID.")],
        warnings: [],
      };
      respond(response, status);
      const client = new HttpApiClient("/api/v1");
      await expect(client.job("bad-id")).rejects.toMatchObject({
        name: "ApiError",
        status,
        response,
        message: "Check the requested path or ID.",
      });
      await expect(
        client.artifactContent("bad-id", "art_01"),
      ).rejects.toMatchObject({ name: "ApiError", status, response });
    },
  );
  it("returns HTTP 200 reports for well-formed JSON with an invalid request shape", async () => {
    const report: ValidationReport = {
      contract_version: "1.0",
      valid: false,
      errors: [
        issue("REQUEST_FIELD_INVALID", null, "Provide a request object."),
      ],
      warnings: [],
      resource_plan: null,
    };
    respond(report);
    expect(
      await new HttpApiClient("/api/v1").validate(
        null as unknown as CreateJobRequest,
      ),
    ).toEqual(report);
  });
  it("propagates the HTTP 400 response for a non-JSON validate body", async () => {
    const response = {
      contract_version: "1.0",
      errors: [issue("REQUEST_FIELD_INVALID", null, "Body must be JSON.")],
      warnings: [],
    };
    respond(response, 400);
    await expect(
      new HttpApiClient("/api/v1").validate({} as CreateJobRequest),
    ).rejects.toMatchObject({ status: 400, response });
  });
});
