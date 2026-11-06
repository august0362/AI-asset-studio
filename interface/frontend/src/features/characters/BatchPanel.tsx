import { useEffect, useState } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type {
  BatchManifest,
  StageDetail,
  SubmitBatchRequest,
} from "../../api/characterTypes";
import { Badge, Failure, Issues, PlanPanel, Status } from "../../components/ui";
import { useI18n } from "../../i18n";
import {
  ArtifactImage,
  DownloadButton,
} from "../../components/ArtifactPreview";
import { Modal } from "./shared";
export function isStoredManifest(batch: BatchManifest) {
  return batch.manifest_id !== "bat_000000000000";
}
export function LinkedImage({
  jobId,
  artifactId,
}: {
  jobId: string;
  artifactId: string | null;
}) {
  const { t } = useI18n();
  const [zoomed, setZoomed] = useState(false);
  const q = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId),
  });
  const a =
    q.data?.artifacts.find((a) => a.artifact_id === artifactId) ??
    q.data?.artifacts.find((a) => a.is_primary);
  return q.error ? (
    <Failure error={q.error} />
  ) : a ? (
    <>
      <button
        className="character-image-open"
        aria-label={t("char.viewImage")}
        onClick={() => setZoomed(true)}
      >
        <ArtifactImage jobId={jobId} artifact={a} />
      </button>
      {zoomed && (
        <Modal title={t("char.viewImage")} onClose={() => setZoomed(false)}>
          <ArtifactImage jobId={jobId} artifact={a} />
          <DownloadButton jobId={jobId} artifact={a} />
          <button onClick={() => setZoomed(false)}>{t("char.close")}</button>
        </Modal>
      )}
    </>
  ) : null;
}
export function ManifestReview({ detail }: { detail: StageDetail }) {
  const { t, label, number, duration } = useI18n();
  const b = detail.manifest_preview ?? detail.batches[0];
  return (
    <section className="character-inset">
      <h3>{t("char.manifest")}</h3>
      {!b ? (
        <p>{t("char.noBatch")}</p>
      ) : (
        <>
          <code>{b.target_model_id}</code>
          <p>{t("char.loads", { count: number(b.expected_model_loads, 0) })}</p>
          {b.groups.map((g) => (
            <div key={g.group_id}>
              <p>
                {t("char.estimated", {
                  duration: duration(g.estimated_runtime_seconds),
                })}
              </p>
              <code>{g.model_revision ?? t("common.unknown")}</code>
            </div>
          ))}
          <ul>
            {b.tasks.map((task) => (
              <li key={task.task_id}>
                {task.task_id} · {label("purpose", task.purpose)} · {task.width}{" "}
                × {task.height} · {t("char.seed")}{" "}
                {task.seed ?? t("common.unknown")}
              </li>
            ))}
          </ul>
          {b.references.map((r) => (
            <p key={r.asset_id}>
              {r.asset_id}:{" "}
              {r.applied
                ? t("char.reference")
                : t("char.notApplied", {
                    reason:
                      r.reason === "model_has_no_image_role"
                        ? t("char.noImageRole")
                        : (r.reason ?? t("common.unknown")),
                  })}
            </p>
          ))}
        </>
      )}
      {detail.resource_plans.map((plan, i) => (
        <PlanPanel key={i} plan={plan} />
      ))}
    </section>
  );
}
export function BatchControls({
  detail,
  dirty,
}: {
  detail: StageDetail;
  dirty: boolean;
}) {
  const { t, label } = useI18n(),
    cache = useQueryClient();
  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api.profiles(),
  });
  const [chosen, setChosen] = useState(""),
    [accelerator, setAccelerator] = useState("auto"),
    [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const profileId =
    chosen || profiles.data?.profiles.find((p) => p.enabled)?.profile_id || "";
  const profile = profiles.data?.profiles.find(
    (p) => p.profile_id === profileId,
  );
  const storedBatches = detail.batches.filter(isStoredManifest);
  const batch = storedBatches.find(
    (b) =>
      b.kind === (detail.config.stage_id === "s3" ? "preview" : "production"),
  );
  const jobs = [
    ...new Set(storedBatches.flatMap((b) => b.attempts.map((a) => a.job_id))),
  ];
  const statuses = useQueries({
    queries: jobs.map((id) => ({
      queryKey: ["character-job-status", id],
      queryFn: () => api.jobStatus(id),
      refetchInterval: (q: { state: { data?: { status: string } } }) =>
        q.state.data && ["completed", "failed"].includes(q.state.data.status)
          ? false
          : 2000,
    })),
  });
  const terminal = statuses
    .map((q) =>
      q.data && ["completed", "failed"].includes(q.data.status)
        ? `${q.data.job_id}:${q.data.status}`
        : "",
    )
    .filter(Boolean)
    .join(",");
  useEffect(() => {
    if (terminal) {
      void cache.invalidateQueries({
        queryKey: ["character-stage", detail.character.character_id],
      });
      void cache.invalidateQueries({
        queryKey: ["character", detail.character.character_id],
      });
    }
  }, [terminal, cache, detail.character.character_id]);
  const action = useMutation({
    mutationFn: (retry: boolean) => {
      const request: SubmitBatchRequest = {
        contract_version: "1.1",
        client_request_id: requestId,
        compute: { profile_id: profileId, accelerator_id: accelerator },
      };
      return detail.config.stage_id === "s3"
        ? api.createPreviewBatch(detail.character.character_id, {
            ...request,
            kind: "preview",
          })
        : retry
          ? api.retryCharacterBatch(
              detail.character.character_id,
              batch!.manifest_id,
              request,
            )
          : api.submitCharacterBatch(
              detail.character.character_id,
              batch!.manifest_id,
              request,
            );
    },
    onSuccess: () => {
      setRequestId(crypto.randomUUID());
      void cache.invalidateQueries({
        queryKey: ["character-stage", detail.character.character_id],
      });
      void cache.invalidateQueries({
        queryKey: ["character-history", detail.character.character_id],
      });
    },
  });
  const c = detail.draft.content;
  const previewReady =
    c.stage_id === "s3" &&
    !!c.preview_profile &&
    !!c.preview_prompt?.trim() &&
    detail.inputs
      .filter((i) => i.kind === "hard")
      .every((i) => i.revision !== null);
  const productionReady =
    !!batch &&
    batch.status === "ready" &&
    detail.inputs
      .filter((i) => i.kind === "hard")
      .every((i) => i.revision !== null) &&
    batch.approved_spec_revision ===
      detail.inputs.find((i) => i.stage_id === "s2")?.revision &&
    batch.prompt_set_revision ===
      detail.inputs.find((i) => i.stage_id === "s4")?.revision;
  return (
    <section className="character-inset">
      <h3>
        {detail.config.stage_id === "s3"
          ? t("char.preview")
          : t("char.production")}
      </h3>
      {profiles.error && <Failure error={profiles.error} />}
      <div className="character-field-grid">
        <label>
          {t("char.compute")}
          <select
            value={profileId}
            onChange={(e) => {
              setChosen(e.target.value);
              setAccelerator("auto");
            }}
          >
            {!profileId && <option value="">{t("char.noProfile")}</option>}
            {profiles.data?.profiles.map((p) => (
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
        <label>
          {t("char.accelerator")}
          <select
            value={accelerator}
            onChange={(e) => setAccelerator(e.target.value)}
          >
            <option value="auto">{t("char.auto")}</option>
            {profile?.accelerators.map((a) => (
              <option key={a.accelerator_id} value={a.accelerator_id}>
                {a.accelerator_id}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        disabled={
          !profileId ||
          dirty ||
          action.isPending ||
          (detail.config.stage_id === "s3" ? !previewReady : !productionReady)
        }
        onClick={() => action.mutate(false)}
      >
        {detail.config.stage_id === "s3"
          ? t("char.generatePreview")
          : t("char.submitBatch")}
      </button>
      {batch?.retryable_task_ids.length ? (
        <button
          disabled={!profileId || dirty || action.isPending}
          onClick={() => action.mutate(true)}
        >
          {t("char.retryBatch")}
        </button>
      ) : null}
      {action.error && <Failure error={action.error} />}
      <div className="character-stack">
        {storedBatches.map((b) => (
          <BatchResults key={b.manifest_id} batch={b} />
        ))}
        {statuses.map((q, i) => (
          <div key={jobs[i]} className="character-inset">
            <Link to={`/jobs/${jobs[i]}`}>{jobs[i]}</Link>
            {q.error ? (
              <Failure error={q.error} />
            ) : (
              q.data && (
                <>
                  <Status status={q.data.status} />
                  <p>
                    {t("char.progress")}:{" "}
                    {q.data.progress?.percent == null
                      ? t("common.unknown")
                      : `${q.data.progress.percent}%`}
                  </p>
                  {q.data.progress?.message && <p>{q.data.progress.message}</p>}
                </>
              )
            )}
          </div>
        ))}
      </div>
      <span className="sr-only">
        {label("batchStatus", batch?.status ?? "ready")}
      </span>
    </section>
  );
}
function BatchResults({ batch }: { batch: BatchManifest }) {
  const { t, label } = useI18n();
  return (
    <section>
      <p>
        <Badge>{label("batchStatus", batch.status)}</Badge>{" "}
        <code>{batch.manifest_id}</code>
      </p>
      <div className="character-gallery">
        {batch.results.map((r) => (
          <article key={r.task_id} className="character-inset">
            <h3>{r.task_id}</h3>
            <p>{label("taskStatus", r.status)}</p>
            {r.status === "succeeded" && r.job_id && (
              <LinkedImage jobId={r.job_id} artifactId={r.artifact_id} />
            )}
            <small>
              {t("char.model")}: {batch.target_model_id}
            </small>
            {r.error && <Issues items={[r.error]} />}
            <code className="break-word">{r.sha256}</code>
            <details>
              <summary>{t("char.provenance")}</summary>
              <code>{batch.model_revision ?? t("common.unknown")}</code>
              {batch.tasks
                .filter((task) => task.task_id === r.task_id)
                .map((task) => (
                  <div key={task.task_id}>
                    <p>
                      {t("char.seed")}: {task.seed ?? t("common.unknown")} ·{" "}
                      {task.width} × {task.height}
                    </p>
                    <h3>{t("char.modelPrompt")}</h3>
                    <p>{task.prompt}</p>
                    <h3>{t("char.negative")}</h3>
                    <p>{task.negative_prompt ?? t("char.none")}</p>
                    <h3>{t("char.options")}</h3>
                    <code className="break-word">
                      {JSON.stringify(task.options)}
                    </code>
                  </div>
                ))}
              {r.job_id && <Link to={`/jobs/${r.job_id}`}>{r.job_id}</Link>}
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}
