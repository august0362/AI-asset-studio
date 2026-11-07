import { useI18n } from "../../i18n";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Clock3, Layers, ListChecks, Trash2, Users } from "lucide-react";
import { api, isMock } from "../../api/client";
import { useJobs } from "../../api/queries";
import type { BulkDeleteResult, JobStatus, RunGroup } from "../../api/types";
import { AutoRunToggle, GroupNote, QueueBadge } from "./RunControl";
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
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<string[]>([]);
  const selected = picked.filter((id) => rows.some((r) => r.job_id === id));
  const heldSelected = rows.filter(
    (r) => selected.includes(r.job_id) && r.scheduling?.queue_state === "held",
  );
  const toggle = (id: string, on: boolean) =>
    setPicked((current) =>
      on ? [...new Set([...current, id])] : current.filter((x) => x !== id),
    );
  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: ["jobs"] });
  const remove = useMutation<BulkDeleteResult, unknown, string[]>({
    mutationFn: (ids) => api.deleteJobs(ids),
    onSuccess: (result) => {
      setPicked((current) =>
        current.filter((id) => !result.deleted.includes(id)),
      );
      for (const id of result.deleted)
        queryClient.removeQueries({ queryKey: ["job", id] });
      refresh();
    },
  });
  const group = useMutation<RunGroup, unknown, [string, string]>({
    mutationFn: (ids) => api.createRunGroup(ids),
    onSuccess: () => {
      setPicked([]);
      refresh();
    },
  });
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
            <strong>
              {isMock
                ? t("copy.mockNoRemoteInference")
                : t("jobs.kaggleExecution")}
            </strong>
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
      <div
        className="selection-bar"
        role="toolbar"
        aria-label={t("jobs.selected", { count: number(selected.length, 0) })}
      >
        <button
          type="button"
          onClick={() =>
            setPicked(
              rows.filter((r) => r.status === "completed").map((r) => r.job_id),
            )
          }
          disabled={!rows.some((r) => r.status === "completed")}
        >
          {t("jobs.selectAllCompleted")}
        </button>
        <button
          type="button"
          onClick={() => setPicked([])}
          disabled={!selected.length}
        >
          {t("jobs.clearSelection")}
        </button>
        <span className="muted small" aria-live="polite">
          {t("jobs.selected", { count: number(selected.length, 0) })}
        </span>
        <button
          type="button"
          title={t("jobs.runTogetherHelp")}
          disabled={
            selected.length !== 2 ||
            heldSelected.length !== 2 ||
            group.isPending
          }
          onClick={() => group.mutate([selected[0], selected[1]])}
        >
          <Users size={14} aria-hidden="true" />
          {t("jobs.runTogether")}
        </button>
        <button
          type="button"
          className="danger-text"
          disabled={!selected.length || remove.isPending}
          onClick={() => {
            if (
              window.confirm(
                t("jobs.confirmDeleteSelected", {
                  count: number(selected.length, 0),
                }),
              )
            )
              remove.mutate(selected);
          }}
        >
          <Trash2 size={14} aria-hidden="true" />
          {t("jobs.deleteSelected")}
        </button>
      </div>
      <p className="small muted selection-help">{t("jobs.runTogetherHelp")}</p>
      <div aria-live="polite">
        {remove.data && remove.data.deleted.length > 0 && (
          <p className="notice">
            {t("jobs.deletedCount", {
              count: number(remove.data.deleted.length, 0),
            })}
          </p>
        )}
        {remove.data && remove.data.refused.length > 0 && (
          <div className="notice warning">
            <div>
              <strong>{t("jobs.refusedTitle")}</strong>
              <ul>
                {remove.data.refused.map((r) => (
                  <li key={r.job_id}>
                    {r.code === "JOB_NOT_FOUND"
                      ? t("jobs.refusedNotFound", { id: r.job_id })
                      : t("jobs.refusedStarted", { id: r.job_id })}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {group.data && (
          <p className="notice">
            {t("jobs.runTogetherStarted", { id: group.data.group_id })}
          </p>
        )}
        {remove.error ? <Failure error={remove.error} /> : null}
        {group.error ? <Failure error={group.error} /> : null}
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
                <div className="job-row-wrap" key={j.job_id}>
                  <input
                    type="checkbox"
                    className="job-select"
                    name={`select-${j.job_id}`}
                    aria-label={t("jobs.select", { id: j.job_id })}
                    checked={selected.includes(j.job_id)}
                    onChange={(e) => toggle(j.job_id, e.target.checked)}
                  />
                  <Link
                    className={`job-row ${jobId === j.job_id ? "selected" : ""}`}
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
                        <span className="danger-text small">
                          {j.error_code}
                        </span>
                      )}
                      <GroupNote jobId={j.job_id} scheduling={j.scheduling} />
                    </div>
                    <span className="job-row-status">
                      <Status status={j.status} />
                      <QueueBadge scheduling={j.scheduling} />
                    </span>
                  </Link>
                  <AutoRunToggle jobId={j.job_id} scheduling={j.scheduling} />
                </div>
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
