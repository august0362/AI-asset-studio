import catalogJson from "../../tests/fixtures/contracts/catalog.json";
import modelsJson from "../../tests/fixtures/contracts/models.json";
import profilesJson from "../../tests/fixtures/contracts/profiles.json";
import snapshotJson from "../../tests/fixtures/contracts/snapshot.json";
import type {
  Catalog,
  ComputeProfile,
  KaggleResourceSnapshot,
  ModelCapabilities,
  Scenario,
} from "./types";
import { issue } from "./errors";
export const catalog = catalogJson as Catalog;
export const models = modelsJson.models as unknown as ModelCapabilities[];
export const profiles = profilesJson.profiles as ComputeProfile[];
export function makeSnapshot(
  scenario: Scenario,
  now = Date.now(),
): KaggleResourceSnapshot {
  const s = structuredClone(snapshotJson) as KaggleResourceSnapshot;
  const stamp = new Date(now).toISOString();
  for (const key of Object.keys(
    s.observed_at,
  ) as (keyof typeof s.observed_at)[])
    s.observed_at[key] = stamp;
  s.session_started_at = new Date(now - 2100_000).toISOString();
  if (scenario === "no_session") {
    s.session_status = "none";
    s.session_started_at = null;
    s.estimated_session_remaining_seconds = null;
    s.accelerator_type = null;
    s.cpu_utilization_percent = null;
    s.ram_used_bytes = null;
    s.ram_total_bytes = null;
    s.gpu_devices = [];
    for (const group of ["host", "gpu"] as const) {
      s.freshness_status[group] = "not_applicable";
      s.source[group] = "none";
      s.observed_at[group] = null;
    }
  }
  if (scenario === "quota_missing") {
    s.gpu_quota_total_hours =
      s.gpu_quota_used_hours =
      s.gpu_quota_remaining_hours =
        null;
    s.freshness_status.quota = "unavailable";
    s.source.quota = "none";
    s.observed_at.quota = null;
    s.error.push(
      issue(
        "COMPUTE_QUOTA_UNKNOWN",
        "compute.profile_id",
        "Quota was not reported in this mock scenario.",
        "warning",
      ),
    );
  }
  if (scenario === "telemetry_stale") {
    for (const group of ["host", "gpu"] as const) {
      s.freshness_status[group] = "stale";
      s.observed_at[group] = new Date(now - 120_000).toISOString();
    }
    s.error.push(
      issue(
        "COMPUTE_TELEMETRY_STALE",
        "host",
        "Last telemetry sample is 120 seconds old. These values are stale.",
        "warning",
        { age_seconds: 120 },
      ),
    );
  }
  if (scenario === "telemetry_unavailable") {
    s.cpu_utilization_percent = null;
    s.ram_used_bytes = null;
    s.ram_total_bytes = null;
    s.gpu_devices = s.gpu_devices.map((g) => ({
      ...g,
      utilization_percent: null,
      vram_used_bytes: null,
      vram_total_bytes: null,
      temperature_c: null,
      status: "unavailable",
    }));
    for (const group of ["host", "gpu"] as const) {
      s.freshness_status[group] = "unavailable";
      s.source[group] = "none";
      s.observed_at[group] = null;
    }
    s.error.push(
      issue(
        "COMPUTE_TELEMETRY_UNAVAILABLE",
        "host",
        "The mock session is running, but no telemetry sample is available.",
        "warning",
      ),
    );
  }
  if (scenario === "gpu_split") {
    s.gpu_devices[1].utilization_percent = 23;
    s.gpu_devices[1].vram_used_bytes = 3221225472;
    s.gpu_devices[1].temperature_c = 46;
  }
  if (scenario === "quota_low") {
    s.gpu_quota_used_hours = 29.7;
    s.gpu_quota_remaining_hours = 0.3;
    s.estimated_session_remaining_seconds = 1080;
  }
  return s;
}
