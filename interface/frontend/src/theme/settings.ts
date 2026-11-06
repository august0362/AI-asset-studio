export type ThemeMode = "light" | "dark" | "system";
export type ThemeFamily = "coffee" | "green";
export type ThemeId = "latte" | "mint" | "caffe" | "matcha";
export interface ThemeSettings {
  mode: ThemeMode;
  family: ThemeFamily;
}
export const defaults: ThemeSettings = { mode: "system", family: "coffee" };
export const themeKey = "aas.theme";
export function resolveTheme(settings: ThemeSettings, dark: boolean): ThemeId {
  const isDark = settings.mode === "system" ? dark : settings.mode === "dark";
  return settings.family === "coffee"
    ? isDark
      ? "caffe"
      : "latte"
    : isDark
      ? "matcha"
      : "mint";
}
export function readTheme(): ThemeSettings {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(themeKey) ?? "null");
    if (
      value &&
      typeof value === "object" &&
      "mode" in value &&
      "family" in value &&
      typeof value.mode === "string" &&
      typeof value.family === "string" &&
      ["light", "dark", "system"].includes(value.mode) &&
      ["coffee", "green"].includes(value.family)
    )
      return {
        mode: value.mode as ThemeMode,
        family: value.family as ThemeFamily,
      };
  } catch {
    /* Storage may be disabled. */
  }
  return { ...defaults };
}
export function writeTheme(settings: ThemeSettings): ThemeSettings {
  try {
    localStorage.setItem(themeKey, JSON.stringify(settings));
    return settings;
  } catch {
    return { ...defaults };
  }
}
