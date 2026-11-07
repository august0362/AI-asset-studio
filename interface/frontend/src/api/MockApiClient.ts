import type {
  ApiClient,
  Artifact,
  ArtifactsResponse,
  BulkDeleteResult,
  CreateJobRequest,
  GenerationResult,
  ImageRole,
  JobFilters,
  JobStatus,
  JobSummary,
  RunGroup,
  Scenario,
  Scheduling,
  UploadRecord,
} from "./types";
import { catalog, makeSnapshot, models, profiles } from "./fixtures";
import metadata from "../../tests/fixtures/contracts/artifact-metadata.json";
import { ApiError, issue, reject } from "./errors";
import { validateRequest } from "../validation/validate";
import { planResources } from "../validation/planner";
import { MockCharacterApi } from "./MockCharacterApi";
import {
  sharedCharacterFixture,
  sharedCharacterContent,
} from "./characterFixtures";
import type {
  BatchManifest,
  ProductionTask,
  SubmitBatchRequest,
} from "./characterTypes";

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
    reject(
      "UPLOAD_TOO_LARGE",
      "Upload an image smaller than 50 MiB.",
      413,
      "file",
    );
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

export class MockApiClient extends MockCharacterApi implements ApiClient {
  private deletedSharedJobs = new Set<string>();
  private characterTasks = new Map<string, ProductionTask[]>();
  protected characterJobs() {
    return this;
  }
  protected async enqueueCharacterTasks(
    character: string,
    manifest: BatchManifest,
    tasks: ProductionTask[],
    request: SubmitBatchRequest,
  ) {
    const first = tasks[0];
    const profile = profiles.find(
      (p) => p.profile_id === request.compute.profile_id,
    );
    const model = models.find((m) => m.model_id === manifest.target_model_id);
    const selected =
      request.compute.accelerator_id === "auto"
        ? null
        : request.compute.accelerator_id;
    const optionsFor = (task: ProductionTask) => ({
      ...task.options,
      width: task.width,
      height: task.height,
      seed: task.seed,
      ...(task.negative_prompt
        ? { negative_prompt: task.negative_prompt }
        : {}),
    });
    for (const task of tasks) {
      const report = await this.validate({
        contract_version: "1.0",
        client_request_id: request.client_request_id,
        pipeline_type: "text_to_2d",
        asset_category: "character",
        model_id: manifest.target_model_id,
        prompt: task.prompt,
        inputs: [],
        options: optionsFor(task),
        output_format: "png",
        compute: {
          profile_id: request.compute.profile_id,
          accelerator_id: selected,
        },
      });
      if (!report.valid)
        throw new ApiError({
          contract_version: "1.1",
          errors: report.errors,
          warnings: report.warnings,
        });
    }
    const plan =
      model && profile
        ? planResources(
            {
              ...model,
              runtime: {
                ...model.runtime,
                estimated_runtime_seconds:
                  model.runtime.estimated_runtime_seconds === null
                    ? null
                    : model.runtime.estimated_runtime_seconds * tasks.length,
              },
            },
            profile,
            makeSnapshot(this.scenario, this.now()),
            selected,
          )
        : null;
    if (plan?.errors.length)
      throw new ApiError({
        contract_version: "1.1",
        errors: plan.errors,
        warnings: plan.warnings,
      });
    const job = await this.createJob({
      contract_version: "1.0",
      client_request_id: request.client_request_id,
      pipeline_type: "text_to_2d",
      asset_category: "character",
      model_id: manifest.target_model_id,
      prompt: first.prompt,
      inputs: [],
      options: optionsFor(first),
      output_format: "png",
      compute: {
        profile_id: request.compute.profile_id,
        accelerator_id:
          request.compute.accelerator_id === "auto"
            ? null
            : request.compute.accelerator_id,
      },
    });
    this.characterTasks.set(job.job_id, copy(tasks));
    const record = this.get(job.job_id);
    record.request.prompt = null;
    if (plan) record.compute.resource_plan = plan;
    record.request.batch = {
      character_id: character,
      manifest_id: manifest.manifest_id,
      group_id: "g01",
      attempt: manifest.attempts.length + 1,
      task_ids: tasks.map((t) => t.task_id),
    };
    return copy(record);
  }
  private uploads = new Map<
    string,
    { record: UploadRecord; file: Blob | null }
  >();
  private records = new Map<string, GenerationResult>();
  private requests = new Map<string, CreateJobRequest>();
  private idempotency = new Map<string, string>();
  private active = new Map<string, number>();
  /** v1.2 run control (§14): auto-run, FIFO request time and run group per job. */
  private runControl = new Map<
    string,
    {
      auto_run: boolean;
      run_requested_at: string | null;
      order: number;
      group_id: string | null;
      group_job_ids: string[];
      gpu_index: 0 | 1 | null;
    }
  >();
  private requestOrder = 0;
  private scenario: Scenario = "fresh";
  constructor(
    private stepMs = 1400,
    seed = true,
    private now = () => Date.now(),
  ) {
    super();
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
  async uploadRecord(id: string) {
    return copy(
      this.uploads.get(id)?.record ??
        reject("UPLOAD_NOT_FOUND", "Upload not found."),
    );
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
    const autoRun = req.auto_run ?? true;
    this.runControl.set(job_id, {
      auto_run: autoRun,
      run_requested_at: autoRun ? stamp : null,
      order: ++this.requestOrder,
      group_id: null,
      group_job_ids: [],
      gpu_index: null,
    });
    return this.view(job);
  }
  private control(id: string) {
    let value = this.runControl.get(id);
    if (!value) {
      const job = this.records.get(id);
      value = {
        auto_run: true,
        run_requested_at: job?.created_at ?? null,
        order: 0,
        group_id: null,
        group_job_ids: [],
        gpu_index: null,
      };
      this.runControl.set(id, value);
    }
    return value;
  }
  private queueState(job: GenerationResult): Scheduling["queue_state"] {
    if (job.status !== "created") return null;
    if (this.active.has(job.job_id)) return "starting";
    return this.control(job.job_id).auto_run ? "waiting" : "held";
  }
  private fifo(): string[][] {
    const waiting = [...this.records.values()]
      .filter((j) => this.queueState(j) === "waiting")
      .sort((a, b) => {
        const x = this.control(a.job_id),
          y = this.control(b.job_id);
        return (
          (x.run_requested_at ?? "").localeCompare(y.run_requested_at ?? "") ||
          x.order - y.order ||
          a.job_id.localeCompare(b.job_id)
        );
      });
    const entries: string[][] = [],
      seen = new Set<string>();
    for (const job of waiting) {
      const c = this.control(job.job_id),
        key = c.group_id ?? job.job_id;
      if (seen.has(key)) continue;
      seen.add(key);
      entries.push(c.group_id ? c.group_job_ids : [job.job_id]);
    }
    return entries;
  }
  private scheduling(job: GenerationResult, fifo = this.fifo()): Scheduling {
    const c = this.control(job.job_id),
      state = this.queueState(job);
    const position = fifo.findIndex((entry) => entry.includes(job.job_id));
    return {
      auto_run: c.auto_run,
      queue_state: state,
      queue_position:
        state === "waiting" && position >= 0 ? position + 1 : null,
      run_requested_at: c.auto_run ? c.run_requested_at : null,
      group_id: c.group_id,
      group_job_ids: [...c.group_job_ids],
      gpu_index: c.gpu_index,
    };
  }
  private view(job: GenerationResult): GenerationResult {
    return copy({ ...job, scheduling: this.scheduling(job) });
  }
  private hold(id: string) {
    const c = this.control(id);
    Object.assign(c, {
      auto_run: false,
      run_requested_at: null,
      group_id: null,
      group_job_ids: [],
      gpu_index: null,
    });
  }
  async setAutoRun(id: string, autoRun: boolean) {
    this.pump();
    const job = this.get(id),
      state = this.queueState(job),
      c = this.control(id);
    if (state !== "held" && state !== "waiting")
      reject(
        "JOB_ALREADY_STARTED",
        "This job has already started, so its auto-run setting can no longer change.",
        409,
      );
    if (autoRun && state === "held")
      Object.assign(c, {
        auto_run: true,
        run_requested_at: new Date(this.now()).toISOString(),
        order: ++this.requestOrder,
      });
    if (!autoRun && state === "waiting") {
      for (const partner of c.group_job_ids)
        if (partner !== id) this.hold(partner);
      this.hold(id);
    }
    return this.view(job);
  }
  async createRunGroup(jobIds: [string, string]): Promise<RunGroup> {
    this.pump();
    const invalid = (reason: string, message: string): never => {
      throw new ApiError(
        {
          contract_version: "1.0",
          errors: [
            issue("JOB_GROUP_INVALID", "job_ids", message, "error", { reason }),
          ],
          warnings: [],
        },
        422,
      );
    };
    const jobs = jobIds.map((id) => this.get(id));
    for (const job of jobs) {
      const state = this.queueState(job);
      if (state === "waiting")
        invalid(
          "not_held",
          "Only held jobs can be grouped. Turn auto-run off first.",
        );
      if (state !== "held")
        reject(
          "JOB_ALREADY_STARTED",
          "This job has already started and cannot be grouped.",
          409,
          "job_ids",
        );
    }
    if (jobIds.length !== 2 || jobIds[0] === jobIds[1])
      invalid("count", "A run group has exactly two different jobs.");
    for (const job of jobs) {
      if (job.request.pipeline_type !== "text_to_2d")
        invalid("pipeline", "Only Text→2D jobs can be grouped.");
      if (job.request.batch)
        invalid("batch", "Character batch jobs cannot be grouped.");
    }
    if (jobs[0].compute.profile_id !== jobs[1].compute.profile_id)
      invalid("profile", "Both jobs must use the same compute profile.");
    for (const job of jobs)
      if (job.compute.accelerator_id !== "gpu_t4x2")
        invalid(
          "accelerator",
          "Both jobs must run on GPU T4 ×2 (one job per T4).",
        );
    const perGpu = profiles
      .find((p) => p.profile_id === jobs[0].compute.profile_id)
      ?.accelerators.find(
        (a) => a.accelerator_id === "gpu_t4x2",
      )?.vram_bytes_per_device;
    for (const job of jobs) {
      const model = models.find((m) => m.model_id === job.request.model_id);
      if (!model || model.runtime.multi_gpu !== "unsupported")
        invalid(
          "multi_gpu",
          "Only models that use a single GPU can be grouped.",
        );
      const need = model!.runtime.minimum_gpu_vram_bytes;
      if (need === null || !perGpu || need > perGpu)
        invalid(
          "vram",
          "The model's GPU memory need is unknown or larger than one GPU of the accelerator.",
        );
    }
    const group_id = `grp_${randomHex().slice(0, 12)}`,
      at = new Date(this.now()).toISOString(),
      order = ++this.requestOrder;
    jobIds.forEach((id, index) =>
      Object.assign(this.control(id), {
        auto_run: true,
        run_requested_at: at,
        order,
        group_id,
        group_job_ids: [...jobIds],
        gpu_index: index as 0 | 1,
      }),
    );
    return {
      contract_version: "1.0",
      group_id,
      job_ids: [...jobIds],
      run_requested_at: at,
    };
  }
  async deleteJobs(jobIds: string[]): Promise<BulkDeleteResult> {
    if (
      !jobIds.length ||
      jobIds.length > 200 ||
      new Set(jobIds).size !== jobIds.length
    )
      reject(
        "REQUEST_FIELD_INVALID",
        "Send 1 to 200 different job IDs.",
        422,
        "job_ids",
      );
    const result: BulkDeleteResult = {
      contract_version: "1.0",
      deleted: [],
      refused: [],
    };
    for (const id of jobIds) {
      try {
        await this.deleteJob(id);
        result.deleted.push(id);
      } catch (error) {
        const code =
          error instanceof ApiError &&
          error.response.errors[0]?.code === "JOB_NOT_FOUND"
            ? "JOB_NOT_FOUND"
            : "JOB_NOT_TERMINAL";
        result.refused.push({ job_id: id, code });
      }
    }
    return result;
  }
  private pump() {
    // Running jobs first, then the FIFO (§14.3): one session per profile in the mock; a run group is one session.
    const fifo = this.fifo().flat();
    const jobs = [...this.records.values()]
      .filter((j) => !terminal(j.status))
      .filter((j) => this.active.has(j.job_id) || fifo.includes(j.job_id))
      .sort(
        (a, b) =>
          Number(this.active.has(b.job_id)) -
            Number(this.active.has(a.job_id)) ||
          fifo.indexOf(a.job_id) - fifo.indexOf(b.job_id),
      );
    const busy = new Set<string>();
    for (const job of jobs) {
      if (!this.active.has(job.job_id) && busy.has(job.compute.profile_id))
        continue;
      const started = this.active.get(job.job_id) ?? this.now();
      this.active.set(job.job_id, started);
      for (const partner of this.control(job.job_id).group_job_ids)
        if (!this.active.has(partner)) this.active.set(partner, started);
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
      const tasks = this.characterTasks.get(job.job_id);
      if (tasks)
        job.artifacts = tasks.map((task, i) => ({
          ...artifact("png", `art_${String(i + 1).padStart(2, "0")}`, i === 0),
          kind: "image",
          task_id: task.task_id,
        }));
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
    const fifo = this.fifo();
    return {
      jobs: rows.slice(offset, offset + limit).map((j): JobSummary =>
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
          scheduling: this.scheduling(j, fifo),
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
    const fixture = sharedCharacterFixture("batch_jobs").find(
      (j) => j.job_id === id,
    );
    if (fixture && !this.records.has(id) && !this.deletedSharedJobs.has(id))
      return fixture;
    return this.view(this.get(id));
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
    if (old.request.batch)
      reject("JOB_NOT_RETRYABLE", "Use the character batch retry.", 409);
    if (old.status !== "failed" || !old.error?.retryable)
      reject(
        "JOB_NOT_RETRYABLE",
        "Only retryable failed jobs can be retried.",
        409,
      );
    const job = await this.createJob({
      ...this.requests.get(id)!,
      client_request_id,
      auto_run: true, // a retry is a new, ungrouped job that runs by itself (§14.4)
    });
    const actual = this.get(job.job_id);
    actual.execution.retry_of = id;
    return this.view(actual);
  }
  async deleteJob(id: string) {
    const j = await this.job(id),
      state = j.scheduling?.queue_state ?? null;
    if (
      !terminal(j.status) &&
      state !== "held" &&
      !(state === "waiting" && !j.request.batch)
    )
      reject(
        "JOB_NOT_TERMINAL",
        "Only completed, failed, held or waiting jobs can be deleted.",
        409,
      );
    if (!terminal(j.status))
      for (const partner of this.control(id).group_job_ids)
        if (partner !== id) this.hold(partner);
    this.runControl.delete(id);
    this.records.delete(id);
    if (sharedCharacterFixture("batch_jobs").some((j) => j.job_id === id))
      this.deletedSharedJobs.add(id);
    this.requests.delete(id);
    this.active.delete(id);
    for (const [key, value] of this.idempotency)
      if (value === id) this.idempotency.delete(key);
  }
  async artifacts(id: string): Promise<ArtifactsResponse> {
    return {
      contract_version: "1.0",
      artifacts: (await this.job(id)).artifacts,
    };
  }
  async artifactContent(id: string, artifactId: string) {
    if (!this.records.has(id)) {
      if (this.deletedSharedJobs.has(id))
        reject("ARTIFACT_NOT_FOUND", "Artifact not found.");
      return sharedCharacterContent(
        `/api/v1/jobs/${id}/artifacts/${artifactId}/content`,
      );
    }
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
