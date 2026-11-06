import { en, type TranslationKey } from "./en";
import { vi } from "./vi";
import type { Locale } from "./settings";
import type { ErrorItem } from "../api/types";
export type Params = Record<string, unknown>;
export function interpolate(
  template: string,
  params: Params = {},
): string | null {
  let missing = false;
  const result = template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = params[key];
    if (value === undefined || value === null) {
      missing = true;
      return "";
    }
    return String(value);
  });
  return missing || !result.trim() ? null : result;
}
export function createI18n(locale: Locale) {
  const dictionary = locale === "vi" ? vi : en;
  const intlLocale = locale === "vi" ? "vi-VN" : "en-US";
  const t = (key: TranslationKey, params?: Params) =>
    interpolate(dictionary[key] ?? en[key], params) ??
    interpolate(en[key], params) ??
    en["common.requestFailed"];
  const label = (group: string, value: string, fallback = value) => {
    const key = `${group}.${value}`;
    return Object.hasOwn(en, key) ? t(key as TranslationKey) : fallback;
  };
  const number = (value: number | null, digits = 1) =>
    value === null
      ? t("common.unknown")
      : new Intl.NumberFormat(intlLocale, {
          maximumFractionDigits: digits,
        }).format(value);
  const date = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(intlLocale, {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(value))
      : t("common.unknown");
  const quantity = (value: number, unit: TranslationKey) =>
    t("format.quantity", { value: number(value), unit: t(unit) });
  const duration = (value: number | null) =>
    value === null
      ? t("common.unknown")
      : value >= 3600
        ? quantity(value / 3600, "unit.hours")
        : quantity(value / 60, "unit.minutes");
  const bytes = (value: number | null) =>
    value === null
      ? t("common.unknown")
      : quantity(value / 1024 ** 3, "unit.gib");
  const errorText = (
    error: Pick<ErrorItem, "code" | "message" | "details">,
  ) => {
    const key = `errors.${error.code}`;
    if (!Object.hasOwn(en, key)) return error.message;
    const params = Object.fromEntries(
      Object.entries(error.details).map(([name, value]) => [
        name,
        name === "role" && typeof value === "string"
          ? label("role", value)
          : name === "missing_roles" && Array.isArray(value)
            ? new Intl.ListFormat(intlLocale, {
                style: "long",
                type: "conjunction",
              }).format(value.map((role) => label("role", String(role))))
            : typeof value === "number"
              ? number(value)
              : value,
      ]),
    );
    const translated = interpolate(dictionary[key as TranslationKey], params);
    if (translated === null) return error.message;
    return typeof error.details.filename === "string"
      ? t("upload.fileError", {
          filename: error.details.filename,
          message: translated,
        })
      : translated;
  };
  const categoryLabels = {
    character: label("category", "character"),
    skill_effect: label("category", "skill_effect"),
    weapon: label("category", "weapon"),
    companion: label("category", "companion"),
  };
  const pipelineLabels = {
    text_to_2d: label("pipeline", "text_to_2d"),
    image_to_3d: label("pipeline", "image_to_3d"),
    text_to_3d: label("pipeline", "text_to_3d"),
  };
  return {
    locale,
    intlLocale,
    t,
    label,
    number,
    date,
    duration,
    bytes,
    quantity,
    errorText,
    categoryLabels,
    pipelineLabels,
  };
}
