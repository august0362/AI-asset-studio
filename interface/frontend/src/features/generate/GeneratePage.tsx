import { useI18n } from "../../i18n";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Box, LockKeyhole, WandSparkles } from "lucide-react";
import { api } from "../../api/client";
import { useJob, useJobs, useStudioData } from "../../api/queries";
import type { Category, CreateJobRequest, Pipeline } from "../../api/types";
import { validateRequest } from "../../validation/validate";
import {
  ArtifactPreview,
  ArtifactImage,
  DownloadButton,
} from "../../components/ArtifactPreview";
import {
  Badge,
  Empty,
  Failure,
  Issues,
  Loading,
  Panel,
  Status,
} from "../../components/ui";
import { useDraft } from "./Draft";
import { ImageInputs } from "./ImageInputs";
import { ComputeInspector } from "./ComputeInspector";
import { formatModelTime } from "./modelTime";
const routeToPipeline: Record<string, Pipeline> = {
  "text-to-2d": "text_to_2d",
  "image-to-3d": "image_to_3d",
  "text-to-3d": "text_to_3d",
};
export function GeneratePage() {
  const { t, number, categoryLabels, pipelineLabels } = useI18n();
  const { pipeline: route = "image-to-3d" } = useParams(),
    pipeline = routeToPipeline[route];
  const { draft, setDraft } = useDraft(),
    data = useStudioData(draft.profileId),
    navigate = useNavigate(),
    queryClient = useQueryClient();
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const jobs = useJobs({ status: "completed" }),
    active = useJob(draft.jobId);
  const model = data.models?.find((m) => m.model_id === draft.modelId);
  useEffect(() => {
    if (!draft.profileId && data.profileId)
      setDraft((d) => ({ ...d, profileId: d.profileId || data.profileId! }));
  }, [draft.profileId, data.profileId, setDraft]);
  const request = useMemo<CreateJobRequest>(
    () => ({
      contract_version: "1.0",
      client_request_id: requestId,
      pipeline_type: pipeline,
      asset_category: draft.category,
      model_id: draft.modelId,
      prompt: draft.prompt.trim() || null,
      inputs: draft.uploads.map((u) => ({
        upload_id: u.record.upload_id,
        role: u.role,
      })),
      options: Object.fromEntries(
        Object.entries(draft.options).filter(
          ([key]) => model?.options_schema[key],
        ),
      ),
      output_format: pipeline === "text_to_2d" ? "png" : "glb",
      compute: {
        profile_id: data.profileId ?? "",
        accelerator_id: draft.acceleratorId,
      },
    }),
    [draft, model, pipeline, requestId, data.profileId],
  );
  const report =
    data.catalog &&
    data.models &&
    data.profiles &&
    data.snapshot &&
    !data.snapshotError
      ? validateRequest(request, {
          catalog: data.catalog,
          models: data.models,
          profiles: data.profiles,
          snapshot: data.snapshot,
          uploads: draft.uploads.map((u) => u.record),
        })
      : null;
  const create = useMutation({
    mutationFn: async () => {
      const validation = await api.validate(request);
      if (!validation.valid) return { job: null, validation };
      return { job: await api.createJob(request), validation };
    },
    onSuccess: ({ job }) => {
      if (job) {
        setDraft((d) => ({ ...d, jobId: job.job_id }));
        setRequestId(crypto.randomUUID());
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      }
    },
  });
  if (!pipeline)
    return (
      <Empty title={t("copy.unknownPipeline")}>
        <Link to="/generate/image-to-3d">{t("copy.openImage3D")}</Link>
      </Empty>
    );
  if (data.error) return <Failure error={data.error} />;
  if (!data.catalog || !data.models || !data.profiles || !model)
    return <Loading />;
  const compatible = data.models.filter(
    (m) =>
      m.supported_pipeline_types.includes(pipeline) &&
      m.supported_asset_categories.includes(draft.category),
  );
  const modelTime = formatModelTime(model, { t, number });
  const example = jobs.data?.pages
    .flatMap((p) => p.jobs)
    .find((j) => j.pipeline_type === pipeline);
  const previewJobId = draft.jobId ?? example?.job_id ?? null;
  const exampleJob =
    active.data && active.data.job_id === previewJobId ? active.data : null;
  const output =
    exampleJob?.artifacts.find((a) => a.is_primary) ??
    (!draft.jobId ? example?.primary_artifact : null);
  const preview = active.data?.artifacts.find(
    (a) =>
      a.kind === "preview" &&
      a.artifact_id === active.data?.preview?.artifact_id,
  );
  const isRunning =
    active.data && !["completed", "failed"].includes(active.data.status);
  const invalid = report?.errors.map((e) => e.field ?? "") ?? [];
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="breadcrumb">{t("copy.workspaceGeneration")}</div>
          <h1>{t("copy.generateStudio")}</h1>
        </div>
        <Badge tone="secondary">{t("copy.m1MockWorkstation")}</Badge>
      </div>
      <div className="studio-controls">
        <div className="pipeline-tabs" aria-label={t("copy.pipelineSelector")}>
          {data.catalog.pipelines.map((p) => (
            <button
              key={p.pipeline_type}
              type="button"
              disabled={p.availability === "planned"}
              aria-pressed={pipeline === p.pipeline_type}
              title={
                p.availability === "planned"
                  ? t("copy.pipelineNotAvailablePlannedForM6")
                  : undefined
              }
              onClick={() => {
                const next = data.models!.find(
                  (m) =>
                    m.supported_pipeline_types.includes(p.pipeline_type) &&
                    m.supported_asset_categories.includes(draft.category),
                );
                setDraft((d) => ({
                  ...d,
                  modelId: next?.model_id ?? d.modelId,
                  jobId: null,
                }));
                navigate(`/generate/${p.pipeline_type.replaceAll("_", "-")}`);
              }}
            >
              {p.pipeline_type === "text_to_3d" ? (
                <LockKeyhole size={14} aria-hidden="true" />
              ) : p.pipeline_type === "image_to_3d" ? (
                <Box size={15} aria-hidden="true" />
              ) : (
                <WandSparkles size={15} aria-hidden="true" />
              )}
              {pipelineLabels[p.pipeline_type]}
              {p.availability === "planned" && (
                <small>{t("copy.plannedM6")}</small>
              )}
            </button>
          ))}
        </div>
        <label className="inline-field">
          {t("copy.assetCategory")}
          <select
            name="asset-category"
            value={draft.category}
            onChange={(e) =>
              setDraft((d) => ({ ...d, category: e.target.value as Category }))
            }
          >
            {data.catalog.asset_categories.map((c) => (
              <option key={c} value={c}>
                {categoryLabels[c]}
              </option>
            ))}
          </select>
        </label>
        <Link className="text-link history-link" to="/jobs">
          {t("copy.jobHistory")}
        </Link>
      </div>
      {pipeline === "text_to_3d" ? (
        <Issues items={report?.errors ?? []} />
      ) : null}
      <div className="studio-grid">
        <Panel
          title={
            model.inputs.max_images
              ? t("copy.referenceIngestion")
              : t("copy.promptWorkspace")
          }
          extra={<Badge>{pipelineLabels[pipeline]}</Badge>}
          className="input-panel"
        >
          <div className="panel-body">
            <label className="field">
              <span>{t("copy.model")}</span>
              <select
                name="model"
                title={modelTime?.tooltip}
                value={draft.modelId}
                aria-invalid={
                  invalid.includes("model_id") ||
                  invalid.includes("asset_category")
                }
                onChange={(e) =>
                  setDraft((d) => ({ ...d, modelId: e.target.value }))
                }
              >
                {!compatible.includes(model) && (
                  <option value={model.model_id} title={modelTime?.tooltip}>
                    {model.display_name}
                    {modelTime ? ` ${modelTime.label}` : ""}
                    {t("copy.incompatibleRetained")}
                  </option>
                )}
                {compatible.map((m) => {
                  const time = formatModelTime(m, { t, number });
                  return (
                    <option
                      value={m.model_id}
                      key={m.model_id}
                      title={time?.tooltip}
                    >
                      {m.display_name}
                      {time ? ` ${time.label}` : ""}
                      {m.availability === "experimental"
                        ? t("copy.experimental")
                        : ""}
                    </option>
                  );
                })}
              </select>
            </label>
            <p className="small muted">
              {model.inputs.max_images
                ? t(
                    "copy.useClearConsistentViewsFullBodyReferencesHelpPreserveSilhouetteAndIdentity",
                  )
                : t("copy.describeTheSubjectMaterialsSilhouetteAndVisualStyle")}
            </p>
            {model.inputs.prompt_supported || draft.prompt ? (
              <label className="field">
                <span>
                  {model.inputs.prompt_supported
                    ? t(
                        model.inputs.prompt_required
                          ? "generate.requiredPrompt"
                          : "generate.optionalPrompt",
                      )
                    : t("copy.retainedPromptUnsupported")}
                </span>
                <textarea
                  name="prompt"
                  autoComplete="off"
                  value={draft.prompt}
                  aria-invalid={invalid.includes("prompt")}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, prompt: e.target.value }))
                  }
                  placeholder={t("copy.ornateFrostGreatswordCrystallineBlade")}
                  rows={6}
                />
                <small>
                  {t("generate.promptCount", {
                    count: number(draft.prompt.trim().length, 0),
                    max:
                      model.inputs.prompt_max_length === null
                        ? t("copy.notSupported")
                        : number(model.inputs.prompt_max_length, 0),
                  })}
                </small>
              </label>
            ) : null}
            {!model.inputs.prompt_supported && draft.prompt && (
              <button onClick={() => setDraft((d) => ({ ...d, prompt: "" }))}>
                {t("copy.clearRetainedPrompt")}
              </button>
            )}
            {model.inputs.max_images > 0 || draft.uploads.length > 0 ? (
              <ImageInputs
                uploads={draft.uploads}
                model={model}
                roles={data.catalog.image_roles}
                errors={report?.errors ?? []}
                onAdd={(items) =>
                  setDraft((d) => ({ ...d, uploads: [...d.uploads, ...items] }))
                }
                onRole={(index, role) =>
                  setDraft((d) => ({
                    ...d,
                    uploads: d.uploads.map((u, i) =>
                      i === index ? { ...u, role } : u,
                    ),
                  }))
                }
                onRemove={(index) =>
                  setDraft((d) => ({
                    ...d,
                    uploads: d.uploads.filter((_, i) => i !== index),
                  }))
                }
              />
            ) : null}
            <Issues
              items={
                report?.errors.filter(
                  (e) => !e.field?.startsWith("compute."),
                ) ?? []
              }
            />
          </div>
          <div className="panel-foot">
            <span className="status-dot" />
            {t("copy.inputsStayInYourDraftWhenSwitchingModels")}
          </div>
        </Panel>
        <Panel
          title={t("copy.assetViewport")}
          extra={
            <Badge tone="info">
              {output?.format.toUpperCase() ??
                request.output_format.toUpperCase()}
            </Badge>
          }
          className="viewport-panel"
        >
          <div className="viewport-subhead">
            <span>
              {draft.jobId ? t("copy.currentJob") : t("copy.exampleFixture")}
            </span>
            <Badge>{t("copy.mockOutput")}</Badge>
          </div>
          {output && previewJobId ? (
            <ArtifactPreview jobId={previewJobId} artifact={output} />
          ) : (
            <Empty
              title={
                isRunning
                  ? t("copy.yourMockJobIsProcessing")
                  : t("copy.yourNextAssetStartsHere")
              }
            >
              {isRunning
                ? t(
                    "copy.statusUpdatesEvery2SecondsProgressPercentageIsNotReported",
                  )
                : t(
                    "copy.addInputsReviewCompatibilityAndGenerateAFixturePreview",
                  )}
            </Empty>
          )}
          <div className="panel-body result-summary" aria-live="polite">
            {active.data && (
              <>
                <div className="flex-between">
                  <Status status={active.data.status} />
                  <Link
                    to={`/jobs/${active.data.job_id}`}
                    className="text-link"
                  >
                    {t("copy.viewJobLogs")}
                  </Link>
                </div>
                <small className="muted break-word">{active.data.job_id}</small>
                {active.data.error && <Issues items={[active.data.error]} />}
              </>
            )}
            {active.error && <Failure error={active.error} />}
            <p className="muted small">
              {pipeline === "image_to_3d"
                ? t("copy.reconstructionMayApproximateUnseenRegions")
                : ""}
              {t(
                "copy.m1ReturnsFixedTestArtifactsPromptAndOptionsAreValidatedNoAiInferenceRuns",
              )}
            </p>
            {output && previewJobId && (
              <DownloadButton jobId={previewJobId} artifact={output} />
            )}
            {preview && previewJobId && (
              <figure className="artifact-thumbnail">
                <ArtifactImage
                  jobId={previewJobId}
                  artifact={preview}
                  alt={t("copy.pngPreviewOfTheGenerated3DArtifact")}
                />
                <figcaption>{t("copy.previewPng")}</figcaption>
              </figure>
            )}
          </div>
        </Panel>
        <ComputeInspector
          model={model}
          models={data.models}
          profiles={data.profiles}
          snapshotError={data.snapshotError}
          report={report}
          outputFormat={request.output_format}
          isRunning={!!isRunning}
          pending={create.isPending}
          error={create.error}
          serverErrors={create.data?.validation.errors ?? []}
          onGenerate={() => create.mutate()}
        />
      </div>
    </>
  );
}
