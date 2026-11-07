import type {
  ApiClient,
  ArtifactsResponse,
  BulkDeleteResult,
  Catalog,
  Category,
  ComputeProfile,
  CreateJobRequest,
  ErrorResponse,
  GenerationResult,
  JobFilters,
  JobLogs,
  JobStatusResponse,
  JobSummary,
  KaggleResourceSnapshot,
  ModelCapabilities,
  Pipeline,
  RunGroup,
  UploadRecord,
  ValidationReport,
} from "./types";
import { ApiError } from "./errors";
import { HttpCharacterApi } from "./HttpCharacterApi";
export class HttpApiClient extends HttpCharacterApi implements ApiClient {
  constructor(private base = "http://127.0.0.1:8000/api/v1") {
    super(base);
  }
  private async request<T>(
    path: string,
    method = "GET",
    body?: unknown,
  ): Promise<T> {
    const form = body instanceof FormData;
    const res = await fetch(`${this.base}${path}`, {
      method,
      headers:
        body && !form ? { "Content-Type": "application/json" } : undefined,
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    });
    if (!res.ok)
      throw new ApiError((await res.json()) as ErrorResponse, res.status);
    return res.status === 204 ? (undefined as T) : (res.json() as Promise<T>);
  }
  private async content(path: string): Promise<Blob> {
    const res = await fetch(`${this.base}${path}`);
    if (!res.ok)
      throw new ApiError((await res.json()) as ErrorResponse, res.status);
    return res.blob();
  }
  health() {
    return this.request<{
      status: string;
      contract_version: string;
      compute_mode: "mock" | "kaggle";
    }>("/health");
  }
  catalog() {
    return this.request<Catalog>("/catalog");
  }
  models(pipeline_type?: Pipeline, asset_category?: Category) {
    const params = new URLSearchParams();
    if (pipeline_type) params.set("pipeline_type", pipeline_type);
    if (asset_category) params.set("asset_category", asset_category);
    return this.request<{ models: ModelCapabilities[] }>(`/models?${params}`);
  }
  model(id: string) {
    return this.request<ModelCapabilities>(`/models/${encodeURIComponent(id)}`);
  }
  upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    return this.request<UploadRecord>("/uploads", "POST", body);
  }
  uploadContent(id: string) {
    return this.content(`/uploads/${encodeURIComponent(id)}/content`);
  }
  uploadRecord(id: string) {
    return this.request<UploadRecord>(`/uploads/${encodeURIComponent(id)}`);
  }
  deleteUpload(id: string) {
    return this.request<void>(`/uploads/${encodeURIComponent(id)}`, "DELETE");
  }
  validate(req: CreateJobRequest) {
    return this.request<ValidationReport>("/validate", "POST", req);
  }
  createJob(req: CreateJobRequest) {
    return this.request<GenerationResult>("/jobs", "POST", req);
  }
  jobs(filters: JobFilters = {}) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined) params.set(k, String(v));
    });
    return this.request<{ jobs: JobSummary[]; next_cursor: string | null }>(
      `/jobs?${params}`,
    );
  }
  job(id: string) {
    return this.request<GenerationResult>(`/jobs/${encodeURIComponent(id)}`);
  }
  jobStatus(id: string) {
    return this.request<JobStatusResponse>(
      `/jobs/${encodeURIComponent(id)}/status`,
    );
  }
  logs(id: string, offset = 0, limit = 500) {
    return this.request<JobLogs>(
      `/jobs/${encodeURIComponent(id)}/logs?offset=${offset}&limit=${limit}`,
    );
  }
  retryJob(id: string, client_request_id: string) {
    return this.request<GenerationResult>(
      `/jobs/${encodeURIComponent(id)}/retry`,
      "POST",
      { client_request_id },
    );
  }
  deleteJob(id: string) {
    return this.request<void>(`/jobs/${encodeURIComponent(id)}`, "DELETE");
  }
  setAutoRun(id: string, autoRun: boolean) {
    return this.request<GenerationResult>(
      `/jobs/${encodeURIComponent(id)}`,
      "PATCH",
      { auto_run: autoRun },
    );
  }
  createRunGroup(jobIds: [string, string]) {
    return this.request<RunGroup>("/jobs/groups", "POST", { job_ids: jobIds });
  }
  deleteJobs(jobIds: string[]) {
    return this.request<BulkDeleteResult>("/jobs/delete", "POST", {
      job_ids: jobIds,
    });
  }
  artifacts(id: string) {
    return this.request<ArtifactsResponse>(
      `/jobs/${encodeURIComponent(id)}/artifacts`,
    );
  }
  artifactContent(id: string, art: string) {
    return this.content(
      `/jobs/${encodeURIComponent(id)}/artifacts/${encodeURIComponent(art)}/content?download=1`,
    );
  }
  inputContent(id: string, input: string) {
    return this.content(
      `/jobs/${encodeURIComponent(id)}/inputs/${encodeURIComponent(input)}/content`,
    );
  }
  profiles() {
    return this.request<{ profiles: ComputeProfile[] }>("/compute/profiles");
  }
  snapshot(id: string, refresh = false) {
    return this.request<KaggleResourceSnapshot>(
      `/compute/profiles/${encodeURIComponent(id)}/snapshot?refresh=${refresh ? 1 : 0}`,
    );
  }
}
