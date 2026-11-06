import type { ReactNode } from "react";
import { AlertCircle, CheckCircle2, Inbox, LoaderCircle } from "lucide-react";
import type { ErrorItem, JobStatus, ResourcePlan } from "../api/types";
import { ApiError } from "../api/errors";
import { useI18n } from "../i18n";
export const acceleratorLabels: Record<string, string> = {
  cpu: "CPU",
  gpu_p100: "NVIDIA P100",
  gpu_t4x2: "2 × NVIDIA T4",
  tpu_vm: "TPU VM",
};
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
  const { label } = useI18n();
  return (
    <Badge
      tone={
        status === "completed"
          ? "success"
          : status === "failed"
            ? "danger"
            : "info"
      }
    >
      <span className="status-dot" aria-hidden="true" />
      {label("status", status)}
    </Badge>
  );
}
export function Loading({ children }: { children?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="empty" role="status">
      <LoaderCircle size={24} aria-hidden="true" />
      <p>{children ?? t("copy.loadingWorkspace")}</p>
    </div>
  );
}
export function Failure({ error }: { error: unknown }) {
  const { t } = useI18n();
  if (error instanceof ApiError)
    return (
      <div role="alert">
        <Issues items={error.response.errors} />
      </div>
    );
  return (
    <div className="notice danger" role="alert">
      <AlertCircle size={16} aria-hidden="true" />
      <span>
        {error instanceof Error ? error.message : t("common.requestFailed")}
      </span>
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
  const { errorText } = useI18n();
  return (
    <div className="issues" aria-live="polite">
      {items.map((e, i) => (
        <div
          className={`notice ${e.severity === "error" ? "danger" : "warning"}`}
          key={`${e.code}-${e.field}-${i}`}
        >
          <AlertCircle size={14} aria-hidden="true" />
          <div>
            <span>{errorText(e)}</span>
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
  const { t, label, number, duration } = useI18n();
  return (
    <Panel
      title={t("copy.resourcePlan")}
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
          {plan ? label("fit", plan.fit) : t("copy.awaitingInputs")}
        </Badge>
      }
    >
      <div className="panel-body">
        {plan ? (
          <>
            <div className="plan-title" data-fit={plan.fit}>
              {plan.fit === "ok" ? (
                <CheckCircle2 size={18} aria-hidden="true" />
              ) : (
                <AlertCircle size={18} aria-hidden="true" />
              )}
              {plan.accelerator_id
                ? (acceleratorLabels[plan.accelerator_id] ??
                  plan.accelerator_id)
                : t("copy.noCompatibleAccelerator")}
            </div>
            <dl className="properties">
              <dt>{t("copy.selection")}</dt>
              <dd>{label("selection", plan.selection)}</dd>
              <dt>{t("copy.estimatedJobTime")}</dt>
              <dd>{duration(plan.required_seconds)}</dd>
              <dt>{t("copy.sessionLimit")}</dt>
              <dd>{duration(plan.session_limit_seconds)}</dd>
              <dt>{t("copy.quotaRemaining")}</dt>
              <dd>{duration(plan.quota_remaining_seconds)}</dd>
            </dl>
            <p className="muted small">
              {t("plan.estimate", {
                factor: number(plan.estimate_basis.safety_factor),
                overhead: duration(plan.estimate_basis.overhead_seconds),
              })}
            </p>
          </>
        ) : (
          <p className="muted">
            {t("copy.completeTheRequiredInputsToEstimateComputeCompatibility")}
          </p>
        )}
      </div>
    </Panel>
  );
}
