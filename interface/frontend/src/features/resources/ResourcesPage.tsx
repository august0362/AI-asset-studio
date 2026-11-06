import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  Cpu,
  Database,
  Fingerprint,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { api, isMock } from "../../api/client";
import { useStudioData } from "../../api/queries";
import {
  scenarios,
  type KaggleResourceSnapshot,
  type MetricGroup,
  type Scenario,
} from "../../api/types";
import { planResources } from "../../validation/planner";
import {
  acceleratorLabels,
  Badge,
  bytes,
  date,
  duration,
  Failure,
  Issues,
  Loading,
  number,
  Panel,
  PlanPanel,
} from "../../components/ui";

function Provenance({
  snapshot,
  group,
}: {
  snapshot: KaggleResourceSnapshot;
  group: MetricGroup;
}) {
  const freshness = snapshot.freshness_status[group];
  return (
    <div className="provenance">
      <Badge tone={freshness === "fresh" ? "success" : "warning"}>
        {freshness.replaceAll("_", " ")}
      </Badge>
      <span>Source: {snapshot.source[group].replaceAll("_", " ")}</span>
      <time dateTime={snapshot.observed_at[group] ?? undefined}>
        {date(snapshot.observed_at[group])}
      </time>
    </div>
  );
}
export function Gauge({
  label,
  value,
  max = 100,
  unit = "%",
}: {
  label: string;
  value: number | null;
  max?: number | null;
  unit?: string;
}) {
  const percent =
    value === null || !max
      ? null
      : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="gauge">
      <div className="flex-between">
        <span>{label}</span>
        <strong>
          {value === null ? "Unknown" : `${number(value)}${unit}`}
        </strong>
      </div>
      {percent !== null ? (
        <div
          className="gauge-track"
          role="meter"
          aria-label={label}
          aria-valuenow={value!}
          aria-valuemin={0}
          aria-valuemax={max ?? 100}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
      ) : (
        <div className="gauge-track unknown" aria-hidden="true" />
      )}
    </div>
  );
}
export function SnapshotDashboard({
  snapshot: s,
}: {
  snapshot: KaggleResourceSnapshot;
}) {
  return (
    <>
      <div className="resource-top-grid">
        <Panel title="Weekly compute quota" extra={<Badge>MOCK</Badge>}>
          <div className="panel-body quota-grid">
            <div>
              <h3>GPU allocation</h3>
              <div className="big-metric">
                {number(s.gpu_quota_remaining_hours)}
                <small> hours remaining</small>
              </div>
              <Gauge
                label="GPU quota used"
                value={s.gpu_quota_used_hours}
                max={s.gpu_quota_total_hours}
                unit=" h"
              />
              <p className="muted small">
                Total: {number(s.gpu_quota_total_hours)} h · Used:{" "}
                {number(s.gpu_quota_used_hours)} h · Remaining:{" "}
                {number(s.gpu_quota_remaining_hours)} h
              </p>
            </div>
            <div>
              <h3>TPU allocation</h3>
              <div className="big-metric">
                {number(s.tpu_quota_remaining_hours)}
                <small> hours remaining</small>
              </div>
              <p className="muted">
                Total: {number(s.tpu_quota_total_hours)} h · Used:{" "}
                {number(s.tpu_quota_used_hours)} h
              </p>
              <Badge tone="warning">TPU telemetry · Unsupported in M1</Badge>
            </div>
            <p className="quota-reset">Quota reset: {date(s.quota_reset_at)}</p>
          </div>
          <Provenance snapshot={s} group="quota" />
        </Panel>
        <Panel
          title="Session status"
          extra={
            <Badge tone={s.session_status === "running" ? "success" : ""}>
              {s.session_status}
            </Badge>
          }
        >
          <div className="panel-body">
            <div className="session-icon">
              <Database size={24} aria-hidden="true" />
            </div>
            <h3>
              {s.accelerator_type
                ? (acceleratorLabels[s.accelerator_type] ?? s.accelerator_type)
                : "No active session"}
            </h3>
            <dl className="properties">
              <dt>Observed start</dt>
              <dd>{date(s.session_started_at)}</dd>
              <dt>Estimated time remaining</dt>
              <dd>{duration(s.estimated_session_remaining_seconds)}</dd>
            </dl>
            <p className="small muted">
              Remaining time is an estimate from known session and quota limits.
            </p>
          </div>
          <Provenance snapshot={s} group="session" />
        </Panel>
      </div>
      <div className="section-title">
        <h2>Notebook telemetry</h2>
        <Badge>MOCK · Not a Kaggle connection</Badge>
      </div>
      <div className="telemetry-grid">
        <Panel
          title="Host resources"
          extra={<Cpu size={17} aria-hidden="true" />}
        >
          <div className="panel-body">
            <Gauge label="CPU utilization" value={s.cpu_utilization_percent} />
            <Gauge
              label="RAM used"
              value={
                s.ram_used_bytes === null ? null : s.ram_used_bytes / 1024 ** 3
              }
              max={
                s.ram_total_bytes === null
                  ? null
                  : s.ram_total_bytes / 1024 ** 3
              }
              unit=" GiB"
            />
            <div className="flex-between muted small">
              <span>RAM total</span>
              <span>{bytes(s.ram_total_bytes)}</span>
            </div>
          </div>
          <Provenance snapshot={s} group="host" />
        </Panel>
        {s.gpu_devices.length ? (
          s.gpu_devices.map((g) => (
            <Panel
              title={`GPU${g.index} · ${g.name ?? "Unknown device"}`}
              key={g.index}
              extra={
                <Badge tone={g.status === "available" ? "success" : "warning"}>
                  {g.status}
                </Badge>
              }
            >
              <div className="panel-body">
                <Gauge
                  label={`GPU${g.index} utilization`}
                  value={g.utilization_percent}
                />
                <Gauge
                  label={`GPU${g.index} VRAM used`}
                  value={
                    g.vram_used_bytes === null
                      ? null
                      : g.vram_used_bytes / 1024 ** 3
                  }
                  max={
                    g.vram_total_bytes === null
                      ? null
                      : g.vram_total_bytes / 1024 ** 3
                  }
                  unit=" GiB"
                />
                <dl className="properties">
                  <dt>VRAM total</dt>
                  <dd>{bytes(g.vram_total_bytes)}</dd>
                  <dt>Temperature</dt>
                  <dd>
                    {g.temperature_c === null
                      ? "Unknown"
                      : `${number(g.temperature_c)} °C`}
                  </dd>
                </dl>
              </div>
              <Provenance snapshot={s} group="gpu" />
            </Panel>
          ))
        ) : (
          <Panel title="GPU telemetry">
            <div className="panel-body">
              <p className="muted">
                No session · GPU telemetry is not applicable.
              </p>
            </div>
            <Provenance snapshot={s} group="gpu" />
          </Panel>
        )}
      </div>
      <Issues items={s.error} />
    </>
  );
}
export function ResourcesPage() {
  const [params, setParams] = useSearchParams(),
    queryClient = useQueryClient();
  const scenario = scenarios.includes(params.get("scenario") as Scenario)
    ? (params.get("scenario") as Scenario)
    : "fresh";
  const profileId = params.get("profile") ?? "default",
    modelId = params.get("model") ?? "mock-i3d-multiview";
  const data = useStudioData(profileId, isMock ? scenario : undefined),
    [refreshAt, setRefreshAt] = useState(0),
    [clock, setClock] = useState(Date.now()),
    [refreshing, setRefreshing] = useState(false),
    [error, setError] = useState<unknown>();
  useEffect(() => {
    const id = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next);
  }
  async function refresh() {
    setRefreshing(true);
    setError(undefined);
    try {
      const snapshot = await api.snapshot(profileId, true);
      queryClient.setQueryData(
        ["snapshot", profileId, isMock ? scenario : undefined],
        snapshot,
      );
      setRefreshAt(Date.now());
    } catch (e) {
      setError(e);
    } finally {
      setRefreshing(false);
    }
  }
  if (data.error) return <Failure error={data.error} />;
  if (!data.profiles || !data.models || !data.snapshot)
    return <Loading>Loading compute resources…</Loading>;
  const profile = data.profiles.find((p) => p.profile_id === profileId),
    model = data.models.find((m) => m.model_id === modelId);
  const plan =
    profile && model
      ? planResources(model, profile, data.snapshot, null)
      : null;
  const remaining = Math.max(0, 60 - Math.floor((clock - refreshAt) / 1000));
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="breadcrumb">Workspace / Compute monitoring</div>
          <h1>Kaggle resources</h1>
        </div>
        <Badge tone="violet">
          {isMock ? "MOCK · Simulated resource data" : "HTTP resource data"}
        </Badge>
      </div>
      <div className="resource-controls">
        <label className="inline-field">
          Authorized profile
          <select
            name="resource-profile"
            value={profileId}
            onChange={(e) => update("profile", e.target.value)}
          >
            {data.profiles
              .filter((p) => p.enabled && p.authorization_confirmed)
              .map((p) => (
                <option key={p.profile_id} value={p.profile_id}>
                  {p.display_name}
                </option>
              ))}
          </select>
        </label>
        {isMock && (
          <label className="inline-field">
            Development scenario
            <select
              name="mock-scenario"
              value={scenario}
              onChange={(e) => update("scenario", e.target.value)}
            >
              {scenarios.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          onClick={() => void refresh()}
          disabled={refreshing || remaining > 0}
        >
          <RefreshCw size={14} aria-hidden="true" />
          {refreshing
            ? "Refreshing…"
            : remaining > 0
              ? `Refresh in ${remaining} s`
              : "Refresh sample"}
        </button>
      </div>
      <div className="profile-banner">
        <div className="profile-emblem">
          <ShieldCheck size={24} aria-hidden="true" />
        </div>
        <div>
          <h2>{profile?.display_name ?? profileId}</h2>
          <p>
            {profile?.owner_label} · Explicitly selected ·{" "}
            {profile?.mode.toUpperCase()}
          </p>
        </div>
        <Badge
          tone={
            data.snapshot.authentication_status === "authenticated"
              ? "success"
              : "danger"
          }
        >
          <Fingerprint size={13} aria-hidden="true" />
          {data.snapshot.authentication_status}
        </Badge>
        <Badge>
          {profile?.authorization_confirmed
            ? "Authorized profile"
            : "Authorization required"}
        </Badge>
      </div>
      {error && <Failure error={error} />}
      <SnapshotDashboard snapshot={data.snapshot} />
      <div className="resource-plan-grid">
        <div>
          <div className="section-title">
            <h2>Model compatibility</h2>
            <label className="field">
              <span className="sr-only">Model for resource plan</span>
              <select
                name="plan-model"
                value={modelId}
                onChange={(e) => update("model", e.target.value)}
              >
                {data.models
                  .filter((m) => m.availability !== "planned")
                  .map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.display_name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <Panel title="Compatible accelerators">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Accelerator</th>
                    <th>Fit</th>
                    <th>Reasons</th>
                  </tr>
                </thead>
                <tbody>
                  {plan?.candidates.map((c) => (
                    <tr key={c.accelerator_id}>
                      <td>
                        {acceleratorLabels[c.accelerator_id] ??
                          c.accelerator_id}
                      </td>
                      <td>
                        <Badge
                          tone={
                            c.fit === "ok"
                              ? "success"
                              : c.fit === "insufficient"
                                ? "danger"
                                : "warning"
                          }
                        >
                          {c.fit}
                        </Badge>
                      </td>
                      <td>
                        {c.reasons.length
                          ? c.reasons.map((r) => r.message).join(" ")
                          : "Meets known requirements"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Issues
              items={[...(plan?.errors ?? []), ...(plan?.warnings ?? [])]}
            />
          </Panel>
        </div>
        <PlanPanel plan={plan} />
      </div>
      <p className="small muted">
        Snapshot: {date(data.snapshot.observed_at.snapshot)}. Every metric group
        carries its own source and freshness. Mock samples are simulated,
        including timestamps. Hardware limits remain provisional until M3.
      </p>
    </>
  );
}
