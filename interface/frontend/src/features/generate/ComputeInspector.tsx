import { useI18n } from "../../i18n";
import { Play } from "lucide-react";
import { isMock } from "../../api/client";
import type {
  ComputeProfile,
  ErrorItem,
  ModelCapabilities,
  OutputFormat,
  ValidationReport,
} from "../../api/types";
import {
  acceleratorLabels,
  Badge,
  Empty,
  Failure,
  Issues,
  Panel,
  PlanPanel,
} from "../../components/ui";
import { useDraft } from "./Draft";
import { ModelOptions } from "./ModelOptions";
interface Props {
  model: ModelCapabilities;
  models: ModelCapabilities[];
  profiles: ComputeProfile[];
  snapshotError: unknown;
  report: ValidationReport | null;
  outputFormat: OutputFormat;
  isRunning: boolean;
  pending: boolean;
  error: unknown;
  serverErrors: ErrorItem[];
  onGenerate: () => void;
}
export function ComputeInspector({
  model,
  models,
  profiles,
  snapshotError,
  report,
  outputFormat,
  isRunning,
  pending,
  error,
  serverErrors,
  onGenerate,
}: Props) {
  const { t, label, number } = useI18n();
  const { draft, setDraft } = useDraft();
  const invalid = report?.errors.map((e) => e.field ?? "") ?? [];
  const hidden = Object.entries(draft.options).filter(
    ([key, value]) =>
      !model.options_schema[key] &&
      value !== null &&
      value !== "" &&
      value !==
        models.find((m) => m.options_schema[key])?.options_schema[key].default,
  );
  return (
    <div className="inspector-stack">
      <Panel
        title={t("copy.computeGeneration")}
        extra={
          <Badge tone="success">
            {isMock ? t("common.mock") : t("common.http")}
          </Badge>
        }
      >
        <form
          className="panel-body"
          onSubmit={(e) => {
            e.preventDefault();
            if (report?.valid && !isRunning) onGenerate();
          }}
        >
          <label className="field">
            <span>{t("copy.computeProfileExplicitSelection")}</span>
            <select
              name="compute-profile"
              value={draft.profileId}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  profileId: e.target.value,
                  acceleratorId: null,
                }))
              }
            >
              {!profiles.some((p) => p.profile_id === draft.profileId) && (
                <option value={draft.profileId} disabled>
                  {draft.profileId || t("compute.noEnabledProfiles")}
                </option>
              )}
              {profiles.map((p) => (
                <option
                  key={p.profile_id}
                  value={p.profile_id}
                  disabled={!p.enabled}
                >
                  {p.display_name} ({label("mode", p.mode)})
                </option>
              ))}
            </select>
          </label>
          {!profiles.some((p) => p.enabled) ? (
            <Empty title={t("compute.noEnabledProfiles")}>
              {t("compute.noEnabledProfilesHelp")}
            </Empty>
          ) : snapshotError ? (
            <Failure error={snapshotError} />
          ) : null}
          <label className="field">
            <span>{t("copy.accelerator")}</span>
            <select
              name="accelerator"
              value={draft.acceleratorId ?? ""}
              aria-invalid={invalid.includes("compute.accelerator_id")}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  acceleratorId: e.target.value || null,
                }))
              }
            >
              <option value="">{t("copy.autoWithinSelectedProfile")}</option>
              {profiles
                .find((p) => p.profile_id === draft.profileId)
                ?.accelerators.map((a) => {
                  const eligible =
                    model.runtime.supported_accelerators.includes(a.kind) &&
                    (model.runtime.multi_gpu !== "required" ||
                      a.device_count >= 2);
                  return (
                    <option
                      key={a.accelerator_id}
                      value={a.accelerator_id}
                      disabled={
                        !eligible && draft.acceleratorId !== a.accelerator_id
                      }
                    >
                      {acceleratorLabels[a.accelerator_id] ?? a.accelerator_id}
                      {!eligible ? t("copy.incompatible") : ""}
                    </option>
                  );
                })}
            </select>
          </label>
          <div className="section-divider" />
          <h3>{t("copy.modelOptions")}</h3>
          <ModelOptions
            model={model}
            values={draft.options}
            invalid={invalid}
            onChange={(key, value) =>
              setDraft((d) => ({
                ...d,
                options: { ...d.options, [key]: value },
              }))
            }
          />
          {hidden.length > 0 && (
            <div className="notice warning">
              <div>
                <strong>{t("copy.notUsedByThisModel")}</strong>
                <p>
                  {hidden
                    .map(
                      ([k, v]) =>
                        `${label("option", k)}: ${typeof v === "number" ? number(v, 0) : v}`,
                    )
                    .join(", ")}
                </p>
                <small>
                  {t("copy.valuesAreRetainedAndRestoredWhenSupported")}
                </small>
              </div>
            </div>
          )}
          <Issues
            items={
              report?.errors.filter((e) => e.field?.startsWith("compute.")) ??
              []
            }
          />
          <Issues items={report?.warnings ?? []} />
          {error ? <Failure error={error} /> : null}
          <Issues items={serverErrors} />
          <button
            type="submit"
            className="primary generate-button"
            disabled={!report?.valid || pending || !!isRunning}
          >
            <Play size={16} aria-hidden="true" />
            {pending
              ? t("copy.creatingJob")
              : isRunning
                ? t("copy.mockJobInProgress")
                : t(
                    outputFormat === "png"
                      ? "generate.action2d"
                      : "generate.action3d",
                  )}
          </button>
          <p className="small muted">
            {report?.errors.length
              ? t("generate.issueCount", {
                  count: number(report.errors.length, 0),
                })
              : t("copy.readyToCreateAMockJob")}
          </p>
        </form>
      </Panel>
      <PlanPanel plan={report?.resource_plan ?? null} />
    </div>
  );
}
