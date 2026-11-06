import { useI18n } from "../../i18n";
import type { ModelCapabilities, OptionValue } from "../../api/types";
export function ModelOptions({
  model,
  values,
  onChange,
  invalid,
}: {
  model: ModelCapabilities;
  values: Record<string, OptionValue>;
  onChange: (key: string, value: OptionValue) => void;
  invalid: string[];
}) {
  const { t, label, number } = useI18n();
  return (
    <div className="options-grid">
      {Object.entries(model.options_schema).map(([name, rule]) => {
        const value = values[name] === undefined ? rule.default : values[name];
        const optionLabel = label("option", name);
        return (
          <label
            className={`field ${name === "negative_prompt" ? "span-two" : ""}`}
            key={name}
          >
            <span>{optionLabel}</span>
            {rule.enum ? (
              <select
                name={name}
                value={String(value ?? "")}
                aria-invalid={invalid.includes(`options.${name}`)}
                onChange={(e) =>
                  onChange(
                    name,
                    rule.type === "integer" || rule.type === "number"
                      ? Number(e.target.value)
                      : e.target.value,
                  )
                }
              >
                {rule.enum.map((v) => (
                  <option key={String(v)} value={String(v)}>
                    {typeof v === "number" ? number(v, 0) : String(v)}
                  </option>
                ))}
              </select>
            ) : rule.type === "boolean" ? (
              <input
                type="checkbox"
                name={name}
                checked={Boolean(value)}
                onChange={(e) => onChange(name, e.target.checked)}
              />
            ) : (
              <input
                name={name}
                autoComplete="off"
                type={rule.type === "string" ? "text" : "number"}
                min={rule.minimum}
                max={rule.maximum}
                step={rule.type === "integer" ? 1 : "any"}
                value={value === null ? "" : String(value)}
                placeholder={rule.default === null ? t("copy.auto") : undefined}
                aria-invalid={invalid.includes(`options.${name}`)}
                onChange={(e) =>
                  onChange(
                    name,
                    e.target.value === ""
                      ? null
                      : rule.type === "string"
                        ? e.target.value
                        : Number(e.target.value),
                  )
                }
              />
            )}
            {rule.description && (
              <small>
                {label("option.description", name, rule.description)}
              </small>
            )}
          </label>
        );
      })}
    </div>
  );
}
