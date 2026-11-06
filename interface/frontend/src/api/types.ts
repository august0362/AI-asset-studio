// Hand mirror of docs/CONTRACTS.md v1.0. No backend storage paths or credentials.
export type Pipeline = "text_to_2d" | "image_to_3d" | "text_to_3d";
export type Category = "character" | "skill_effect" | "weapon" | "companion";
export type ImageRole =
  | "front"
  | "side"
  | "back"
  | "three_quarter"
  | "detail"
  | "style_reference";
export type OutputFormat = "png" | "glb";
export type AcceleratorKind = "cpu" | "gpu_cuda" | "tpu";
export type JobStatus =
  | "created"
  | "uploading"
  | "queued"
  | "running"
  | "downloading"
  | "completed"
  | "failed";
export type Availability =
  | "available"
  | "experimental"
  | "planned"
  | "unavailable";
export type Fit = "ok" | "unknown" | "insufficient";
export type Freshness =
  | "fresh"
  | "stale"
  | "unavailable"
  | "unsupported"
  | "not_applicable";
export type Source =
  | "kaggle_cli_quota"
  | "kaggle_cli_status"
  | "notebook_telemetry"
  | "local_observation"
  | "mock"
  | "none";
export type ErrorCode =
  | "CONTRACT_VERSION_UNSUPPORTED"
  | "REQUEST_FIELD_INVALID"
  | "PIPELINE_UNKNOWN"
  | "PIPELINE_NOT_AVAILABLE"
  | "ASSET_CATEGORY_UNKNOWN"
  | "MODEL_NOT_FOUND"
  | "MODEL_UNAVAILABLE"
  | "MODEL_EXPERIMENTAL"
  | "MODEL_PIPELINE_INCOMPATIBLE"
  | "MODEL_CATEGORY_INCOMPATIBLE"
  | "MODEL_PROMPT_REQUIRED"
  | "MODEL_PROMPT_NOT_SUPPORTED"
  | "MODEL_PROMPT_TOO_LONG"
  | "MODEL_IMAGE_INPUT_NOT_SUPPORTED"
  | "MODEL_INPUT_COUNT_INSUFFICIENT"
  | "MODEL_INPUT_COUNT_EXCEEDED"
  | "MODEL_IMAGE_ROLE_UNSUPPORTED"
  | "MODEL_IMAGE_ROLE_DUPLICATE"
  | "MODEL_REQUIRED_VIEW_MISSING"
  | "MODEL_UNSUPPORTED_FILE_FORMAT"
  | "MODEL_FILE_TOO_LARGE"
  | "MODEL_IMAGE_DIMENSIONS_INVALID"
  | "MODEL_OUTPUT_FORMAT_UNSUPPORTED"
  | "MODEL_OPTION_UNSUPPORTED"
  | "MODEL_OPTION_INVALID"
  | "MODEL_ACCELERATOR_INCOMPATIBLE"
  | "MODEL_RUNTIME_UNKNOWN"
  | "UPLOAD_NOT_FOUND"
  | "UPLOAD_CORRUPT"
  | "UPLOAD_TOO_LARGE"
  | "UPLOAD_UNSUPPORTED_TYPE"
  | "UPLOAD_IN_USE"
  | "COMPUTE_PROFILE_NOT_FOUND"
  | "COMPUTE_PROFILE_UNAUTHENTICATED"
  | "COMPUTE_VRAM_INSUFFICIENT"
  | "COMPUTE_VRAM_UNKNOWN"
  | "COMPUTE_SESSION_LIMIT_EXCEEDED"
  | "COMPUTE_QUOTA_INSUFFICIENT"
  | "COMPUTE_QUOTA_UNKNOWN"
  | "COMPUTE_TPU_QUOTA_UNAVAILABLE"
  | "COMPUTE_TELEMETRY_UNAVAILABLE"
  | "COMPUTE_TELEMETRY_STALE"
  | "JOB_NOT_FOUND"
  | "ARTIFACT_NOT_FOUND"
  | "JOB_NOT_RETRYABLE"
  | "JOB_NOT_TERMINAL"
  | "PATH_INVALID"
  | "KAGGLE_AUTH_FAILED"
  | "KAGGLE_RATE_LIMITED"
  | "KAGGLE_NETWORK_ERROR"
  | "KAGGLE_UPLOAD_FAILED"
  | "KAGGLE_SUBMIT_FAILED"
  | "KAGGLE_QUOTA_EXHAUSTED"
  | "KAGGLE_KERNEL_ERROR"
  | "KAGGLE_TIMEOUT"
  | "ARTIFACT_DOWNLOAD_FAILED"
  | "ARTIFACT_INVALID"
  | "BACKEND_RESTARTED"
  | "INTERNAL_ERROR";
export interface ErrorItem {
  code: ErrorCode;
  severity: "error" | "warning";
  field: string | null;
  message: string;
  details: Record<string, unknown>;
  retryable: boolean;
}
export interface ErrorResponse {
  contract_version: string;
  errors: ErrorItem[];
  warnings: ErrorItem[];
}
export type OptionValue = number | string | boolean | null;
export interface OptionSchema {
  type: "integer" | "number" | "string" | "boolean";
  enum?: OptionValue[];
  minimum?: number;
  maximum?: number;
  max_length?: number;
  default: OptionValue;
  description?: string;
}
export interface ModelCapabilities {
  contract_version: string;
  model_id: string;
  display_name: string;
  adapter: string;
  is_mock: boolean;
  availability: Availability;
  supported_pipeline_types: Pipeline[];
  supported_asset_categories: Category[];
  inputs: {
    prompt_supported: boolean;
    prompt_required: boolean;
    prompt_max_length: number | null;
    min_images: number;
    max_images: number;
    supported_image_roles: ImageRole[];
    required_image_roles: ImageRole[];
    supported_mime_types: string[] | null;
    maximum_file_size_bytes: number | null;
    min_image_width: number | null;
    min_image_height: number | null;
    max_image_width: number | null;
    max_image_height: number | null;
  };
  supported_output_formats: OutputFormat[];
  runtime: {
    supported_accelerators: AcceleratorKind[];
    multi_gpu: "unsupported" | "optional" | "required";
    minimum_gpu_vram_bytes: number | null;
    estimated_runtime_seconds: number | null;
  };
  options_schema: Record<string, OptionSchema>;
  unknown_requirements: string[];
}
export interface Catalog {
  contract_version: string;
  pipelines: {
    pipeline_type: Pipeline;
    display_name: string;
    availability: Availability;
    output_formats: OutputFormat[];
  }[];
  asset_categories: Category[];
  image_roles: ImageRole[];
  limits: {
    max_upload_bytes: number;
    max_images_per_request: number;
    prompt_max_length: number;
    supported_upload_mime_types: string[];
  };
}
export interface UploadRecord {
  contract_version: string;
  upload_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  sha256: string;
  created_at: string;
  expires_at: string;
}
export interface CreateJobRequest {
  contract_version: string;
  client_request_id: string;
  pipeline_type: Pipeline;
  asset_category: Category;
  model_id: string;
  prompt?: string | null;
  inputs: { upload_id: string; role: ImageRole }[];
  options: Record<string, OptionValue>;
  output_format: OutputFormat;
  compute: { profile_id: string; accelerator_id: string | null };
}
export interface Accelerator {
  accelerator_id: string;
  kind: AcceleratorKind;
  device_count: number;
  vram_bytes_per_device: number | null;
  max_session_seconds: number;
}
export interface ComputeProfile {
  contract_version: string;
  profile_id: string;
  display_name: string;
  owner_label: string;
  mode: "mock" | "kaggle";
  enabled: boolean;
  authorization_confirmed: boolean;
  accelerators: Accelerator[];
}
export interface ResourcePlan {
  contract_version: string;
  profile_id: string;
  accelerator_id: string | null;
  selection: "user_selected" | "recommended";
  fit: Fit;
  required_seconds: number | null;
  estimate_basis: {
    estimated_runtime_seconds: number | null;
    safety_factor: number;
    overhead_seconds: number;
  };
  session_limit_seconds: number | null;
  quota_remaining_seconds: number | null;
  candidates: { accelerator_id: string; fit: Fit; reasons: ErrorItem[] }[];
  warnings: ErrorItem[];
  errors: ErrorItem[];
}
export interface ValidationReport {
  contract_version: string;
  valid: boolean;
  errors: ErrorItem[];
  warnings: ErrorItem[];
  resource_plan: ResourcePlan | null;
}
export interface GpuDevice {
  index: number;
  name: string | null;
  utilization_percent: number | null;
  vram_used_bytes: number | null;
  vram_total_bytes: number | null;
  temperature_c: number | null;
  status: "available" | "unavailable" | "unsupported";
}
export type MetricGroup = "quota" | "session" | "host" | "gpu";
export interface KaggleResourceSnapshot {
  contract_version: string;
  compute_profile_id: string;
  authentication_status:
    | "authenticated"
    | "unauthenticated"
    | "invalid_credentials"
    | "unknown";
  accelerator_type: string | null;
  accelerator_availability: {
    accelerator_id: string;
    status: "available" | "quota_exhausted" | "unknown" | "not_in_profile";
  }[];
  gpu_quota_total_hours: number | null;
  gpu_quota_used_hours: number | null;
  gpu_quota_remaining_hours: number | null;
  tpu_quota_total_hours: number | null;
  tpu_quota_used_hours: number | null;
  tpu_quota_remaining_hours: number | null;
  quota_reset_at: string | null;
  session_started_at: string | null;
  estimated_session_remaining_seconds: number | null;
  session_status:
    | "none"
    | "queued"
    | "running"
    | "finished"
    | "failed"
    | "unknown";
  cpu_utilization_percent: number | null;
  ram_used_bytes: number | null;
  ram_total_bytes: number | null;
  gpu_devices: GpuDevice[];
  observed_at: Record<MetricGroup | "snapshot", string | null>;
  source: Record<MetricGroup, Source>;
  freshness_status: Record<MetricGroup, Freshness>;
  error: ErrorItem[];
}
export interface Artifact {
  artifact_id: string;
  kind: "image" | "model_3d" | "texture" | "preview";
  format: OutputFormat;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  width: number | null;
  height: number | null;
  is_primary: boolean;
  content_url: string;
}
export interface GenerationResult {
  contract_version: string;
  job_id: string;
  status: JobStatus;
  status_history: { status: JobStatus; at: string }[];
  request: {
    pipeline_type: Pipeline;
    asset_category: Category;
    model_id: string;
    prompt: string | null;
    output_format: OutputFormat;
    options: Record<string, OptionValue>;
    inputs: {
      input_id: string;
      role: ImageRole;
      mime_type: string;
      width: number;
      height: number;
      size_bytes: number;
      content_url: string;
    }[];
  };
  compute: {
    profile_id: string;
    accelerator_id: string | null;
    resource_plan: ResourcePlan;
  };
  artifacts: Artifact[];
  preview: { artifact_id: string } | null;
  warnings: ErrorItem[];
  error: ErrorItem | null;
  execution: {
    backend: "mock" | "kaggle";
    remote_ref: string | null;
    submitted_at: string | null;
    started_at: string | null;
    finished_at: string | null;
    duration_seconds: number | null;
    transient_retries: number;
    retry_of: string | null;
  };
  created_at: string;
  updated_at: string;
}
export interface JobSummary {
  job_id: string;
  status: JobStatus;
  pipeline_type: Pipeline;
  asset_category: Category;
  model_id: string;
  created_at: string;
  updated_at: string;
  primary_artifact: Artifact | null;
  error_code: ErrorCode | null;
}
export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  updated_at: string;
  progress: { stage: string; percent: number | null; message: string } | null;
}
export interface JobLogs {
  lines: {
    n: number;
    at: string;
    source: "backend" | "remote";
    text: string;
  }[];
  next_offset: number;
  complete: boolean;
}
export interface JobFilters {
  status?: JobStatus;
  pipeline_type?: Pipeline;
  limit?: number;
  cursor?: string;
}
export interface ApiClient {
  health(): Promise<{
    status: string;
    contract_version: string;
    compute_mode: "mock" | "kaggle";
  }>;
  catalog(): Promise<Catalog>;
  models(
    pipeline_type?: Pipeline,
    asset_category?: Category,
  ): Promise<{ models: ModelCapabilities[] }>;
  model(id: string): Promise<ModelCapabilities>;
  upload(file: File): Promise<UploadRecord>;
  uploadContent(id: string): Promise<Blob>;
  deleteUpload(id: string): Promise<void>;
  validate(request: CreateJobRequest): Promise<ValidationReport>;
  createJob(request: CreateJobRequest): Promise<GenerationResult>;
  jobs(
    filters?: JobFilters,
  ): Promise<{ jobs: JobSummary[]; next_cursor: string | null }>;
  job(id: string): Promise<GenerationResult>;
  jobStatus(id: string): Promise<JobStatusResponse>;
  logs(id: string, offset?: number, limit?: number): Promise<JobLogs>;
  retryJob(id: string, client_request_id: string): Promise<GenerationResult>;
  deleteJob(id: string): Promise<void>;
  artifacts(id: string): Promise<Artifact[]>;
  artifactContent(id: string, artifactId: string): Promise<Blob>;
  inputContent(id: string, inputId: string): Promise<Blob>;
  profiles(): Promise<{ profiles: ComputeProfile[] }>;
  snapshot(
    profileId: string,
    refresh?: boolean,
  ): Promise<KaggleResourceSnapshot>;
}
export const scenarios = [
  "fresh",
  "no_session",
  "quota_missing",
  "telemetry_stale",
  "telemetry_unavailable",
  "gpu_split",
  "quota_low",
] as const;
export type Scenario = (typeof scenarios)[number];
