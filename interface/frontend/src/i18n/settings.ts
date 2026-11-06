export type Locale = "en" | "vi";
export const localeKey = "aas.locale";
export function detectLocale(languages: readonly string[]): Locale {
  return languages.some((language) => /^vi/i.test(language)) ? "vi" : "en";
}
export function readLocale(): Locale {
  try {
    const stored = localStorage.getItem(localeKey);
    if (stored === "vi" || stored === "en") return stored;
  } catch {
    /* Continue with browser language detection. */
  }
  return detectLocale(navigator.languages ?? []);
}
export function writeLocale(locale: Locale) {
  try {
    localStorage.setItem(localeKey, locale);
  } catch {
    /* The current page still works. */
  }
}
