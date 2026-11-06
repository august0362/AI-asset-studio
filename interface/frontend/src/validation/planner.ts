import type {
  ComputeProfile,
  ErrorItem,
  KaggleResourceSnapshot,
  ModelCapabilities,
  ResourcePlan,
} from "../api/types";
import { validationIssue as issue } from "../i18n/validation";

export function planResources(
  model: ModelCapabilities,
  profile: ComputeProfile,
  snapshot: KaggleResourceSnapshot,
  selected: string | null,
): ResourcePlan {
  const runtime = model.runtime;
  let eligible = runtime.supported_accelerators.flatMap((kind) =>
    profile.accelerators.filter((a) => a.kind === kind),
  );
  if (runtime.multi_gpu === "required")
    eligible = eligible.filter((a) => a.device_count >= 2);
  if (selected)
    eligible = eligible.filter((a) => a.accelerator_id === selected);
  const required =
    runtime.estimated_runtime_seconds === null
      ? null
      : Math.ceil(runtime.estimated_runtime_seconds * 1.5 + 600);
  const candidates = eligible.map((a) => {
    const reasons: ErrorItem[] = [];
    const add = (e: ErrorItem) => reasons.push(e);
    if (a.kind === "gpu_cuda") {
      if (
        runtime.minimum_gpu_vram_bytes !== null &&
        a.vram_bytes_per_device !== null &&
        runtime.minimum_gpu_vram_bytes > a.vram_bytes_per_device
      )
        add(issue("COMPUTE_VRAM_INSUFFICIENT", "compute.accelerator_id"));
      else if (
        a.vram_bytes_per_device === null ||
        model.unknown_requirements.includes("runtime.minimum_gpu_vram_bytes")
      )
        add(issue("COMPUTE_VRAM_UNKNOWN", "compute.accelerator_id", "warning"));
    }
    if (required === null)
      add(issue("MODEL_RUNTIME_UNKNOWN", "model_id", "warning"));
    else if (required > a.max_session_seconds)
      add(issue("COMPUTE_SESSION_LIMIT_EXCEEDED", "compute.accelerator_id"));
    if (a.kind !== "cpu") {
      const quota =
        a.kind === "tpu"
          ? snapshot.tpu_quota_remaining_hours
          : snapshot.gpu_quota_remaining_hours;
      if (quota === null || snapshot.freshness_status.quota !== "fresh")
        add(issue("COMPUTE_QUOTA_UNKNOWN", "compute.profile_id", "warning"));
      else if (required !== null && required > quota * 3600)
        add(
          issue(
            "COMPUTE_QUOTA_INSUFFICIENT",
            "compute.accelerator_id",
            "error",
            {},
            true,
          ),
        );
    }
    const fit = reasons.some((e) => e.severity === "error")
      ? "insufficient"
      : reasons.length
        ? "unknown"
        : "ok";
    return {
      accelerator_id: a.accelerator_id,
      fit: fit as ResourcePlan["fit"],
      reasons,
    };
  });
  const chosen =
    candidates.find((c) => c.fit === "ok") ??
    candidates.find((c) => c.fit === "unknown");
  const result = chosen ?? candidates[0];
  const accelerator = profile.accelerators.find(
    (a) => a.accelerator_id === result?.accelerator_id,
  );
  const quota =
    accelerator?.kind === "cpu"
      ? null
      : accelerator?.kind === "tpu"
        ? snapshot.tpu_quota_remaining_hours
        : snapshot.gpu_quota_remaining_hours;
  return {
    contract_version: "1.0",
    profile_id: profile.profile_id,
    accelerator_id: chosen?.accelerator_id ?? null,
    selection: selected ? "user_selected" : "recommended",
    fit: chosen?.fit ?? "insufficient",
    required_seconds: required,
    estimate_basis: {
      estimated_runtime_seconds: runtime.estimated_runtime_seconds,
      safety_factor: 1.5,
      overhead_seconds: 600,
    },
    session_limit_seconds: accelerator?.max_session_seconds ?? null,
    quota_remaining_seconds:
      quota == null || snapshot.freshness_status.quota !== "fresh"
        ? null
        : quota * 3600,
    candidates,
    warnings: result?.reasons.filter((e) => e.severity === "warning") ?? [],
    errors: result?.reasons.filter((e) => e.severity === "error") ?? [
      issue("MODEL_ACCELERATOR_INCOMPATIBLE", "compute.accelerator_id"),
    ],
  };
}
