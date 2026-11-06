import type {
  ApiClient,
  Artifact,
  CreateJobRequest,
  GenerationResult,
  ImageRole,
  JobFilters,
  JobStatus,
  Scenario,
  UploadRecord,
} from "./types";
import { catalog, makeSnapshot, models, profiles } from "./fixtures";
import metadata from "../../tests/fixtures/contracts/artifact-metadata.json";
import { ApiError, issue, reject } from "./errors";
import { validateRequest } from "../validation/validate";

const copy = <T>(value: T): T => structuredClone(value);
const terminal = (s: JobStatus) => s === "completed" || s === "failed";
const randomHex = () => crypto.randomUUID().replaceAll("-", "");
const base = import.meta.env.BASE_URL;
export const fixtureUrl = (format: "png" | "glb") =>
  `${base}mock-artifacts/mock.${format}`;

export async function inspectImage(file: File): Promise<{
  mime: string;
  width: number;
  height: number;
  bytes: ArrayBuffer;
}> {
  if (file.size > catalog.limits.max_upload_bytes)
    reject("UPLOAD_TOO_LARGE", "Upload an image smaller than 50 MiB.", 413, "file");
  const bytes = await file.arrayBuffer();
  const h = new Uint8Array(bytes);
  const mime =
    h[0] === 137 &&
    h[1] === 80 &&
    h[2] === 78 &&
    h[3] === 71 &&
    h[4] === 13 &&
    h[5] === 10 &&
    h[6] === 26 &&
    h[7] === 10
      ? "image/png"
      : h[0] === 255 && h[1] === 216 && h[2] === 255
        ? "image/jpeg"
        : String.fromCharCode(...h.slice(0, 4)) === "RIFF" &&
            String.fromCharCode(...h.slice(8, 12)) === "WEBP"
          ? "image/webp"
          : null;
  if (!mime)
    reject(
      "UPLOAD_UNSUPPORTED_TYPE",
      "Upload a PNG, JPEG or WebP image. The file content must match its format.",
      415,
      "file",
    );
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    if (!image.naturalWidth || !image.naturalHeight) throw new Error("empty");
    return {
      mime,
      width: image.naturalWidth,
      height: image.naturalHeight,
      bytes,
    };
  } catch {
    return reject(
      "UPLOAD_CORRUPT",
      "This image cannot be decoded. Choose a valid image.",
      422,
      "file",
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

export class MockApiClient implements ApiClient {
  private uploads = new Map<
    string,
    { record: UploadRecord; file: Blob | null }
  >();
  private records = new Map<string, GenerationResult>();
  private requests = new Map<string, CreateJobRequest>();
  private idempotency = new Map<string, string>();
  private active = new Map<string, number>();
  private scenario: Scenario = "fresh";
  constructor(
    private stepMs = 1400,
    seed = true,
    private now = () => Date.now(),
  ) {
    if (seed) this.seed();
  }
  setScenario(scenario: Scenario) {
    this.scenario = scenario;
  }
  async health() {
    return {
      status: "ok",
      contract_version: "1.0",
      compute_mode: "mock" as const,
    };
  }
  async catalog() {
    return copy(catalog);
  }
  async models(
    pipeline_type?: CreateJobRequest["pipeline_type"],
    asset_category?: CreateJobRequest["asset_category"],
  ) {
    return {
      models: copy(
        models.filter(
          (m) =>
            (!pipeline_type ||
              m.supported_pipeline_types.includes(pipeline_type)) &&
            (!asset_category ||
              m.supported_asset_categories.includes(asset_category)),
        ),
      ),
    };
  }
  async model(id: string) {
    return copy(
      models.find((m) => m.model_id === id) ??
        reject("MODEL_NOT_FOUND", "This model does not exist."),
    );
  }
  async profiles() {
    return { profiles: copy(profiles) };
  }
  async snapshot(id: string) {
    if (!profiles.some((p) => p.profile_id === id))
      reject("COMPUTE_PROFILE_NOT_FOUND", "This profile does not exist.");
    return makeSnapshot(this.scenario, this.now());
  }
  async upload(file: File) {
    const decoded = await inspectImage(file);
    const digest = await crypto.subtle.digest("SHA-256", decoded.bytes);
    const record: UploadRecord = {
      contract_version: "1.0",
      upload_id: `upl_${randomHex()}`,
      filename: file.name,
      mime_type: decoded.mime,
      size_bytes: file.size,
      width: decoded.width,
      height: decoded.height,
      sha256: Array.from(new Uint8Array(digest), (b) =>
        b.toString(16).padStart(2, "0"),
      ).join(""),
      created_at: new Date(this.now()).toISOString(),
      expires_at: new Date(this.now() + 86400_000).toISOString(),
    };
    this.uploads.set(record.upload_id, {
      record,
      file: new Blob([decoded.bytes], { type: decoded.mime }),
    });
    return copy(record);
  }
  async uploadContent(id: string) {
    const u =
      this.uploads.get(id) ?? reject("UPLOAD_NOT_FOUND", "Upload not found.");
    return u.file ?? this.fixture("png");
  }
  async deleteUpload(id: string) {
    if (!this.uploads.has(id)) reject("UPLOAD_NOT_FOUND", "Upload not found.");
    if (
      [...this.requests.values()].some((r) =>
        r.inputs.some((i) => i.upload_id === id),
      )
    )
      reject(
        "UPLOAD_IN_USE",
        "A job references this upload. Remove it from your form without deleting the job input.",
        409,
      );
    this.uploads.delete(id);
  }
  async validate(req: CreateJobRequest) {
    return copy(
      validateRequest(req, {
        catalog,
        models,
        uploads: [...this.uploads.values()].map((u) => u.record),
        profiles,
        snapshot: makeSnapshot(this.scenario, this.now()),
        now: this.now(),
      }),
    );
  }
  async createJob(req: CreateJobRequest) {
    const existing = this.idempotency.get(req.client_request_id);
    if (existing) return this.job(existing);
    const report = await this.validate(req);
    if (!report.valid || !report.resource_plan)
      throw new ApiError({
        contract_version: report.contract_version,
        errors: report.errors,
        warnings: report.warnings,
      });
    const stamp = new Date(this.now()).toISOString();
    const job_id = `job_${stamp.slice(0, 19).replaceAll("-", "").replaceAll(":", "")}Z_${randomHex().slice(0, 6)}`;
    const model = models.find((m) => m.model_id === req.model_id)!;
    const job: GenerationResult = {
      contract_version: "1.0",
      job_id,
      status: "created",
      status_history: [{ status: "created", at: stamp }],
      request: {
        pipeline_type: req.pipeline_type,
        asset_category: req.asset_category,
        model_id: req.model_id,
        prompt: req.prompt?.trim() || null,
        output_format: req.output_format,
        options: {
          ...Object.fromEntries(
            Object.entries(model.options_schema).map(([k, v]) => [
              k,
              v.default,
            ]),
          ),
          ...req.options,
        },
        inputs: req.inputs.map((i, n) => {
          const u = this.uploads.get(i.upload_id)!.record;
          const input_id = `in_${String(n + 1).padStart(2, "0")}`;
          return {
            input_id,
            role: i.role,
            mime_type: u.mime_type,
            width: u.width,
            height: u.height,
            size_bytes: u.size_bytes,
            content_url: `/api/v1/jobs/${job_id}/inputs/${input_id}/content`,
          };
        }),
      },
      compute: {
        ...req.compute,
        accelerator_id: report.resource_plan.accelerator_id,
        resource_plan: report.resource_plan,
      },
      artifacts: [],
      preview: null,
      warnings: report.warnings,
      error: null,
      execution: {
        backend: "mock",
        remote_ref: null,
        submitted_at: null,
        started_at: null,
        finished_at: null,
        duration_seconds: null,
        transient_retries: 0,
        retry_of: null,
      },
      created_at: stamp,
      updated_at: stamp,
    };
    this.records.set(job_id, job);
    this.requests.set(job_id, copy(req));
    this.idempotency.set(req.client_request_id, job_id);
    return copy(job);
  }
  private pump() {
    const jobs = [...this.records.values()].filter((j) => !terminal(j.status));
    const busy = new Set<string>();
    for (const job of jobs) {
      if (busy.has(job.compute.profile_id)) continue;
      const started = this.active.get(job.job_id) ?? this.now();
      this.active.set(job.job_id, started);
      const stages: JobStatus[] = job.request.inputs.length
        ? [
            "created",
            "uploading",
            "queued",
            "running",
            "downloading",
            "completed",
          ]
        : ["created", "queued", "running", "downloading", "completed"];
      const target = Math.min(
        stages.length - 1,
        Math.floor((this.now() - started) / this.stepMs),
      );
      while (job.status_history.length <= target)
        this.transition(
          job,
          stages[job.status_history.length],
          new Date(
            started + job.status_history.length * this.stepMs,
          ).toISOString(),
        );
      if (!terminal(job.status)) busy.add(job.compute.profile_id);
    }
  }
  private transition(job: GenerationResult, status: JobStatus, at: string) {
    job.status = status;
    job.updated_at = at;
    job.status_history.push({ status, at });
    if (status === "queued") job.execution.submitted_at = at;
    if (status === "running") job.execution.started_at = at;
    if (status === "completed") {
      job.execution.finished_at = at;
      job.execution.duration_seconds = job.execution.started_at
        ? (Date.parse(at) - Date.parse(job.execution.started_at)) / 1000
        : null;
      const artifact = (
        format: "png" | "glb",
        id: string,
        primary: boolean,
      ): Artifact => ({
        artifact_id: id,
        kind: primary ? (format === "glb" ? "model_3d" : "image") : "preview",
        format,
        mime_type: format === "png" ? "image/png" : "model/gltf-binary",
        ...metadata[format],
        is_primary: primary,
        content_url: `/api/v1/jobs/${job.job_id}/artifacts/${id}/content`,
      });
      job.artifacts = [artifact(job.request.output_format, "art_01", true)];
      if (job.request.output_format === "glb") {
        job.artifacts.push(artifact("png", "art_02", false));
        job.preview = { artifact_id: "art_02" };
      } else job.preview = { artifact_id: "art_01" };
    }
  }
  async jobs(filters: JobFilters = {}) {
    this.pump();
    const limit = Math.min(50, Math.max(1, filters.limit ?? 50)),
      offset = Number(filters.cursor) || 0;
    const rows = [...this.records.values()]
      .filter(
        (j) =>
          (!filters.status || j.status === filters.status) &&
          (!filters.pipeline_type ||
            j.request.pipeline_type === filters.pipeline_type),
      )
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    return {
      jobs: rows.slice(offset, offset + limit).map((j) =>
        copy({
          job_id: j.job_id,
          status: j.status,
          pipeline_type: j.request.pipeline_type,
          asset_category: j.request.asset_category,
          model_id: j.request.model_id,
          created_at: j.created_at,
          updated_at: j.updated_at,
          primary_artifact: j.artifacts.find((a) => a.is_primary) ?? null,
          error_code: j.error?.code ?? null,
        }),
      ),
      next_cursor: offset + limit < rows.length ? String(offset + limit) : null,
    };
  }
  private get(id: string) {
    return (
      this.records.get(id) ??
      reject("JOB_NOT_FOUND", "Job not found. Return to job history.")
    );
  }
  async job(id: string) {
    this.pump();
    return copy(this.get(id));
  }
  async jobStatus(id: string) {
    const j = await this.job(id);
    return {
      job_id: id,
      status: j.status,
      updated_at: j.updated_at,
      progress: null,
    };
  }
  async logs(id: string, offset = 0, limit = 500) {
    const j = await this.job(id);
    const lines = j.status_history.map((h, n) => ({
      n,
      at: h.at,
      source: "backend" as const,
      text: `[MOCK] ${h.status}: ${h.status === "completed" ? "Fixture artifacts validated. No AI inference ran." : h.status === "failed" ? j.error?.message : "Simulated job lifecycle."}`,
    }));
    return {
      lines: lines.slice(offset, offset + limit),
      next_offset: Math.min(lines.length, offset + limit),
      complete: terminal(j.status),
    };
  }
  async retryJob(id: string, client_request_id: string) {
    const old = await this.job(id);
    if (old.status !== "failed" || !old.error?.retryable)
      reject(
        "JOB_NOT_RETRYABLE",
        "Only retryable failed jobs can be retried.",
        409,
      );
    const job = await this.createJob({
      ...this.requests.get(id)!,
      client_request_id,
    });
    const actual = this.get(job.job_id);
    actual.execution.retry_of = id;
    return copy(actual);
  }
  async deleteJob(id: string) {
    const j = await this.job(id);
    if (!terminal(j.status))
      reject(
        "JOB_NOT_TERMINAL",
        "Wait until the job completes or fails before deleting it.",
        409,
      );
    this.records.delete(id);
    this.requests.delete(id);
    this.active.delete(id);
    for (const [key, value] of this.idempotency)
      if (value === id) this.idempotency.delete(key);
  }
  async artifacts(id: string) {
    return (await this.job(id)).artifacts;
  }
  async artifactContent(id: string, artifactId: string) {
    const a =
      (await this.job(id)).artifacts.find(
        (a) => a.artifact_id === artifactId,
      ) ?? reject("ARTIFACT_NOT_FOUND", "Artifact not found.");
    return this.fixture(a.format);
  }
  async inputContent(id: string, inputId: string) {
    const j = await this.job(id);
    const index = j.request.inputs.findIndex((i) => i.input_id === inputId);
    if (index < 0) reject("ARTIFACT_NOT_FOUND", "Input not found.");
    return this.uploadContent(this.requests.get(id)!.inputs[index].upload_id);
  }
  private async fixture(format: "png" | "glb") {
    const response = await fetch(fixtureUrl(format));
    if (!response.ok)
      reject(
        "ARTIFACT_NOT_FOUND",
        "Mock fixture could not be loaded. Run npm run fixtures and restart.",
        404,
      );
    return response.blob();
  }
  private seed() {
    // Seed records are deliberately labeled examples; all correspond to real fixture files.
    const start = this.now() - 3600_000;
    const uploadId = `upl_${"a".repeat(32)}`;
    this.uploads.set(uploadId, {
      record: {
        contract_version: "1.0",
        upload_id: uploadId,
        filename: "mock.png",
        mime_type: "image/png",
        ...metadata.png,
        width: 768,
        height: 768,
        created_at: new Date(start).toISOString(),
        expires_at: new Date(this.now() + 86400_000).toISOString(),
      },
      file: null,
    });
    for (let i = 0; i < 5; i++) {
      const is3d = i === 0 || i === 2;
      const req: CreateJobRequest = {
        contract_version: "1.0",
        client_request_id: crypto.randomUUID(),
        pipeline_type: is3d ? "image_to_3d" : "text_to_2d",
        asset_category: catalog.asset_categories[i % 4],
        model_id: is3d ? "mock-i3d-single" : "mock-t2d-basic",
        prompt: is3d ? null : "Cyan ceramic study — mock fixture",
        inputs: is3d
          ? [{ upload_id: uploadId, role: "front" as ImageRole }]
          : [],
        options: {},
        output_format: is3d ? "glb" : "png",
        compute: { profile_id: "default", accelerator_id: null },
      };
      const id = `job_${new Date(start + i * 60000).toISOString().slice(0, 19).replaceAll("-", "").replaceAll(":", "")}Z_${(i + 1).toString(16).padStart(6, "0")}`;
      const plan = validateRequest(req, {
        catalog,
        models,
        profiles,
        snapshot: makeSnapshot("fresh", this.now()),
        uploads: [...this.uploads.values()].map((u) => u.record),
        now: this.now(),
      }).resource_plan!;
      const at = new Date(start + i * 60000).toISOString();
      const j: GenerationResult = {
        contract_version: "1.0",
        job_id: id,
        status: "created",
        status_history: [{ status: "created", at }],
        request: {
          pipeline_type: req.pipeline_type,
          asset_category: req.asset_category,
          model_id: req.model_id,
          output_format: req.output_format,
          options: Object.fromEntries(
            Object.entries(
              models.find((m) => m.model_id === req.model_id)!.options_schema,
            ).map(([key, value]) => [key, value.default]),
          ),
          prompt: req.prompt ?? null,
          inputs: is3d
            ? [
                {
                  input_id: "in_01",
                  role: "front",
                  mime_type: "image/png",
                  width: 768,
                  height: 768,
                  size_bytes: metadata.png.size_bytes,
                  content_url: `/api/v1/jobs/${id}/inputs/in_01/content`,
                },
              ]
            : [],
        },
        compute: {
          profile_id: "default",
          accelerator_id: plan.accelerator_id,
          resource_plan: plan,
        },
        artifacts: [],
        preview: null,
        warnings: plan.warnings,
        error: null,
        execution: {
          backend: "mock",
          remote_ref: null,
          submitted_at: null,
          started_at: null,
          finished_at: null,
          duration_seconds: null,
          transient_retries: 0,
          retry_of: null,
        },
        created_at: at,
        updated_at: at,
      };
      this.records.set(id, j);
      this.requests.set(id, req);
      for (const status of (is3d
        ? ["uploading", "queued", "running"]
        : ["queued", "running"]) as JobStatus[])
        this.transition(j, status, at);
      if (i === 4) {
        j.error = issue(
          "BACKEND_RESTARTED",
          null,
          "Example interrupted mock job. Retry creates a new job.",
          "error",
          { failed_in_status: "running" },
          true,
        );
        this.transition(j, "failed", at);
        j.execution.finished_at = at;
      } else {
        this.transition(j, "downloading", at);
        this.transition(j, "completed", at);
      }
    }
  }
}
