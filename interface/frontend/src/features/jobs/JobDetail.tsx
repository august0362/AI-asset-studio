import { useI18n } from "../../i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { RefreshCw, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import { useJob } from "../../api/queries";
import {
  ArtifactPreview,
  DownloadButton,
} from "../../components/ArtifactPreview";
import {
  Failure,
  Issues,
  Loading,
  Panel,
  PlanPanel,
  Status,
} from "../../components/ui";
import { AutoRunToggle, GroupNote, QueueBadge, RunButton } from "./RunControl";
export function JobDetail({ id }: { id: string }) {
  const {
    t,
    label,
    date,
    duration,
    categoryLabels,
    pipelineLabels,
    intlLocale,
  } = useI18n();
  const job = useJob(id),
    queryClient = useQueryClient(),
    navigate = useNavigate();
  const status = useQuery({
    queryKey: ["status", id],
    queryFn: () => api.jobStatus(id),
    refetchInterval: (q) =>
      q.state.data && ["completed", "failed"].includes(q.state.data.status)
        ? false
        : 2000,
  });
  const logs = useQuery({
    queryKey: ["logs", id],
    queryFn: () => api.logs(id),
    refetchInterval: (q) => (q.state.data?.complete ? false : 2000),
  });
  const retry = useMutation({
    mutationFn: () => api.retryJob(id, crypto.randomUUID()),
    onSuccess: (j) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/jobs/${j.job_id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteJob(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.removeQueries({ queryKey: ["job", id] });
      navigate("/jobs");
    },
  });
  if (job.error) return <Failure error={job.error} />;
  if (!job.data) return <Loading>{t("copy.loadingJobDetails")}</Loading>;
  const j = job.data,
    primary = j.artifacts.find((a) => a.is_primary),
    terminal = ["completed", "failed"].includes(j.status),
    queue = j.scheduling?.queue_state ?? null,
    // §14.6: terminal, held or waiting jobs (a waiting character batch job stays)
    deletable =
      terminal || queue === "held" || (queue === "waiting" && !j.request.batch);
  return (
    <div className="job-detail-stack">
      {/* A finished job shows its image first, then its details (owner, 2026-11-07). */}
      {primary && (
        <Panel title={t("copy.jobArtifacts")}>
          {j.request.batch ? (
            j.artifacts.map((a) => (
              <div key={a.artifact_id}>
                <p className="panel-body">
                  <code>{a.task_id ?? a.artifact_id}</code>
                </p>
                <ArtifactPreview jobId={id} artifact={a} />
              </div>
            ))
          ) : (
            <ArtifactPreview jobId={id} artifact={primary} />
          )}
          <div className="panel-body button-row">
            {j.artifacts.map((a) => (
              <DownloadButton key={a.artifact_id} jobId={id} artifact={a} />
            ))}
          </div>
        </Panel>
      )}
      <Panel
        title={t("copy.jobInspector")}
        extra={<Status status={j.status} />}
      >
        <div className="panel-body">
          <code className="job-id">{id}</code>
          <h3>
            {categoryLabels[j.request.asset_category]} ·{" "}
            {pipelineLabels[j.request.pipeline_type]}
          </h3>
          <p className="muted">
            {j.request.model_id} · {label("mode", j.execution.backend)}
          </p>
          {(queue || j.scheduling?.group_id) && (
            <div className="run-control-row">
              <QueueBadge scheduling={j.scheduling} />
              <AutoRunToggle jobId={id} scheduling={j.scheduling} />
              <GroupNote jobId={id} scheduling={j.scheduling} />
            </div>
          )}
          <dl className="properties">
            <dt>{t("copy.created")}</dt>
            <dd>{date(j.created_at)}</dd>
            <dt>{t("copy.duration")}</dt>
            <dd>{duration(j.execution.duration_seconds)}</dd>
            <dt>{t("copy.retryOf")}</dt>
            <dd className="break-word">
              {j.execution.retry_of ?? t("copy.originalJob")}
            </dd>
          </dl>
          <div className="timeline" aria-label={t("copy.statusTimeline")}>
            {j.status_history.map((h) => (
              <div className={`timeline-item ${h.status}`} key={h.status}>
                <span className="timeline-dot" aria-hidden="true" />
                <Status status={h.status} />
                <time dateTime={h.at}>{date(h.at)}</time>
              </div>
            ))}
          </div>
          {!terminal && (
            <div className="job-progress" role="status">
              {status.data?.progress ? (
                <>
                  <p>{status.data.progress.message}</p>
                  {status.data.progress.percent !== null ? (
                    <progress
                      max={100}
                      value={status.data.progress.percent}
                      aria-label={t("copy.reportedJobProgress")}
                    />
                  ) : (
                    <progress aria-label={t("copy.jobProcessing")} />
                  )}
                </>
              ) : (
                <p className="muted">
                  {t("copy.processingNoProgressPercentageReported")}
                </p>
              )}
            </div>
          )}
          {status.error && <Failure error={status.error} />}
          <Issues items={[...(j.error ? [j.error] : []), ...j.warnings]} />
          <div className="button-row">
            <RunButton jobId={id} scheduling={j.scheduling} />
            {j.status === "failed" && j.error?.retryable && (
              <button
                className="primary"
                onClick={() => retry.mutate()}
                disabled={retry.isPending}
              >
                <RefreshCw size={14} aria-hidden="true" />
                {retry.isPending ? t("copy.retrying") : t("copy.retryJob")}
              </button>
            )}
            {deletable && (
              <button
                className="danger-text"
                disabled={remove.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      t(
                        "copy.deleteThisJobItsInputsLogsAndArtifactsThisCannotBeUndone",
                      ),
                    )
                  )
                    remove.mutate();
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
                {t("copy.deleteJob")}
              </button>
            )}
          </div>
          {retry.error && <Failure error={retry.error} />}{" "}
          {remove.error && <Failure error={remove.error} />}
        </div>
      </Panel>
      <Panel
        title={t("copy.executionLogs")}
        extra={
          <span className="muted small">
            {logs.data?.complete
              ? t("copy.complete")
              : t("copy.pollingEvery2S")}
          </span>
        }
      >
        <div
          className="terminal"
          tabIndex={0}
          role="log"
          aria-label={t("copy.executionLogs")}
        >
          {logs.error ? (
            <Failure error={logs.error} />
          ) : (
            (logs.data?.lines.map((l) => (
              <div key={l.n}>
                <time dateTime={l.at}>
                  {new Intl.DateTimeFormat(intlLocale, {
                    timeStyle: "medium",
                  }).format(new Date(l.at))}
                </time>
                <span>{l.text}</span>
              </div>
            )) ?? <span>{t("copy.loadingLogs")}</span>)
          )}
        </div>
      </Panel>
      <PlanPanel plan={j.compute.resource_plan} />
    </div>
  );
}
