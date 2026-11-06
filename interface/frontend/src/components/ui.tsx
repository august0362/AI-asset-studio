import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Inbox, LoaderCircle } from "lucide-react";
import type { ErrorItem, JobStatus, ResourcePlan } from "../api/types";
import { errorMessage } from "../api/errors";
export const categoryLabels = {
  character: "Character",
  skill_effect: "Skill / VFX",
  weapon: "Weapon",
  companion: "Companion",
};
export const pipelineLabels = {
  text_to_2d: "Text → 2D",
  image_to_3d: "Image → 3D",
  text_to_3d: "Text → 3D",
};
export const acceleratorLabels: Record<string, string> = {
  cpu: "CPU",
  gpu_p100: "NVIDIA P100",
  gpu_t4x2: "2 × NVIDIA T4",
  tpu_vm: "TPU VM",
};
export function date(value: string | null) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "Unknown";
}
export function number(value: number | null, digits = 1) {
  return value === null
    ? "Unknown"
    : new Intl.NumberFormat(undefined, {
        maximumFractionDigits: digits,
      }).format(value);
}
export function bytes(value: number | null) {
  return value === null ? "Unknown" : `${number(value / 1024 ** 3)} GiB`;
}
export function duration(value: number | null) {
  return value === null
    ? "Unknown"
    : value >= 3600
      ? `${number(value / 3600)} h`
      : `${number(value / 60)} min`;
}
export function Panel({
  title,
  extra,
  children,
  className = "",
}: {
  title: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-heading">
        <h2>{title}</h2>
        {extra}
      </header>
      {children}
    </section>
  );
}
export function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Status({ status }: { status: JobStatus }) {
  return (
    <Badge
      tone={
        status === "completed"
          ? "success"
          : status === "failed"
            ? "danger"
            : "cyan"
      }
    >
      <span className="status-dot" aria-hidden="true" />
      {status}
    </Badge>
  );
}
export function Loading({
  children = "Loading workspace…",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="empty" role="status">
      <LoaderCircle size={24} aria-hidden="true" />
      <p>{children}</p>
    </div>
  );
}
export function Failure({ error }: { error: unknown }) {
  return (
    <div className="notice danger" role="alert">
      <AlertCircle size={16} aria-hidden="true" />
      <span>{errorMessage(error)}</span>
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={32} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Issues({ items }: { items: ErrorItem[] }) {
  return (
    <div className="issues" aria-live="polite">
      {items.map((e, i) => (
        <div
          className={`notice ${e.severity === "error" ? "danger" : "warning"}`}
          key={`${e.code}-${e.field}-${i}`}
        >
          <AlertCircle size={14} aria-hidden="true" />
          <div>
            <span>{e.message}</span>
            <code>
              {e.code}
              {e.field ? ` · ${e.field}` : ""}
            </code>
          </div>
        </div>
      ))}
    </div>
  );
}
export function PlanPanel({ plan }: { plan: ResourcePlan | null }) {
  return (
    <Panel
      title="Resource plan"
      extra={
        <Badge
          tone={
            plan?.fit === "ok"
              ? "success"
              : plan?.fit === "insufficient"
                ? "danger"
                : "warning"
          }
        >
          {plan?.fit ?? "Awaiting inputs"}
        </Badge>
      }
    >
      <div className="panel-body">
        {plan ? (
          <>
            <div className="plan-title">
              <CheckCircle2 size={18} aria-hidden="true" />
              {plan.accelerator_id
                ? (acceleratorLabels[plan.accelerator_id] ??
                  plan.accelerator_id)
                : "No compatible accelerator"}
            </div>
            <dl className="properties">
              <dt>Selection</dt>
              <dd>{plan.selection.replace("_", " ")}</dd>
              <dt>Estimated job time</dt>
              <dd>{duration(plan.required_seconds)}</dd>
              <dt>Session limit</dt>
              <dd>{duration(plan.session_limit_seconds)}</dd>
              <dt>Quota remaining</dt>
              <dd>{duration(plan.quota_remaining_seconds)}</dd>
            </dl>
            <p className="muted small">
              Estimate: runtime × {plan.estimate_basis.safety_factor} +{" "}
              {duration(plan.estimate_basis.overhead_seconds)} overhead. Mock
              catalog; hardware limits are provisional.
            </p>
          </>
        ) : (
          <p className="muted">
            Complete the required inputs to estimate compute compatibility.
          </p>
        )}
      </div>
    </Panel>
  );
}
