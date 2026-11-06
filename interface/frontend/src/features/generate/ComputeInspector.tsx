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
  report,
  outputFormat,
  isRunning,
  pending,
  error,
  serverErrors,
  onGenerate,
}: Props) {
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
        title="Compute & generation"
        extra={<Badge tone="success">{isMock ? "MOCK" : "HTTP"}</Badge>}
      >
        <form
          className="panel-body"
          onSubmit={(e) => {
            e.preventDefault();
            if (report?.valid && !isRunning) onGenerate();
          }}
        >
          <label className="field">
            <span>Compute profile · Explicit selection</span>
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
              {profiles
                .filter((p) => p.enabled && p.authorization_confirmed)
                .map((p) => (
                  <option key={p.profile_id} value={p.profile_id}>
                    {p.display_name} ({p.mode})
                  </option>
                ))}
            </select>
          </label>
          <label className="field">
            <span>Accelerator</span>
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
              <option value="">Auto · Within selected profile</option>
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
                      {!eligible ? " (incompatible)" : ""}
                    </option>
                  );
                })}
            </select>
          </label>
          <div className="section-divider" />
          <h3>Model options</h3>
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
                <strong>Not used by this model</strong>
                <p>{hidden.map(([k, v]) => `${k}: ${v}`).join(", ")}</p>
                <small>Values are retained and restored when supported.</small>
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
              ? "Creating job…"
              : isRunning
                ? "Mock job in progress…"
                : `Generate ${outputFormat === "png" ? "2D image" : "3D asset"}`}
          </button>
          <p className="small muted">
            {report?.errors.length
              ? `${report.errors.length} validation issue(s) to resolve.`
              : "Ready to create a mock job."}
          </p>
        </form>
      </Panel>
      <PlanPanel plan={report?.resource_plan ?? null} />
    </div>
  );
}
