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
  categoryLabels,
  date,
  duration,
  Failure,
  Issues,
  Loading,
  Panel,
  pipelineLabels,
  PlanPanel,
  Status,
} from "../../components/ui";
export function JobDetail({ id }: { id: string }) {
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
  if (!job.data) return <Loading>Loading job details…</Loading>;
  const j = job.data,
    primary = j.artifacts.find((a) => a.is_primary),
    terminal = ["completed", "failed"].includes(j.status);
  return (
    <div className="job-detail-stack">
      <Panel title="Job inspector" extra={<Status status={j.status} />}>
        <div className="panel-body">
          <code className="job-id">{id}</code>
          <h3>
            {categoryLabels[j.request.asset_category]} ·{" "}
            {pipelineLabels[j.request.pipeline_type]}
          </h3>
          <p className="muted">
            {j.request.model_id} · {j.execution.backend.toUpperCase()}
          </p>
          <dl className="properties">
            <dt>Created</dt>
            <dd>{date(j.created_at)}</dd>
            <dt>Duration</dt>
            <dd>{duration(j.execution.duration_seconds)}</dd>
            <dt>Retry of</dt>
            <dd className="break-word">
              {j.execution.retry_of ?? "Original job"}
            </dd>
          </dl>
          <div className="timeline" aria-label="Status timeline">
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
                      aria-label="Reported job progress"
                    />
                  ) : (
                    <progress aria-label="Job processing" />
                  )}
                </>
              ) : (
                <p className="muted">
                  Processing · No progress percentage reported.
                </p>
              )}
            </div>
          )}
          {status.error && <Failure error={status.error} />}
          <Issues items={[...(j.error ? [j.error] : []), ...j.warnings]} />
          <div className="button-row">
            {j.status === "failed" && j.error?.retryable && (
              <button onClick={() => retry.mutate()} disabled={retry.isPending}>
                <RefreshCw size={14} aria-hidden="true" />
                {retry.isPending ? "Retrying…" : "Retry job"}
              </button>
            )}
            {terminal && (
              <button
                className="danger-text"
                disabled={remove.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      "Delete this job, its inputs, logs and artifacts? This cannot be undone.",
                    )
                  )
                    remove.mutate();
                }}
              >
                <Trash2 size={14} aria-hidden="true" />
                Delete job
              </button>
            )}
          </div>
          {retry.error && <Failure error={retry.error} />}{" "}
          {remove.error && <Failure error={remove.error} />}
        </div>
      </Panel>
      <Panel
        title="Execution logs"
        extra={
          <span className="muted small">
            {logs.data?.complete ? "Complete" : "Polling every 2 s"}
          </span>
        }
      >
        <div className="terminal" role="log" aria-label="Execution logs">
          {logs.error ? (
            <Failure error={logs.error} />
          ) : (
            (logs.data?.lines.map((l) => (
              <div key={l.n}>
                <time dateTime={l.at}>
                  {new Intl.DateTimeFormat(undefined, {
                    timeStyle: "medium",
                  }).format(new Date(l.at))}
                </time>
                <span>{l.text}</span>
              </div>
            )) ?? <span>Loading logs…</span>)
          )}
        </div>
      </Panel>
      {primary && (
        <Panel title="Job artifacts">
          <ArtifactPreview jobId={id} artifact={primary} />
          <div className="panel-body button-row">
            {j.artifacts.map((a) => (
              <DownloadButton key={a.artifact_id} jobId={id} artifact={a} />
            ))}
          </div>
        </Panel>
      )}
      <PlanPanel plan={j.compute.resource_plan} />
    </div>
  );
}
