import { useI18n } from "../../i18n";
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
  Empty,
  Failure,
  Issues,
  Loading,
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
  const { t, label, date } = useI18n();
  const freshness = snapshot.freshness_status[group];
  return (
    <div className="provenance">
      <Badge tone={freshness === "fresh" ? "success" : "warning"}>
        {label("freshness", freshness)}
      </Badge>
      <span>
        {t("resource.source", {
          source: label("source", snapshot.source[group]),
        })}
      </span>
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
  unit,
}: {
  label: string;
  value: number | null;
  max?: number | null;
  unit?: string;
}) {
  const { t, number } = useI18n();
  const percent =
    value === null || !max
      ? null
      : Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="gauge">
      <div className="flex-between">
        <span>{label}</span>
        <strong>
          {value === null
            ? t("common.unknown")
            : `${number(value)}${unit ?? t("unit.percent")}`}
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
  const { t, label, number, date, duration, bytes, quantity } = useI18n();
  return (
    <>
      <div className="resource-top-grid">
        <Panel
          title={t("copy.weeklyComputeQuota")}
          extra={<Badge>{t("common.mock")}</Badge>}
        >
          <div className="panel-body quota-grid">
            <div>
              <h3>{t("copy.gpuAllocation")}</h3>
              <div className="big-metric">
                {number(s.gpu_quota_remaining_hours)}
                <small>{t("resource.remainingHours")}</small>
              </div>
              <Gauge
                label={t("copy.gpuQuotaUsed")}
                value={s.gpu_quota_used_hours}
                max={s.gpu_quota_total_hours}
                unit={` ${t("unit.hours")}`}
              />
              <p className="muted small">
                {t("resource.quotaTotals", {
                  total: number(s.gpu_quota_total_hours),
                  used: number(s.gpu_quota_used_hours),
                  remaining: number(s.gpu_quota_remaining_hours),
                  unit: t("unit.hours"),
                })}
              </p>
            </div>
            <div>
              <h3>{t("copy.tpuAllocation")}</h3>
              <div className="big-metric">
                {number(s.tpu_quota_remaining_hours)}
                <small>{t("resource.remainingHours")}</small>
              </div>
              <p className="muted">
                {t("resource.quotaUsed", {
                  total: number(s.tpu_quota_total_hours),
                  used: number(s.tpu_quota_used_hours),
                  unit: t("unit.hours"),
                })}
              </p>
              <Badge tone="warning">
                {t("copy.tpuTelemetryUnsupportedInM1")}
              </Badge>
            </div>
            <p className="quota-reset">
              {t("resource.reset", { date: date(s.quota_reset_at) })}
            </p>
          </div>
          <Provenance snapshot={s} group="quota" />
        </Panel>
        <Panel
          title={t("copy.sessionStatus")}
          extra={
            <Badge tone={s.session_status === "running" ? "success" : ""}>
              {label("session", s.session_status)}
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
                : t("copy.noActiveSession")}
            </h3>
            <dl className="properties">
              <dt>{t("copy.observedStart")}</dt>
              <dd>{date(s.session_started_at)}</dd>
              <dt>{t("copy.estimatedTimeRemaining")}</dt>
              <dd>{duration(s.estimated_session_remaining_seconds)}</dd>
            </dl>
            <p className="small muted">
              {t(
                "copy.remainingTimeIsAnEstimateFromKnownSessionAndQuotaLimits",
              )}
            </p>
          </div>
          <Provenance snapshot={s} group="session" />
        </Panel>
      </div>
      <div className="section-title">
        <h2>{t("copy.notebookTelemetry")}</h2>
        <Badge>{t("copy.mockNotAKaggleConnection")}</Badge>
      </div>
      <div className="telemetry-grid">
        <Panel
          title={t("copy.hostResources")}
          extra={<Cpu size={17} aria-hidden="true" />}
        >
          <div className="panel-body">
            <Gauge
              label={t("copy.cpuUtilization")}
              value={s.cpu_utilization_percent}
            />
            <Gauge
              label={t("copy.ramUsed")}
              value={
                s.ram_used_bytes === null ? null : s.ram_used_bytes / 1024 ** 3
              }
              max={
                s.ram_total_bytes === null
                  ? null
                  : s.ram_total_bytes / 1024 ** 3
              }
              unit={` ${t("unit.gib")}`}
            />
            <div className="flex-between muted small">
              <span>{t("copy.ramTotal")}</span>
              <span>{bytes(s.ram_total_bytes)}</span>
            </div>
          </div>
          <Provenance snapshot={s} group="host" />
        </Panel>
        {s.gpu_devices.length ? (
          s.gpu_devices.map((g) => (
            <Panel
              title={t("resource.gpuTitle", {
                index: number(g.index, 0),
                name: g.name ?? t("copy.unknownDevice"),
              })}
              key={g.index}
              extra={
                <Badge tone={g.status === "available" ? "success" : "warning"}>
                  {label("device", g.status)}
                </Badge>
              }
            >
              <div className="panel-body">
                <Gauge
                  label={t("resource.gpuUtilization", {
                    index: number(g.index, 0),
                  })}
                  value={g.utilization_percent}
                />
                <Gauge
                  label={t("resource.gpuVram", { index: number(g.index, 0) })}
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
                  unit={` ${t("unit.gib")}`}
                />
                <dl className="properties">
                  <dt>{t("copy.vramTotal")}</dt>
                  <dd>{bytes(g.vram_total_bytes)}</dd>
                  <dt>{t("copy.temperature")}</dt>
                  <dd>
                    {g.temperature_c === null
                      ? t("common.unknown")
                      : quantity(g.temperature_c, "unit.celsius")}
                  </dd>
                </dl>
              </div>
              <Provenance snapshot={s} group="gpu" />
            </Panel>
          ))
        ) : (
          <Panel title={t("copy.gpuTelemetry")}>
            <div className="panel-body">
              <p className="muted">
                {t("copy.noSessionGpuTelemetryIsNotApplicable")}
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
  const { t, label, number, date, errorText } = useI18n();
  const [params, setParams] = useSearchParams(),
    queryClient = useQueryClient();
  const scenario = scenarios.includes(params.get("scenario") as Scenario)
    ? (params.get("scenario") as Scenario)
    : "fresh";
  const modelId = params.get("model") ?? "mock-i3d-multiview";
  const data = useStudioData(
      params.get("profile"),
      isMock ? scenario : undefined,
    ),
    [refreshAt, setRefreshAt] = useState(0),
    [clock, setClock] = useState(Date.now()),
    [refreshing, setRefreshing] = useState(false),
    [error, setError] = useState<unknown>();
  const profileId = data.profileId;
  useEffect(() => {
    setError(undefined);
  }, [profileId]);
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
    if (!profileId) return;
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
  if (!data.profiles || !data.models)
    return <Loading>{t("copy.loadingComputeResources")}</Loading>;
  const profile = data.profiles.find((p) => p.profile_id === profileId),
    model = data.models.find((m) => m.model_id === modelId);
  const plan =
    profile && model && data.snapshot
      ? planResources(model, profile, data.snapshot, null)
      : null;
  const remaining = Math.max(0, 60 - Math.floor((clock - refreshAt) / 1000));
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="breadcrumb">
            {t("copy.workspaceComputeMonitoring")}
          </div>
          <h1>{t("copy.kaggleResources")}</h1>
        </div>
        <Badge tone="secondary">
          {isMock
            ? t("copy.mockSimulatedResourceData")
            : t("copy.httpResourceData")}
        </Badge>
      </div>
      <div className="resource-controls">
        <label className="inline-field">
          {t("copy.authorizedProfile")}
          <select
            name="resource-profile"
            value={profileId ?? ""}
            onChange={(e) => update("profile", e.target.value)}
          >
            {!data.profiles.some((p) => p.profile_id === profileId) && (
              <option value={profileId ?? ""} disabled>
                {profileId || t("compute.noEnabledProfiles")}
              </option>
            )}
            {data.profiles.map((p) => (
              <option
                key={p.profile_id}
                value={p.profile_id}
                disabled={!p.enabled}
              >
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
        {isMock && (
          <label className="inline-field">
            {t("copy.developmentScenario")}
            <select
              name="mock-scenario"
              value={scenario}
              onChange={(e) => update("scenario", e.target.value)}
            >
              {scenarios.map((s) => (
                <option key={s} value={s}>
                  {label("scenario", s)}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          onClick={() => void refresh()}
          disabled={!profileId || refreshing || remaining > 0}
        >
          <RefreshCw size={14} aria-hidden="true" />
          {refreshing
            ? t("copy.refreshing")
            : remaining > 0
              ? t("resource.refreshIn", { seconds: number(remaining, 0) })
              : t("copy.refreshSample")}
        </button>
      </div>
      {!data.profiles.some((p) => p.enabled) ? (
        <Empty title={t("compute.noEnabledProfiles")}>
          {t("compute.noEnabledProfilesHelp")}
        </Empty>
      ) : data.snapshotError ? (
        <Failure error={data.snapshotError} />
      ) : !data.snapshot ? (
        <Loading>{t("copy.loadingComputeResources")}</Loading>
      ) : (
        <>
          <div className="profile-banner">
            <div className="profile-emblem">
              <ShieldCheck size={24} aria-hidden="true" />
            </div>
            <div>
              <h2>{profile?.display_name ?? profileId}</h2>
              <p>
                {t("resource.selected", {
                  owner: profile?.owner_label,
                  mode: label("mode", profile?.mode ?? "mock"),
                })}
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
              {label("authentication", data.snapshot.authentication_status)}
            </Badge>
            <Badge>
              {profile?.authorization_confirmed
                ? t("copy.authorizedProfile")
                : t("copy.authorizationRequired")}
            </Badge>
          </div>
          {error && <Failure error={error} />}
          <SnapshotDashboard snapshot={data.snapshot} />
          <div className="resource-plan-grid">
            <div>
              <div className="section-title">
                <h2>{t("copy.modelCompatibility")}</h2>
                <label className="field">
                  <span className="sr-only">
                    {t("copy.modelForResourcePlan")}
                  </span>
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
              <Panel title={t("copy.compatibleAccelerators")}>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("copy.accelerator")}</th>
                        <th>{t("copy.fit")}</th>
                        <th>{t("copy.reasons")}</th>
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
                              {label("fit", c.fit)}
                            </Badge>
                          </td>
                          <td>
                            {c.reasons.length
                              ? c.reasons.map((r) => errorText(r)).join(" ")
                              : t("copy.meetsKnownRequirements")}
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
            {t("resource.snapshotNote", {
              date: date(data.snapshot.observed_at.snapshot),
            })}
          </p>
        </>
      )}
    </>
  );
}
