import { describe, expect, it } from "vitest";
import { catalog, makeSnapshot, models, profiles } from "../api/fixtures";
import type {
  CreateJobRequest,
  ModelCapabilities,
  UploadRecord,
} from "../api/types";
import { validateRequest, type ValidationContext } from "./validate";
import { planResources } from "./planner";

const now = Date.parse("2026-11-06T10:20:05Z");
export function upload(
  index = 0,
  overrides: Partial<UploadRecord> = {},
): UploadRecord {
  return {
    contract_version: "1.0",
    upload_id: `upl_${String(index).padStart(32, "a")}`,
    filename: `view-${index}.png`,
    mime_type: "image/png",
    size_bytes: 812345,
    width: 1024,
    height: 1536,
    sha256: "a".repeat(64),
    created_at: new Date(now).toISOString(),
    expires_at: new Date(now + 86400_000).toISOString(),
    ...overrides,
  };
}
export function request(modelId = "mock-i3d-multiview"): CreateJobRequest {
  const text = modelId.startsWith("mock-t");
  return {
    contract_version: "1.0",
    client_request_id: "0b6d7c55-91f2-4d8e-8c3a-5f1e2d9a7b44",
    pipeline_type: modelId.startsWith("mock-t3")
      ? "text_to_3d"
      : text
        ? "text_to_2d"
        : "image_to_3d",
    asset_category: "character",
    model_id: modelId,
    prompt: text ? "Cyan box concept" : null,
    inputs: text
      ? []
      : (modelId === "mock-i3d-single"
          ? (["front"] as const)
          : (["front", "side", "back"] as const)
        ).map((role, i) => ({ upload_id: upload(i).upload_id, role })),
    options: {},
    output_format: modelId.startsWith("mock-t2") ? "png" : "glb",
    compute: { profile_id: "default", accelerator_id: "gpu_t4x2" },
  };
}
function context(): ValidationContext {
  return {
    catalog: structuredClone(catalog),
    models: structuredClone(models),
    profiles: structuredClone(profiles),
    uploads: [upload(0), upload(1), upload(2)],
    snapshot: makeSnapshot("fresh", now),
    now,
  };
}
function codes(req: CreateJobRequest, ctx = context()) {
  return validateRequest(req, ctx).errors.map((e) => e.code);
}
describe("CONTRACTS §8.4 validation matrix", () => {
  it("V-01 rejects images on a text-only model", () => {
    const r = request("mock-t2d-basic");
    r.inputs = [{ upload_id: upload().upload_id, role: "front" }];
    expect(codes(r)).toContain("MODEL_IMAGE_INPUT_NOT_SUPPORTED");
  });
  it("V-02 reports count and both unsupported views", () => {
    const r = request();
    r.model_id = "mock-i3d-single";
    const result = validateRequest(r, context());
    expect(
      result.errors.filter((e) => e.code === "MODEL_IMAGE_ROLE_UNSUPPORTED"),
    ).toHaveLength(2);
    expect(
      result.errors.find((e) => e.code === "MODEL_INPUT_COUNT_EXCEEDED")
        ?.details,
    ).toEqual({ max_images: 1, provided: 3 });
  });
  it("V-03 identifies exactly the missing side view", () => {
    const r = request();
    r.inputs = r.inputs.filter((i) => i.role !== "side");
    expect(
      validateRequest(r, context()).errors.find(
        (e) => e.code === "MODEL_REQUIRED_VIEW_MISSING",
      )?.details,
    ).toEqual({ missing_roles: ["side"] });
  });
  it("V-04 accepts front/side/back and fits dual T4", () => {
    const result = validateRequest(request(), context());
    expect(result.valid).toBe(true);
    expect(result.resource_plan?.fit).toBe("ok");
    expect(result.resource_plan?.required_seconds).toBe(1950);
  });
  it("V-05 rejects a TPU for a CUDA model", () => {
    const r = request();
    r.compute.accelerator_id = "tpu_vm";
    expect(codes(r)).toContain("MODEL_ACCELERATOR_INCOMPATIBLE");
  });
  it("V-06 unknown VRAM warns and does not block", () => {
    const result = validateRequest(request("mock-i3d-single"), context());
    expect(result.valid).toBe(true);
    expect(result.resource_plan?.fit).toBe("unknown");
    expect(result.warnings.map((w) => w.code)).toContain(
      "COMPUTE_VRAM_UNKNOWN",
    );
  });
  it("V-07 missing quota warns and does not block", () => {
    const ctx = context();
    ctx.snapshot = makeSnapshot("quota_missing", now);
    const result = validateRequest(request(), ctx);
    expect(result.valid).toBe(true);
    expect(result.resource_plan?.fit).toBe("unknown");
    expect(result.warnings.map((w) => w.code)).toContain(
      "COMPUTE_QUOTA_UNKNOWN",
    );
  });
  it("V-09 blocks an estimate exceeding session length", () => {
    const ctx = context();
    ctx.models.find(
      (m) => m.model_id === "mock-i3d-multiview",
    )!.runtime.estimated_runtime_seconds = 40000;
    expect(codes(request(), ctx)).toContain("COMPUTE_SESSION_LIMIT_EXCEEDED");
  });
  it("V-11 normalizes a blank required prompt", () => {
    const r = request("mock-t2d-basic");
    r.prompt = "   ";
    expect(codes(r)).toContain("MODEL_PROMPT_REQUIRED");
  });
  it("V-12 rejects WebP for the single-image model", () => {
    const ctx = context();
    ctx.uploads[0].mime_type = "image/webp";
    expect(codes(request("mock-i3d-single"), ctx)).toContain(
      "MODEL_UNSUPPORTED_FILE_FORMAT",
    );
  });
  it("V-13 rejects a 25 MiB reference", () => {
    const ctx = context();
    ctx.uploads[0].size_bytes = 25 * 1024 ** 2;
    expect(codes(request(), ctx)).toContain("MODEL_FILE_TOO_LARGE");
  });
  it("V-14 rejects 256 × 256 reference dimensions", () => {
    const ctx = context();
    ctx.uploads[0].width = ctx.uploads[0].height = 256;
    const e = validateRequest(request(), ctx).errors.find(
      (e) => e.code === "MODEL_IMAGE_DIMENSIONS_INVALID",
    );
    expect(e?.details.actual).toEqual({ width: 256, height: 256 });
  });
  it("V-15 rejects the unsupported weapon category", () => {
    const r = request();
    r.asset_category = "weapon";
    expect(codes(r)).toEqual(["MODEL_CATEGORY_INCOMPATIBLE"]);
  });
  it("V-16 rejects the wrong output format", () => {
    const r = request("mock-t2d-basic");
    r.output_format = "glb";
    expect(codes(r)).toContain("MODEL_OUTPUT_FORMAT_UNSUPPORTED");
  });
  it("V-17 rejects an unsupported option", () => {
    const r = request("mock-i3d-single");
    r.options.texture_resolution = 2048;
    expect(codes(r)).toContain("MODEL_OPTION_UNSUPPORTED");
  });
  it("V-18 blocks insufficient quota", () => {
    const ctx = context();
    ctx.snapshot = makeSnapshot("quota_low", now);
    expect(codes(request(), ctx)).toContain("COMPUTE_QUOTA_INSUFFICIENT");
  });
  it("V-20 rejects planned Text → 3D before model validation", () => {
    expect(codes(request("mock-t3d-basic"))).toEqual([
      "PIPELINE_NOT_AVAILABLE",
    ]);
  });
});
describe("validation and planner boundaries", () => {
  it("aggregates inputs, format, options and compute failures with no resource plan", () => {
    const r = request();
    r.inputs = [];
    r.prompt = "retained";
    r.output_format = "png";
    r.options.seed = -1;
    r.compute.accelerator_id = "tpu_vm";
    const result = validateRequest(r, context());
    expect(result.errors.length).toBeGreaterThanOrEqual(6);
    expect(result.resource_plan).toBeNull();
  });
  it("checks expired/missing uploads, repeated view roles and prompt length", () => {
    const ctx = context(),
      r = request();
    ctx.uploads[0].expires_at = new Date(now - 1).toISOString();
    r.inputs[1].role = "front";
    expect(codes(r, ctx)).toEqual(
      expect.arrayContaining([
        "UPLOAD_NOT_FOUND",
        "MODEL_REQUIRED_VIEW_MISSING",
        "MODEL_IMAGE_ROLE_DUPLICATE",
      ]),
    );
    const text = request("mock-t2d-basic");
    text.prompt = "a".repeat(1001);
    expect(codes(text)).toContain("MODEL_PROMPT_TOO_LONG");
  });
  it("does not mutate requests on model changes", () => {
    const r = request(),
      before = structuredClone(r);
    r.model_id = "mock-i3d-single";
    validateRequest(r, context());
    expect(r.inputs).toEqual(before.inputs);
    expect(r.options).toEqual(before.options);
  });
  it("rejects unknown fields and invalid option values", () => {
    const r = { ...request(), extra: "value" };
    expect(codes(r)).toEqual(["REQUEST_FIELD_INVALID"]);
    const basic = request("mock-t2d-basic");
    basic.options = {
      width: 200,
      seed: 1.5,
      negative_prompt: "a".repeat(1001),
    };
    expect(codes(basic)).toEqual([
      "MODEL_OPTION_INVALID",
      "MODEL_OPTION_INVALID",
      "MODEL_OPTION_INVALID",
    ]);
  });
  it("checks catalog, model, profile and authentication with short circuits", () => {
    const r = request(),
      ctx = context();
    r.model_id = "missing";
    expect(codes(r)).toEqual(["MODEL_NOT_FOUND"]);
    r.model_id = "mock-t2d-basic";
    expect(codes(r)).toEqual(["MODEL_PIPELINE_INCOMPATIBLE"]);
    r.model_id = "mock-i3d-multiview";
    r.compute.profile_id = "missing";
    expect(codes(r)).toContain("COMPUTE_PROFILE_NOT_FOUND");
    r.compute.profile_id = "default";
    ctx.snapshot.authentication_status = "unknown";
    expect(codes(r, ctx)).toContain("COMPUTE_PROFILE_UNAUTHENTICATED");
  });
  it("recommends CPU first for a CPU-preferred model without GPU warnings", () => {
    const ctx = context(),
      m = ctx.models[0];
    const plan = planResources(m, ctx.profiles[0], ctx.snapshot, null);
    expect(plan.accelerator_id).toBe("cpu");
    expect(plan.fit).toBe("ok");
    expect(plan.warnings).toEqual([]);
  });
  it("uses per-device VRAM, skips insufficient candidates, and honors explicit selection", () => {
    const ctx = context(),
      m = ctx.models[3];
    ctx.profiles[0].accelerators[1].vram_bytes_per_device = 1024;
    const plan = planResources(m, ctx.profiles[0], ctx.snapshot, null);
    expect(plan.accelerator_id).toBe("gpu_t4x2");
    expect(plan.candidates[0].reasons[0].code).toBe(
      "COMPUTE_VRAM_INSUFFICIENT",
    );
    const explicit = planResources(
      m,
      ctx.profiles[0],
      ctx.snapshot,
      "gpu_p100",
    );
    expect(explicit.fit).toBe("insufficient");
    expect(explicit.accelerator_id).toBeNull();
  });
  it("handles required multiple devices, unknown runtime and stale quota", () => {
    const ctx = context(),
      m: ModelCapabilities = ctx.models[3];
    m.runtime.multi_gpu = "required";
    m.runtime.estimated_runtime_seconds = null;
    ctx.snapshot.freshness_status.quota = "stale";
    const plan = planResources(m, ctx.profiles[0], ctx.snapshot, null);
    expect(plan.candidates).toHaveLength(1);
    expect(plan.warnings.map((e) => e.code)).toEqual([
      "MODEL_RUNTIME_UNKNOWN",
      "COMPUTE_QUOTA_UNKNOWN",
    ]);
    expect(plan.fit).toBe("unknown");
  });
  it("reports experimental models without blocking", () => {
    const r = request("mock-t2d-styleref");
    const result = validateRequest(r, context());
    expect(result.valid).toBe(true);
    expect(result.warnings.map((w) => w.code)).toEqual(
      expect.arrayContaining(["MODEL_EXPERIMENTAL", "COMPUTE_VRAM_UNKNOWN"]),
    );
  });
});
