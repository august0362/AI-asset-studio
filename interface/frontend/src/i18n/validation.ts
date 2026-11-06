import { issue } from "../api/errors";
import type { ErrorCode, ErrorItem } from "../api/types";
import { createI18n } from "./core";
import { en } from "./en";

// Validation reports remain locale-independent English contract data. Rendering
// translates the same code/details through errorText for the selected locale.
const english = createI18n("en");
export function validationIssue(
  code: ErrorCode,
  field: string | null,
  severity: ErrorItem["severity"] = "error",
  details: Record<string, unknown> = {},
  retryable = false,
): ErrorItem {
  const item = issue(
    code,
    field,
    en["common.requestFailed"],
    severity,
    details,
    retryable,
  );
  return { ...item, message: english.errorText(item) };
}
