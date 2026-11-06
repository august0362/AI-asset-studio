import { describe, expect, it } from "vitest";
import { createI18n } from "../../i18n/core";
import { formatModelTime } from "./modelTime";

describe.each(["en", "vi"] as const)("model picker time (%s)", (locale) => {
  const i18n = createI18n(locale);
  const model = (seconds: number | null, is_mock = false) => ({
    is_mock,
    runtime: {
      supported_accelerators: [],
      multi_gpu: "unsupported" as const,
      minimum_gpu_vram_bytes: null,
      estimated_runtime_seconds: seconds,
    },
  });

  it.each([
    [25, "(~25 s/image)", "(~25 giây/ảnh)"],
    [25.6, "(~26 s/image)", "(~26 giây/ảnh)"],
    [89, "(~89 s/image)", "(~89 giây/ảnh)"],
    [89.6, "(~90 s/image)", "(~90 giây/ảnh)"],
    [90, "(~2 min/image)", "(~2 phút/ảnh)"],
    [354, "(~6 min/image)", "(~6 phút/ảnh)"],
    [0, "(~0 s/image)", "(~0 giây/ảnh)"],
  ])("formats %s seconds with whole units", (seconds, en, vi) => {
    expect(formatModelTime(model(seconds), i18n)).toEqual({
      label: locale === "en" ? en : vi,
      tooltip:
        locale === "en"
          ? "Mean time per image measured on a Kaggle T4; excludes setup and download."
          : "Thời gian trung bình mỗi ảnh đo trên Kaggle T4; không bao gồm thiết lập và tải xuống.",
    });
  });

  it.each([25, 90, 354, null])(
    "omits mock time and tooltip (%s)",
    (seconds) => {
      expect(formatModelTime(model(seconds, true), i18n)).toBeUndefined();
    },
  );

  it.each([null, undefined, NaN, Infinity])(
    "omits missing or non-finite time (%s)",
    (seconds) => {
      const value = model(null);
      if (seconds !== undefined)
        value.runtime.estimated_runtime_seconds = seconds;
      else Reflect.deleteProperty(value.runtime, "estimated_runtime_seconds");
      expect(formatModelTime(value, i18n)).toBeUndefined();
    },
  );
});
