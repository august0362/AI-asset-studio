import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type {
  ArtifactsResponse,
  GenerationResult,
  JobSummary,
  KaggleResourceSnapshot,
  UploadRecord,
} from "../../src/api/types";

const backend = process.env.AAS_HTTP_BACKEND_URL ?? "http://127.0.0.1:8000/api/v1";
const png = resolve("tests/fixtures/artifacts/mock.png");
let exchanges: unknown[] = [],
  pending: Promise<void>[] = [],
  errors: string[] = [],
  fixtureRequests: string[] = [];

test.beforeAll(async ({ request }) => {
  let health;
  try {
    health = await request.get(`${backend}/health`, { timeout: 2000 });
  } catch {
    /* Skip when the independently owned backend is offline. */
  }
  test.skip(
    !health?.ok(),
    "Start the mock backend with .\\.venv\\Scripts\\python -m aas_backend first.",
  );
  expect(await health!.json()).toMatchObject({
    contract_version: "1.0",
    compute_mode: "mock",
    status: "ok",
  });
});
test.beforeEach(async ({ page }) => {
  exchanges = [];
  pending = [];
  errors = [];
  fixtureRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().includes("/mock-artifacts/"))
      fixtureRequests.push(request.url());
  });
  page.on("response", (response) => {
    if (
      !response.url().startsWith(backend) ||
      !response.headers()["content-type"]?.includes("application/json")
    )
      return;
    pending.push(
      (async () => {
        const req = response.request();
        let body: unknown = null;
        try {
          body = req.postDataJSON();
        } catch {
          body = req.headers()["content-type"]?.startsWith("multipart/")
            ? "multipart file: local mock.png fixture"
            : req.postData();
        }
        exchanges.push({
          method: req.method(),
          url: response.url(),
          request: body,
          status: response.status(),
          response: await response.json(),
        });
      })().catch((error) => {
        errors.push(String(error));
      }),
    );
  });
});
test.afterEach(async ({ page }, info) => {
  await Promise.all(pending);
  const path = info.outputPath("exchanges.json");
  await mkdir(dirname(path), { recursive: true });
  await writeFile(
    path,
    JSON.stringify({ exchanges, errors, fixtureRequests }, null, 2) + "\n",
  );
  await info.attach("HTTP request and response evidence", {
    path,
    contentType: "application/json",
  });
  if (!page.isClosed())
    await screenshot(page, {
      path: info.outputPath("final-screen.png"),
      fullPage: true,
    });
  expect(errors).toEqual([]);
  expect(fixtureRequests).toEqual([]);
});

async function screenshot(
  page: Page,
  options: Parameters<Page["screenshot"]>[0],
) {
  // Full-page captures should start at the page origin rather than preserving
  // the scroll/focus left by a download or a canvas keyboard interaction.
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement)
      document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  await page.screenshot(options);
}

async function raw(
  request: APIRequestContext,
  path: string,
  method = "GET",
  body?: unknown,
  contentType = "application/json",
) {
  const response = await request.fetch(`${backend}${path}`, {
    method,
    data:
      body === undefined
        ? undefined
        : typeof body === "string" && contentType === "text/plain"
          ? body
          : JSON.stringify(body),
    headers: body === undefined ? undefined : { "Content-Type": contentType },
  });
  const value = await response.json();
  exchanges.push({
    method,
    url: `${backend}${path}`,
    request: body,
    status: response.status(),
    response: value,
  });
  return { status: response.status(), body: value };
}
async function allJobs(request: APIRequestContext) {
  const jobs: JobSummary[] = [];
  let cursor: string | null = null;
  do {
    const result = await raw(
      request,
      `/jobs?limit=50${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
    );
    expect(result.status).toBe(200);
    jobs.push(...result.body.jobs);
    cursor = result.body.next_cursor;
  } while (cursor);
  return jobs;
}
async function create(page: Page, button: string) {
  const response = page.waitForResponse(
    (r) => r.url() === `${backend}/jobs` && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: button, exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(201);
  const job: GenerationResult = await result.json();
  expect(job.status).toBe("created");
  await expect(page.getByText("completed", { exact: true })).toBeVisible({
    timeout: 45_000,
  });
  return job.job_id;
}
async function download(
  page: Page,
  format: "PNG" | "GLB",
  job: GenerationResult,
) {
  const event = page.waitForEvent("download");
  await page
    .getByRole("button", { name: `Download ${format}`, exact: true })
    .click();
  const artifact = await event;
  const primary = job.artifacts.find((a) => a.is_primary)!;
  expect(artifact.suggestedFilename()).toBe(
    `${job.job_id}_${primary.artifact_id}.${primary.format}`,
  );
  const bytes = await readFile((await artifact.path())!);
  expect(bytes.length).toBe(primary.size_bytes);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(primary.sha256);
  if (format === "PNG") {
    expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(bytes.readUInt32BE(16)).toBe(primary.width);
    expect(bytes.readUInt32BE(20)).toBe(primary.height);
  } else {
    expect(bytes.subarray(0, 4).toString()).toBe("glTF");
    expect(bytes.readUInt32LE(4)).toBe(2);
    expect(bytes.readUInt32LE(8)).toBe(bytes.length);
  }
}
async function views(page: Page) {
  const buffer = await readFile(png);
  await page.locator("input[type=file]").setInputFiles(
    ["front", "side", "back"].map((role) => ({
      name: `${role}.png`,
      mimeType: "image/png",
      buffer,
    })),
  );
  await expect(page.getByText("back.png", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Remove .*png/ })).toHaveCount(
    3,
  );
}

test("a) HTTP Text→2D completes, previews/downloads a PNG, and preserves the full plan", async ({
  page,
  request,
}, info) => {
  await page.goto("/generate/text-to-2d");
  await expect(page.getByText("Local API session")).toBeVisible();
  await page
    .getByRole("textbox", { name: /Prompt/ })
    .fill("M2 HTTP acceptance: ornate frost greatsword, crystalline blade");
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("mock-t2d-basic");
  await page
    .getByRole("combobox", { name: "Accelerator", exact: true })
    .selectOption("gpu_t4x2");
  const id = await create(page, "Generate 2D image");
  const result = await raw(request, `/jobs/${id}`),
    job: GenerationResult = result.body;
  expect(result.status).toBe(200);
  expect(job.status).toBe("completed");
  expect(job.execution.backend).toBe("mock");
  expect(job.compute.resource_plan).toMatchObject({
    contract_version: "1.0",
    fit: "ok",
    profile_id: "default",
    accelerator_id: "gpu_t4x2",
    selection: "user_selected",
    required_seconds: 645,
    estimate_basis: {
      estimated_runtime_seconds: 30,
      safety_factor: 1.5,
      overhead_seconds: 600,
    },
  });
  expect(
    job.compute.resource_plan.candidates.map((c) => c.accelerator_id),
  ).toEqual(["gpu_t4x2"]);
  expect(job.warnings.map((w) => w.code)).not.toContain("COMPUTE_VRAM_UNKNOWN");
  await expect(page.locator(".image-preview img")).toBeVisible();
  expect(
    await page
      .locator(".image-preview img")
      .evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
  ).toBe(true);
  await download(page, "PNG", job);
  await screenshot(page, {
    path: info.outputPath("a-text-to-2d.png"),
    fullPage: true,
  });
  const artifacts = await raw(request, `/jobs/${id}/artifacts`);
  expect(artifacts.status).toBe(200);
  expect(artifacts.body as ArtifactsResponse).toEqual({
    contract_version: "1.0",
    artifacts: job.artifacts,
  });
  expect(
    (await allJobs(request)).find((j) => j.job_id === id)?.primary_artifact,
  ).toEqual(job.artifacts.find((a) => a.is_primary));
  await page.getByRole("link", { name: "View job & logs" }).click();
  const plan = page
    .getByRole("heading", { name: "Resource plan", exact: true })
    .locator("..")
    .locator("..");
  await expect(plan).toContainText("runtime × 1.5 + 10 min overhead");
  await expect(plan).toContainText("10.8 min");
  await screenshot(page, {
    path: info.outputPath("a-job-plan.png"),
    fullPage: true,
  });
});

test("b) HTTP multiview uploads three views, records uploading, and previews/downloads GLB + PNG", async ({
  page,
  request,
}, info) => {
  await page.goto("/generate/image-to-3d");
  await views(page);
  await page
    .getByRole("combobox", { name: "Accelerator", exact: true })
    .selectOption("gpu_t4x2");
  const id = await create(page, "Generate 3D asset");
  const result = await raw(request, `/jobs/${id}`),
    job: GenerationResult = result.body;
  expect(job.status).toBe("completed");
  expect(job.request.model_id).toBe("mock-i3d-multiview");
  expect(job.request.inputs.map((i) => i.role)).toEqual([
    "front",
    "side",
    "back",
  ]);
  expect(job.status_history.map((h) => h.status)).toEqual([
    "created",
    "uploading",
    "queued",
    "running",
    "downloading",
    "completed",
  ]);
  expect(job.compute.resource_plan).toMatchObject({
    contract_version: "1.0",
    required_seconds: 1950,
    estimate_basis: {
      estimated_runtime_seconds: 900,
      safety_factor: 1.5,
      overhead_seconds: 600,
    },
    session_limit_seconds: 43200,
    candidates: [{ accelerator_id: "gpu_t4x2", fit: "ok", reasons: [] }],
    warnings: [],
    errors: [],
  });
  await expect(page.getByText("GLB loaded · textured fixture")).toBeVisible();
  const canvas = page.locator("canvas");
  const initial = await canvas.screenshot();
  await canvas.focus();
  await page.keyboard.press("ArrowLeft");
  const orbit = await canvas.screenshot();
  expect(orbit.equals(initial)).toBe(false);
  await page.keyboard.press("-");
  expect((await canvas.screenshot()).equals(orbit)).toBe(false);
  await expect(
    page.getByRole("img", { name: "PNG preview of the generated 3D artifact" }),
  ).toBeVisible();
  expect(
    await page
      .locator(".artifact-thumbnail img")
      .evaluate(
        (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
      ),
  ).toBe(true);
  await download(page, "GLB", job);
  await screenshot(page, {
    path: info.outputPath("b-image-to-3d.png"),
    fullPage: true,
  });
  const preview = job.artifacts.find(
    (a) => a.artifact_id === job.preview?.artifact_id,
  )!;
  expect(preview.kind).toBe("preview");
  expect(preview.format).toBe("png");
  const previewResponse = await request.get(
    `${backend}/jobs/${id}/artifacts/${preview.artifact_id}/content`,
  );
  const bytes = await previewResponse.body();
  expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(preview.sha256);
  await page.getByRole("link", { name: "View job & logs" }).click();
  await expect(page.locator(".timeline-item.uploading")).toBeVisible();
  await screenshot(page, {
    path: info.outputPath("b-uploading-timeline.png"),
    fullPage: true,
  });
});

test("c) V-02 shows input errors, disables Generate, and backend rejection creates no job", async ({
  page,
  request,
}, info) => {
  const uploads: UploadRecord[] = [];
  page.on("response", (response) => {
    if (response.url() === `${backend}/uploads` && response.status() === 201)
      pending.push(
        response.json().then((record) => {
          uploads.push(record);
        }),
      );
  });
  await page.goto("/generate/image-to-3d");
  await views(page);
  await Promise.all(pending);
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("mock-i3d-single");
  await expect(
    page.getByText("MODEL_INPUT_COUNT_EXCEEDED · inputs"),
  ).toBeVisible();
  await expect(page.getByText(/MODEL_IMAGE_ROLE_UNSUPPORTED/)).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Generate 3D asset" }),
  ).toBeDisabled();
  const before = (await allJobs(request)).map((j) => j.job_id).sort();
  const body = {
    contract_version: "1.0",
    client_request_id: crypto.randomUUID(),
    pipeline_type: "image_to_3d",
    asset_category: "character",
    model_id: "mock-i3d-single",
    prompt: null,
    inputs: ["front", "side", "back"].map((role) => ({
      upload_id: uploads.find((u) => u.filename === `${role}.png`)!.upload_id,
      role,
    })),
    options: {},
    output_format: "glb",
    compute: { profile_id: "default", accelerator_id: "gpu_t4x2" },
  };
  const report = await raw(request, "/validate", "POST", body);
  expect(report.status).toBe(200);
  expect(report.body.valid).toBe(false);
  expect(report.body.errors.map((e: { code: string }) => e.code)).toContain(
    "MODEL_INPUT_COUNT_EXCEEDED",
  );
  const rejected = await raw(request, "/jobs", "POST", body);
  expect(rejected.status).toBe(422);
  expect(rejected.body.errors.map((e: { code: string }) => e.code)).toContain(
    "MODEL_INPUT_COUNT_EXCEEDED",
  );
  expect(
    rejected.body.errors.filter(
      (e: { code: string }) => e.code === "MODEL_IMAGE_ROLE_UNSUPPORTED",
    ),
  ).toHaveLength(2);
  expect((await allJobs(request)).map((j) => j.job_id).sort()).toEqual(before);
  await screenshot(page, {
    path: info.outputPath("c-rejected-inputs.png"),
    fullPage: true,
  });
});

test("d) HTTP resources show backend mock data and clarified routes/validation behave as documented", async ({
  page,
  request,
}, info) => {
  const profiles = await raw(request, "/compute/profiles");
  expect(profiles.body.profiles[0].mode).toBe("mock");
  // Read the current session; this check also works when run alone or after a/b.
  // A running session can precede its first reporter frame. Wait for that frame
  // or for the session to finish; neither path requires creating a job here.
  await expect
    .poll(
      async () => {
        const current: KaggleResourceSnapshot = (
          await raw(request, "/compute/profiles/default/snapshot")
        ).body;
        return (
          current.session_status !== "running" ||
          (current.source.host === "mock" && current.source.gpu === "mock")
        );
      },
      { timeout: 15_000, intervals: [100] },
    )
    .toBe(true);
  const snapshot = page.waitForResponse((response) =>
    response.url().includes("/compute/profiles/default/snapshot"),
  );
  await page.goto("/resources");
  const s: KaggleResourceSnapshot = await (await snapshot).json();
  expect(["running", "finished", "none"]).toContain(s.session_status);
  if (s.session_status === "running") {
    expect(Object.values(s.source)).toEqual(["mock", "mock", "mock", "mock"]);
    expect(s.gpu_devices.map((gpu) => gpu.index)).toEqual([0, 1]);
    await expect(page.getByText("Source: mock")).toHaveCount(5);
    for (const gpu of s.gpu_devices) {
      await expect(
        page.getByRole("meter", { name: `GPU${gpu.index} utilization` }),
      ).toHaveAttribute("aria-valuenow", String(gpu.utilization_percent));
      await expect(
        page.getByRole("meter", { name: `GPU${gpu.index} VRAM used` }),
      ).toHaveAttribute(
        "aria-valuenow",
        String(gpu.vram_used_bytes! / 1024 ** 3),
      );
    }
  } else {
    for (const group of ["host", "gpu"] as const) {
      expect(s.source[group]).toBe("none");
      expect(s.freshness_status[group]).toBe("not_applicable");
    }
    expect(s.cpu_utilization_percent).toBeNull();
    expect(s.gpu_devices).toEqual([]);
    await expect(page.getByText("Source: none")).toHaveCount(2);
    await expect(page.getByText("not applicable", { exact: true })).toHaveCount(
      2,
    );
    await expect(
      page.getByText("Unknown", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByRole("meter", { name: "CPU utilization" }),
    ).toHaveCount(0);
    await expect(
      page.getByText("No session · GPU telemetry is not applicable."),
    ).toBeVisible();
  }
  await expect(
    page.getByRole("combobox", { name: "Development scenario" }),
  ).toHaveCount(0);
  await screenshot(page, {
    path: info.outputPath("d-resources.png"),
    fullPage: true,
  });
  const registry = await raw(request, "/models");
  const fixture = JSON.parse(
    await readFile(resolve("tests/fixtures/contracts/models.json"), "utf8"),
  );
  expect(registry.body.models).toEqual(fixture.models);
  for (const [path, status] of [
    ["/not-a-route", 404],
    ["/jobs/bad-id", 400],
  ] as const) {
    const result = await raw(request, path);
    expect(result.status).toBe(status);
    expect(result.body.errors[0].code).toBe("PATH_INVALID");
  }
  const wrongMethod = await raw(request, "/health", "POST");
  expect(wrongMethod.status).toBe(405);
  expect(wrongMethod.body.errors[0].code).toBe("REQUEST_FIELD_INVALID");
  const nonJson = await raw(
    request,
    "/validate",
    "POST",
    "not-json",
    "text/plain",
  );
  expect(nonJson.status).toBe(400);
  expect(nonJson.body.errors[0].code).toBe("REQUEST_FIELD_INVALID");
  for (const value of [null, [], false, 42, "text", {}]) {
    const result = await raw(request, "/validate", "POST", value);
    expect(result.status).toBe(200);
    expect(result.body).toMatchObject({
      contract_version: "1.0",
      valid: false,
      resource_plan: null,
    });
    expect(result.body.errors.length).toBeGreaterThan(0);
  }
  const uploaded = await request.post(`${backend}/uploads`, {
    multipart: {
      file: {
        name: "http-metadata.png",
        mimeType: "image/png",
        buffer: await readFile(png),
      },
    },
  });
  expect(uploaded.status()).toBe(201);
  const upload: UploadRecord = await uploaded.json();
  exchanges.push({
    method: "POST",
    url: `${backend}/uploads`,
    request: { file: "http-metadata.png", mime_type: "image/png" },
    status: 201,
    response: upload,
  });
  const record = await raw(request, `/uploads/${upload.upload_id}`);
  expect(record.status).toBe(200);
  expect(record.body).toEqual(upload);
});
