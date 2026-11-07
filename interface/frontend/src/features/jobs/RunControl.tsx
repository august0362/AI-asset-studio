import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { api } from "../../api/client";
import type { Scheduling } from "../../api/types";
import { useI18n } from "../../i18n";
import { Badge, Failure } from "../../components/ui";

/** v1.2 (§14.2): a job is held, waiting or starting only while it is `created`. */
export const canChangeRun = (scheduling?: Scheduling | null) =>
  scheduling?.queue_state === "held" || scheduling?.queue_state === "waiting";

export function QueueBadge({ scheduling }: { scheduling?: Scheduling | null }) {
  const { t, number } = useI18n();
  if (!scheduling?.queue_state) return null;
  const text =
    scheduling.queue_state === "held"
      ? t("runControl.held")
      : scheduling.queue_state === "starting"
        ? t("runControl.starting")
        : scheduling.queue_position
          ? t("runControl.waiting", {
              position: number(scheduling.queue_position, 0),
            })
          : t("runControl.waitingNoPosition");
  return (
    <Badge tone={scheduling.queue_state === "held" ? "secondary" : "info"}>
      {text}
    </Badge>
  );
}

function useSetAutoRun(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (autoRun: boolean) => api.setAutoRun(jobId, autoRun),
    onSuccess: (job) => {
      queryClient.setQueryData(["job", jobId], job);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

/** The auto-run switch of a held or waiting job (FR-J6). */
export function AutoRunToggle({
  jobId,
  scheduling,
}: {
  jobId: string;
  scheduling?: Scheduling | null;
}) {
  const { t } = useI18n();
  const toggle = useSetAutoRun(jobId);
  if (!canChangeRun(scheduling)) return null;
  return (
    <span className="auto-run-toggle">
      <label className="switch-field">
        <input
          type="checkbox"
          role="switch"
          name={`auto-run-${jobId}`}
          aria-label={t("runControl.autoRunFor", { id: jobId })}
          checked={!!scheduling?.auto_run}
          disabled={toggle.isPending}
          onChange={(e) => toggle.mutate(e.target.checked)}
        />
        <span aria-hidden="true">{t("runControl.autoRun")}</span>
      </label>
      {toggle.error ? <Failure error={toggle.error} /> : null}
    </span>
  );
}

/** "Run": turn auto-run on for a held job, so it joins the end of the queue. */
export function RunButton({
  jobId,
  scheduling,
}: {
  jobId: string;
  scheduling?: Scheduling | null;
}) {
  const { t } = useI18n();
  const run = useSetAutoRun(jobId);
  if (scheduling?.queue_state !== "held") return null;
  return (
    <>
      <button
        type="button"
        className="primary"
        disabled={run.isPending}
        onClick={() => run.mutate(true)}
      >
        <Play size={14} aria-hidden="true" />
        {t("runControl.run")}
      </button>
      {run.error ? <Failure error={run.error} /> : null}
    </>
  );
}

export function GroupNote({
  jobId,
  scheduling,
}: {
  jobId: string;
  scheduling?: Scheduling | null;
}) {
  const { t, number } = useI18n();
  if (!scheduling?.group_id) return null;
  const partner = scheduling.group_job_ids.find((id) => id !== jobId);
  return (
    <small className="muted break-word">
      {t("runControl.runGroup", {
        id: scheduling.group_id,
        gpu: number(scheduling.gpu_index ?? 0, 0),
      })}
      {partner ? ` · ${t("runControl.runGroupWith", { id: partner })}` : ""}
    </small>
  );
}
