import { useI18n } from "../i18n";
import { useTheme } from "./ThemeProvider";
import { resolveTheme } from "./settings";
import tokens from "./tokens.json";
export function PreferenceSwitchers() {
  const { settings, theme, setSettings } = useTheme();
  const { t, locale, setLocale } = useI18n();
  return (
    <div className="preferences">
      <div className="segmented" role="group" aria-label={t("theme.mode")}>
        {(["light", "dark", "system"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            aria-pressed={settings.mode === mode}
            onClick={() => setSettings({ ...settings, mode })}
          >
            {t(`theme.${mode}`)}
          </button>
        ))}
      </div>
      <div className="segmented" role="group" aria-label={t("theme.family")}>
        {(["coffee", "green"] as const).map((family) => (
          <button
            key={family}
            type="button"
            aria-pressed={settings.family === family}
            onClick={() => setSettings({ ...settings, family })}
          >
            <span
              className="family-swatch"
              aria-hidden="true"
              style={{
                backgroundColor:
                  tokens[
                    resolveTheme(
                      {
                        mode:
                          theme === "caffe" || theme === "matcha"
                            ? "dark"
                            : "light",
                        family,
                      },
                      false,
                    )
                  ]["--primary"],
              }}
            />
            {t(`theme.${family}`)}
          </button>
        ))}
      </div>
      <label className="locale-switcher">
        <span className="sr-only">{t("locale.label")}</span>
        <select
          value={locale}
          onChange={(event) => setLocale(event.target.value as "vi" | "en")}
        >
          <option value="vi">{t("locale.vi")}</option>
          <option value="en">{t("locale.en")}</option>
        </select>
      </label>
    </div>
  );
}
