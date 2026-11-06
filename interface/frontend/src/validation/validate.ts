import type {
  Catalog,
  ComputeProfile,
  CreateJobRequest,
  ErrorItem,
  KaggleResourceSnapshot,
  ModelCapabilities,
  OptionSchema,
  OptionValue,
  UploadRecord,
  ValidationReport,
} from "../api/types";
import { validationIssue as issue } from "../i18n/validation";
import { planResources } from "./planner";

export interface ValidationContext {
  catalog: Catalog;
  models: ModelCapabilities[];
  uploads: UploadRecord[];
  profiles: ComputeProfile[];
  snapshot: KaggleResourceSnapshot;
  now?: number;
}
export function optionValid(value: OptionValue, rule: OptionSchema): boolean {
  if (value === null) return rule.default === null;
  if (
    rule.type === "integer"
      ? typeof value !== "number" || !Number.isInteger(value)
      : typeof value !== rule.type
  )
    return false;
  if (rule.enum && !rule.enum.includes(value)) return false;
  if (
    typeof value === "number" &&
    (!Number.isFinite(value) ||
      (rule.minimum !== undefined && value < rule.minimum) ||
      (rule.maximum !== undefined && value > rule.maximum))
  )
    return false;
  return !(
    typeof value === "string" &&
    rule.max_length !== undefined &&
    value.length > rule.max_length
  );
}

// Stages 2–7 are pure. The lightweight mock schema guard also rejects unknown fields.
export function validateRequest(
  req: CreateJobRequest,
  context: ValidationContext,
): ValidationReport {
  const errors: ErrorItem[] = [],
    warnings: ErrorItem[] = [];
  const report = (
    resource_plan: ValidationReport["resource_plan"] = null,
  ): ValidationReport => ({
    contract_version: "1.0",
    valid: !errors.length,
    errors,
    warnings,
    resource_plan,
  });
  const add = (
    code: ErrorItem["code"],
    field: string,
    details: Record<string, unknown> = {},
  ) => errors.push(issue(code, field, "error", details));
  const known = [
    "contract_version",
    "client_request_id",
    "pipeline_type",
    "asset_category",
    "model_id",
    "prompt",
    "inputs",
    "options",
    "output_format",
    "compute",
  ];
  if (!req || typeof req !== "object") {
    add("REQUEST_FIELD_INVALID", "");
    return report();
  }
  if (
    typeof req.contract_version !== "string" ||
    !/^1\.\d+$/.test(req.contract_version)
  )
    add("CONTRACT_VERSION_UNSUPPORTED", "contract_version");
  for (const key of Object.keys(req))
    if (!known.includes(key)) add("REQUEST_FIELD_INVALID", key);
  for (const key of [
    "client_request_id",
    "pipeline_type",
    "asset_category",
    "model_id",
    "output_format",
  ] as const)
    if (typeof req[key] !== "string") add("REQUEST_FIELD_INVALID", key);
  if (
    typeof req.client_request_id === "string" &&
    !/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(
      req.client_request_id,
    )
  )
    add("REQUEST_FIELD_INVALID", "client_request_id");
  if (req.prompt != null && typeof req.prompt !== "string")
    add("REQUEST_FIELD_INVALID", "prompt");
  if (
    !Array.isArray(req.inputs) ||
    req.inputs.some(
      (i) =>
        !i ||
        typeof i.upload_id !== "string" ||
        !context.catalog.image_roles.includes(i.role) ||
        Object.keys(i).some((k) => !["upload_id", "role"].includes(k)),
    )
  )
    add("REQUEST_FIELD_INVALID", "inputs");
  if (
    !req.options ||
    typeof req.options !== "object" ||
    Array.isArray(req.options)
  )
    add("REQUEST_FIELD_INVALID", "options");
  if (
    !req.compute ||
    typeof req.compute.profile_id !== "string" ||
    !(
      req.compute.accelerator_id === null ||
      typeof req.compute.accelerator_id === "string"
    ) ||
    Object.keys(req.compute).some(
      (k) => !["profile_id", "accelerator_id"].includes(k),
    )
  )
    add("REQUEST_FIELD_INVALID", "compute");
  if (errors.length) return report();
  const pipeline = context.catalog.pipelines.find(
    (p) => p.pipeline_type === req.pipeline_type,
  );
  if (!pipeline) add("PIPELINE_UNKNOWN", "pipeline_type");
  else if (!["available", "experimental"].includes(pipeline.availability))
    add("PIPELINE_NOT_AVAILABLE", "pipeline_type");
  if (!context.catalog.asset_categories.includes(req.asset_category))
    add("ASSET_CATEGORY_UNKNOWN", "asset_category");
  if (errors.length) return report();
  const model = context.models.find((m) => m.model_id === req.model_id);
  if (!model) {
    add("MODEL_NOT_FOUND", "model_id");
    return report();
  }
  if (!["available", "experimental"].includes(model.availability))
    add("MODEL_UNAVAILABLE", "model_id");
  if (!model.supported_pipeline_types.includes(req.pipeline_type))
    add("MODEL_PIPELINE_INCOMPATIBLE", "model_id");
  if (!model.supported_asset_categories.includes(req.asset_category))
    add("MODEL_CATEGORY_INCOMPATIBLE", "asset_category");
  if (errors.length) return report();
  if (model.availability === "experimental")
    warnings.push(issue("MODEL_EXPERIMENTAL", "model_id", "warning"));
  const caps = model.inputs,
    prompt = req.prompt?.trim() || null;
  if (caps.prompt_required && !prompt) add("MODEL_PROMPT_REQUIRED", "prompt");
  if (!caps.prompt_supported && prompt)
    add("MODEL_PROMPT_NOT_SUPPORTED", "prompt");
  if (
    prompt &&
    prompt.length >
      Math.min(
        caps.prompt_max_length ?? 4000,
        context.catalog.limits.prompt_max_length,
      )
  )
    add("MODEL_PROMPT_TOO_LONG", "prompt");
  if (!caps.max_images && req.inputs.length)
    add("MODEL_IMAGE_INPUT_NOT_SUPPORTED", "inputs");
  else if (
    req.inputs.length >
    Math.min(caps.max_images, context.catalog.limits.max_images_per_request)
  )
    add("MODEL_INPUT_COUNT_EXCEEDED", "inputs", {
      max_images: caps.max_images,
      provided: req.inputs.length,
    });
  if (req.inputs.length < caps.min_images)
    add("MODEL_INPUT_COUNT_INSUFFICIENT", "inputs");
  const missing = caps.required_image_roles.filter(
    (r) => !req.inputs.some((i) => i.role === r),
  );
  if (missing.length)
    add("MODEL_REQUIRED_VIEW_MISSING", "inputs", { missing_roles: missing });
  const seen = new Set<string>();
  req.inputs.forEach((input, i) => {
    if (caps.max_images && !caps.supported_image_roles.includes(input.role))
      add("MODEL_IMAGE_ROLE_UNSUPPORTED", `inputs[${i}].role`, {
        role: input.role,
      });
    if (
      ["front", "side", "back", "three_quarter"].includes(input.role) &&
      seen.has(input.role)
    )
      add("MODEL_IMAGE_ROLE_DUPLICATE", `inputs[${i}].role`);
    seen.add(input.role);
    const upload = context.uploads.find((u) => u.upload_id === input.upload_id);
    const field = `inputs[${i}].upload_id`;
    if (
      !upload ||
      Date.parse(upload.expires_at) <= (context.now ?? Date.now())
    ) {
      add("UPLOAD_NOT_FOUND", field);
      return;
    }
    if (
      caps.supported_mime_types &&
      !caps.supported_mime_types.includes(upload.mime_type)
    )
      add("MODEL_UNSUPPORTED_FILE_FORMAT", field);
    if (
      upload.size_bytes >
      (caps.maximum_file_size_bytes ?? context.catalog.limits.max_upload_bytes)
    )
      add("MODEL_FILE_TOO_LARGE", field);
    if (
      (caps.min_image_width !== null && upload.width < caps.min_image_width) ||
      (caps.min_image_height !== null &&
        upload.height < caps.min_image_height) ||
      (caps.max_image_width !== null && upload.width > caps.max_image_width) ||
      (caps.max_image_height !== null && upload.height > caps.max_image_height)
    )
      add("MODEL_IMAGE_DIMENSIONS_INVALID", field, {
        actual: { width: upload.width, height: upload.height },
        allowed: {
          min_width: caps.min_image_width,
          min_height: caps.min_image_height,
          max_width: caps.max_image_width,
          max_height: caps.max_image_height,
        },
      });
  });
  if (
    !model.supported_output_formats.includes(req.output_format) ||
    !pipeline?.output_formats.includes(req.output_format)
  )
    add("MODEL_OUTPUT_FORMAT_UNSUPPORTED", "output_format");
  for (const [name, value] of Object.entries(req.options)) {
    const rule = model.options_schema[name];
    if (!rule) add("MODEL_OPTION_UNSUPPORTED", `options.${name}`);
    else if (!optionValid(value, rule))
      add("MODEL_OPTION_INVALID", `options.${name}`);
  }
  const inputErrors = errors.length;
  const profile = context.profiles.find(
    (p) =>
      p.profile_id === req.compute.profile_id &&
      p.enabled &&
      p.authorization_confirmed,
  );
  if (!profile) {
    add("COMPUTE_PROFILE_NOT_FOUND", "compute.profile_id");
    return report();
  }
  if (
    context.snapshot.compute_profile_id !== profile.profile_id ||
    context.snapshot.authentication_status !== "authenticated"
  ) {
    errors.push(
      issue(
        "COMPUTE_PROFILE_UNAUTHENTICATED",
        "compute.profile_id",
        "error",
        {},
        true,
      ),
    );
    return report();
  }
  const plan = planResources(
    model,
    profile,
    context.snapshot,
    req.compute.accelerator_id,
  );
  errors.push(...plan.errors);
  warnings.push(...plan.warnings);
  return report(inputErrors ? null : plan);
}
