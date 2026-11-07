import { useI18n } from "../../i18n";
import type { OptionSchema, OptionValue } from "../../api/types";

/** Animagine's `style_strength` (CONTRACTS §14.9): the IP-Adapter scale, shown only with a style image. */
export function StyleStrength({
  rule,
  value,
  invalid,
  onChange,
}: {
  rule: OptionSchema;
  value: OptionValue | undefined;
  invalid: boolean;
  onChange: (value: number) => void;
}) {
  const { t, number } = useI18n();
  const min = rule.minimum ?? 0,
    max = rule.maximum ?? 1;
  const current =
    typeof value === "number"
      ? value
      : typeof rule.default === "number"
        ? rule.default
        : 0.6;
  return (
    <label className="field style-strength">
      <span>
        {t("style.strength")}{" "}
        <output htmlFor="style-strength">{number(current, 2)}</output>
      </span>
      <input
        id="style-strength"
        name="style_strength"
        type="range"
        min={min}
        max={max}
        step={0.05}
        value={current}
        aria-label={t("style.strength")}
        aria-invalid={invalid}
        aria-valuetext={number(current, 2)}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <small>{t("style.strengthHelp")}</small>
    </label>
  );
}
