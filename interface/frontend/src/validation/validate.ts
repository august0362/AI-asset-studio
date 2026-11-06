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
import { issue } from "../api/errors";
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
    message: string,
    details: Record<string, unknown> = {},
  ) => errors.push(issue(code, field, message, "error", details));
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
    add("REQUEST_FIELD_INVALID", "", "Provide a job request object.");
    return report();
  }
  if (
    typeof req.contract_version !== "string" ||
    !/^1\.\d+$/.test(req.contract_version)
  )
    add(
      "CONTRACT_VERSION_UNSUPPORTED",
      "contract_version",
      "Use contract version 1.x.",
    );
  for (const key of Object.keys(req))
    if (!known.includes(key))
      add("REQUEST_FIELD_INVALID", key, `Unknown field: ${key}. Remove it.`);
  for (const key of [
    "client_request_id",
    "pipeline_type",
    "asset_category",
    "model_id",
    "output_format",
  ] as const)
    if (typeof req[key] !== "string")
      add(
        "REQUEST_FIELD_INVALID",
        key,
        `${key} is required and must be a string.`,
      );
  if (
    typeof req.client_request_id === "string" &&
    !/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i.test(
      req.client_request_id,
    )
  )
    add(
      "REQUEST_FIELD_INVALID",
      "client_request_id",
      "Provide a UUID v4 request ID.",
    );
  if (req.prompt != null && typeof req.prompt !== "string")
    add("REQUEST_FIELD_INVALID", "prompt", "Prompt must be text or null.");
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
    add(
      "REQUEST_FIELD_INVALID",
      "inputs",
      "Provide upload IDs with a known reference role.",
    );
  if (
    !req.options ||
    typeof req.options !== "object" ||
    Array.isArray(req.options)
  )
    add("REQUEST_FIELD_INVALID", "options", "Options must be an object.");
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
    add(
      "REQUEST_FIELD_INVALID",
      "compute",
      "Choose a compute profile and an accelerator or Auto.",
    );
  if (errors.length) return report();
  const pipeline = context.catalog.pipelines.find(
    (p) => p.pipeline_type === req.pipeline_type,
  );
  if (!pipeline)
    add("PIPELINE_UNKNOWN", "pipeline_type", "Choose a known pipeline.");
  else if (!["available", "experimental"].includes(pipeline.availability))
    add(
      "PIPELINE_NOT_AVAILABLE",
      "pipeline_type",
      "Text → 3D is planned for M6 and cannot accept jobs yet.",
    );
  if (!context.catalog.asset_categories.includes(req.asset_category))
    add(
      "ASSET_CATEGORY_UNKNOWN",
      "asset_category",
      "Choose a known asset category.",
    );
  if (errors.length) return report();
  const model = context.models.find((m) => m.model_id === req.model_id);
  if (!model) {
    add("MODEL_NOT_FOUND", "model_id", "Select a model from the catalog.");
    return report();
  }
  if (!["available", "experimental"].includes(model.availability))
    add(
      "MODEL_UNAVAILABLE",
      "model_id",
      "This model is not available. Choose an available model.",
    );
  if (!model.supported_pipeline_types.includes(req.pipeline_type))
    add(
      "MODEL_PIPELINE_INCOMPATIBLE",
      "model_id",
      "Choose a model compatible with this pipeline.",
    );
  if (!model.supported_asset_categories.includes(req.asset_category))
    add(
      "MODEL_CATEGORY_INCOMPATIBLE",
      "asset_category",
      "This model does not support this category. Choose another model.",
    );
  if (errors.length) return report();
  if (model.availability === "experimental")
    warnings.push(
      issue(
        "MODEL_EXPERIMENTAL",
        "model_id",
        "This mock model is experimental.",
        "warning",
      ),
    );
  const caps = model.inputs,
    prompt = req.prompt?.trim() || null;
  if (caps.prompt_required && !prompt)
    add(
      "MODEL_PROMPT_REQUIRED",
      "prompt",
      "Enter a prompt to describe your asset.",
    );
  if (!caps.prompt_supported && prompt)
    add(
      "MODEL_PROMPT_NOT_SUPPORTED",
      "prompt",
      "This model does not accept prompts. Clear the retained prompt or choose another model.",
    );
  if (
    prompt &&
    prompt.length >
      Math.min(
        caps.prompt_max_length ?? 4000,
        context.catalog.limits.prompt_max_length,
      )
  )
    add(
      "MODEL_PROMPT_TOO_LONG",
      "prompt",
      "Shorten the prompt to the model limit.",
    );
  if (!caps.max_images && req.inputs.length)
    add(
      "MODEL_IMAGE_INPUT_NOT_SUPPORTED",
      "inputs",
      "This model accepts text only. Remove the retained images or switch models.",
    );
  else if (
    req.inputs.length >
    Math.min(caps.max_images, context.catalog.limits.max_images_per_request)
  )
    add(
      "MODEL_INPUT_COUNT_EXCEEDED",
      "inputs",
      `This model accepts at most ${caps.max_images} image(s); ${req.inputs.length} were provided.`,
      { max_images: caps.max_images, provided: req.inputs.length },
    );
  if (req.inputs.length < caps.min_images)
    add(
      "MODEL_INPUT_COUNT_INSUFFICIENT",
      "inputs",
      `Add at least ${caps.min_images} reference image(s).`,
    );
  const missing = caps.required_image_roles.filter(
    (r) => !req.inputs.some((i) => i.role === r),
  );
  if (missing.length)
    add(
      "MODEL_REQUIRED_VIEW_MISSING",
      "inputs",
      `Add the required ${missing.join(" and ")} view.`,
      { missing_roles: missing },
    );
  const seen = new Set<string>();
  req.inputs.forEach((input, i) => {
    if (caps.max_images && !caps.supported_image_roles.includes(input.role))
      add(
        "MODEL_IMAGE_ROLE_UNSUPPORTED",
        `inputs[${i}].role`,
        `The ${input.role} role is not supported by this model.`,
      );
    if (
      ["front", "side", "back", "three_quarter"].includes(input.role) &&
      seen.has(input.role)
    )
      add(
        "MODEL_IMAGE_ROLE_DUPLICATE",
        `inputs[${i}].role`,
        "Each view role can be used only once. Choose a different role.",
      );
    seen.add(input.role);
    const upload = context.uploads.find((u) => u.upload_id === input.upload_id);
    const field = `inputs[${i}].upload_id`;
    if (
      !upload ||
      Date.parse(upload.expires_at) <= (context.now ?? Date.now())
    ) {
      add(
        "UPLOAD_NOT_FOUND",
        field,
        "This upload is missing or expired. Upload the image again.",
      );
      return;
    }
    if (
      caps.supported_mime_types &&
      !caps.supported_mime_types.includes(upload.mime_type)
    )
      add(
        "MODEL_UNSUPPORTED_FILE_FORMAT",
        field,
        "Use an image format supported by this model.",
      );
    if (
      upload.size_bytes >
      (caps.maximum_file_size_bytes ?? context.catalog.limits.max_upload_bytes)
    )
      add(
        "MODEL_FILE_TOO_LARGE",
        field,
        "The image exceeds the model file size limit. Upload a smaller file.",
      );
    if (
      (caps.min_image_width !== null && upload.width < caps.min_image_width) ||
      (caps.min_image_height !== null &&
        upload.height < caps.min_image_height) ||
      (caps.max_image_width !== null && upload.width > caps.max_image_width) ||
      (caps.max_image_height !== null && upload.height > caps.max_image_height)
    )
      add(
        "MODEL_IMAGE_DIMENSIONS_INVALID",
        field,
        "Resize the reference image to the model dimensions.",
        {
          actual: { width: upload.width, height: upload.height },
          allowed: {
            min_width: caps.min_image_width,
            min_height: caps.min_image_height,
            max_width: caps.max_image_width,
            max_height: caps.max_image_height,
          },
        },
      );
  });
  if (
    !model.supported_output_formats.includes(req.output_format) ||
    !pipeline?.output_formats.includes(req.output_format)
  )
    add(
      "MODEL_OUTPUT_FORMAT_UNSUPPORTED",
      "output_format",
      "Choose the output format supported by this pipeline and model.",
    );
  for (const [name, value] of Object.entries(req.options)) {
    const rule = model.options_schema[name];
    if (!rule)
      add(
        "MODEL_OPTION_UNSUPPORTED",
        `options.${name}`,
        "This option is not supported by this model.",
      );
    else if (!optionValid(value, rule))
      add(
        "MODEL_OPTION_INVALID",
        `options.${name}`,
        `Enter a valid ${name.replaceAll("_", " ")} value.`,
      );
  }
  const inputErrors = errors.length;
  const profile = context.profiles.find(
    (p) =>
      p.profile_id === req.compute.profile_id &&
      p.enabled &&
      p.authorization_confirmed,
  );
  if (!profile) {
    add(
      "COMPUTE_PROFILE_NOT_FOUND",
      "compute.profile_id",
      "Select an enabled, authorized compute profile.",
    );
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
        "This profile is not authenticated. Check its status in Resources.",
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
