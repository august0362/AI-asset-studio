import type { ModelCapabilities } from "../../api/types";
import type { createI18n } from "../../i18n/core";

export function formatModelTime(
  model: Pick<ModelCapabilities, "is_mock" | "runtime">,
  { t, number }: Pick<ReturnType<typeof createI18n>, "t" | "number">,
) {
  const seconds = model.runtime.estimated_runtime_seconds;
  if (
    model.is_mock !== false ||
    typeof seconds !== "number" ||
    !Number.isFinite(seconds)
  )
    return undefined;
  const minutes = seconds >= 90;
  return {
    label: t(minutes ? "modelTime.minutes" : "modelTime.seconds", {
      count: number(Math.round(minutes ? seconds / 60 : seconds), 0),
    }),
    tooltip: t("modelTime.tooltip"),
  };
}
