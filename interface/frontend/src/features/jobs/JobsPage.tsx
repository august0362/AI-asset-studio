import { useI18n } from "../../i18n";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Clock3, Layers, ListChecks } from "lucide-react";
import { useJobs } from "../../api/queries";
import type { JobStatus } from "../../api/types";
import {
  Badge,
  Empty,
  Failure,
  Loading,
  Panel,
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
  const { t, label, number, date, categoryLabels, pipelineLabels } = useI18n();
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
          <div className="breadcrumb">{t("copy.workspaceExecutionHub")}</div>
          <h1>{t("copy.jobsLogs")}</h1>
        </div>
        <Link className="button" to="/generate/image-to-3d">
          <Layers size={15} aria-hidden="true" />
          {t("copy.newGeneration")}
        </Link>
      </div>
      <div className="summary-strip">
        <div>
          <ListChecks size={20} aria-hidden="true" />
          <span>
            {t("copy.jobHistory")}
            <strong>
              {t("jobs.recorded", {
                count: number(rows.length, 0),
                more: jobs.hasNextPage ? "+" : "",
              })}
            </strong>
          </span>
        </div>
        <div>
          <Clock3 size={20} aria-hidden="true" />
          <span>
            {t("copy.updates")}
            <strong>{t("copy.every2Seconds")}</strong>
          </span>
        </div>
        <div>
          <Layers size={20} aria-hidden="true" />
          <span>
            {t("copy.execution")}
            <strong>{t("copy.mockNoRemoteInference")}</strong>
          </span>
        </div>
      </div>
      <div className="filter-tabs" aria-label={t("copy.jobStatusFilters")}>
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
            {s === "all" ? t("common.all") : label("status", s)}
          </button>
        ))}
      </div>
      <div className={`jobs-layout ${jobId ? "has-detail" : ""}`}>
        <Panel
          title={t("copy.executionHistory")}
          extra={
            <Badge>
              {t("jobs.visible", { count: number(rows.length, 0) })}
            </Badge>
          }
        >
          {jobs.error ? (
            <Failure error={jobs.error} />
          ) : jobs.isPending ? (
            <Loading />
          ) : !rows.length ? (
            <Empty title={t("copy.noJobsInThisView")}>
              {t("copy.chooseAnotherStatusOrStartAGenerationInTheStudio")}
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
                {t("copy.loadMoreJobs")}
              </button>
            </div>
          )}
        </Panel>
        {jobId ? (
          <JobDetail key={jobId} id={jobId} />
        ) : (
          <div className="selection-hint">
            <ListChecks size={40} aria-hidden="true" />
            <h2>{t("copy.selectAJob")}</h2>
            <p>{t("copy.inspectItsTimelineLogsErrorsAndArtifacts")}</p>
          </div>
        )}
      </div>
    </>
  );
}
