import { Link, useParams, useSearchParams } from "react-router-dom";
import { Clock3, Layers, ListChecks } from "lucide-react";
import { useJobs } from "../../api/queries";
import type { JobStatus } from "../../api/types";
import {
  Badge,
  categoryLabels,
  date,
  Empty,
  Failure,
  Loading,
  Panel,
  pipelineLabels,
  Status,
} from "../../components/ui";
import { JobDetail } from "./JobDetail";
export const statuses: JobStatus[] = [
  "created",
  "uploading",
  "queued",
  "running",
  "downloading",
  "completed",
  "failed",
];
export function JobsPage() {
  const [params, setParams] = useSearchParams(),
    { jobId } = useParams(),
    filter = params.get("status");
  const jobs = useJobs(
    statuses.includes(filter as JobStatus)
      ? { status: filter as JobStatus }
      : {},
  );
  const rows = jobs.data?.pages.flatMap((p) => p.jobs) ?? [];
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="breadcrumb">Workspace / Execution hub</div>
          <h1>Jobs & logs</h1>
        </div>
        <Link className="button primary" to="/generate/image-to-3d">
          <Layers size={15} aria-hidden="true" />
          New generation
        </Link>
      </div>
      <div className="summary-strip">
        <div>
          <ListChecks size={20} aria-hidden="true" />
          <span>
            Job history
            <strong>
              {rows.length}
              {jobs.hasNextPage ? "+" : ""} recorded
            </strong>
          </span>
        </div>
        <div>
          <Clock3 size={20} aria-hidden="true" />
          <span>
            Updates<strong>Every 2 seconds</strong>
          </span>
        </div>
        <div>
          <Layers size={20} aria-hidden="true" />
          <span>
            Execution<strong>Mock · No remote inference</strong>
          </span>
        </div>
      </div>
      <div className="filter-tabs" aria-label="Job status filters">
        {["all", ...statuses].map((s) => (
          <button
            key={s}
            aria-pressed={(filter ?? "all") === s}
            onClick={() => {
              const next = new URLSearchParams(params);
              if (s === "all") next.delete("status");
              else next.set("status", s);
              setParams(next);
            }}
          >
            {s}
          </button>
        ))}
      </div>
      <div className={`jobs-layout ${jobId ? "has-detail" : ""}`}>
        <Panel
          title="Execution history"
          extra={<Badge>{rows.length} visible</Badge>}
        >
          {jobs.error ? (
            <Failure error={jobs.error} />
          ) : jobs.isPending ? (
            <Loading />
          ) : !rows.length ? (
            <Empty title="No jobs in this view">
              Choose another status, or start a generation in the studio.
            </Empty>
          ) : (
            <div className="job-list">
              {rows.map((j) => (
                <Link
                  className={`job-row ${jobId === j.job_id ? "selected" : ""}`}
                  key={j.job_id}
                  to={`/jobs/${j.job_id}${params.size ? `?${params}` : ""}`}
                >
                  <div>
                    <span className="job-kind">
                      {categoryLabels[j.asset_category]}{" "}
                      <span className="muted">/</span>{" "}
                      {pipelineLabels[j.pipeline_type]}
                    </span>
                    <code className="job-id">{j.job_id}</code>
                    <small>
                      {j.model_id} · {date(j.created_at)}
                    </small>
                    {j.error_code && (
                      <span className="danger-text small">{j.error_code}</span>
                    )}
                  </div>
                  <Status status={j.status} />
                </Link>
              ))}
            </div>
          )}
          {jobs.hasNextPage && (
            <div className="panel-body">
              <button
                onClick={() => void jobs.fetchNextPage()}
                disabled={jobs.isFetchingNextPage}
              >
                Load more jobs
              </button>
            </div>
          )}
        </Panel>
        {jobId ? (
          <JobDetail key={jobId} id={jobId} />
        ) : (
          <div className="selection-hint">
            <ListChecks size={40} aria-hidden="true" />
            <h2>Select a job</h2>
            <p>Inspect its timeline, logs, errors and artifacts.</p>
          </div>
        )}
      </div>
    </>
  );
}
