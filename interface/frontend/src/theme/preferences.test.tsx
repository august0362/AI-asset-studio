import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  defaults,
  readTheme,
  resolveTheme,
  writeTheme,
  type ThemeSettings,
} from "./settings";
import { ThemeProvider } from "./ThemeProvider";
import { PreferenceSwitchers } from "./PreferenceSwitchers";
import { I18nProvider } from "../i18n";
import { detectLocale, readLocale, writeLocale } from "../i18n/settings";

let query: MediaQueryList;
let change: (() => void) | undefined;
beforeEach(() => {
  localStorage.clear();
  change = undefined;
  query = {
    matches: false,
    addEventListener: vi.fn((_type, listener) => {
      change = listener as () => void;
    }),
    removeEventListener: vi.fn(),
  } as unknown as MediaQueryList;
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => query),
  );
});
function mount() {
  return render(
    <ThemeProvider>
      <I18nProvider>
        <PreferenceSwitchers />
      </I18nProvider>
    </ThemeProvider>,
  );
}
describe("theme and locale preferences", () => {
  it.each([
    ["light", "coffee", false, "latte"],
    ["light", "green", true, "mint"],
    ["dark", "coffee", false, "caffe"],
    ["dark", "green", false, "matcha"],
    ["system", "coffee", false, "latte"],
    ["system", "coffee", true, "caffe"],
    ["system", "green", false, "mint"],
    ["system", "green", true, "matcha"],
  ] as const)(
    "resolves %s + %s with OS dark=%s",
    (mode, family, dark, theme) => {
      expect(resolveTheme({ mode, family }, dark)).toBe(theme);
    },
  );
  it("persists only mode/family and restores them", () => {
    const choice: ThemeSettings = { mode: "dark", family: "green" };
    expect(readTheme()).toEqual(defaults);
    writeTheme(choice);
    expect(JSON.parse(localStorage.getItem("aas.theme")!)).toEqual(choice);
    expect(readTheme()).toEqual(choice);
    localStorage.setItem("aas.theme", '{"mode":"invalid","family":"green"}');
    expect(readTheme()).toEqual(defaults);
    localStorage.setItem("aas.theme", "not-json");
    expect(readTheme()).toEqual(defaults);
    localStorage.setItem("aas.theme", '{"mode":["dark"],"family":"green"}');
    expect(readTheme()).toEqual(defaults);
  });
  it("uses defaults when theme storage reads or writes throw", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    expect(readTheme()).toEqual(defaults);
    expect(writeTheme({ mode: "dark", family: "green" })).toEqual(defaults);
    expect(() => mount()).not.toThrow();
  });
  it("follows OS changes live in system mode and ignores them in explicit mode", async () => {
    const user = userEvent.setup();
    const view = mount();
    expect(document.documentElement.dataset.theme).toBe("latte");
    act(() => {
      Object.defineProperty(query, "matches", {
        value: true,
        configurable: true,
      });
      change?.();
    });
    expect(document.documentElement.dataset.theme).toBe("caffe");
    await user.click(screen.getByRole("button", { name: "Light" }));
    expect(document.documentElement.dataset.theme).toBe("latte");
    act(() => {
      Object.defineProperty(query, "matches", {
        value: false,
        configurable: true,
      });
      change?.();
    });
    expect(document.documentElement.dataset.theme).toBe("latte");
    view.unmount();
    expect(query.removeEventListener).toHaveBeenCalled();
  });
  it("operates mode and family buttons using Tab, Enter and Space", async () => {
    const user = userEvent.setup();
    mount();
    await user.tab();
    expect(screen.getByRole("button", { name: "Light" })).toHaveFocus();
    await user.tab();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Dark" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await user.tab();
    await user.tab();
    await user.tab();
    await user.keyboard(" ");
    expect(screen.getByRole("button", { name: "Green" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(document.documentElement.dataset.theme).toBe("matcha");
    expect(readTheme()).toEqual({ mode: "dark", family: "green" });
  });
  it.each([
    [["en-US", "vi-VN"], "vi"],
    [["VI"], "vi"],
    [["fr", "en"], "en"],
    [[], "en"],
  ] as const)("detects locale from %j", (languages, expected) => {
    expect(detectLocale(languages)).toBe(expected);
  });
  it("persists locale, detects the first visit, and survives storage failures", () => {
    vi.spyOn(navigator, "languages", "get").mockReturnValue(["en", "vi-VN"]);
    expect(readLocale()).toBe("vi");
    writeLocale("en");
    expect(readLocale()).toBe("en");
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("disabled");
    });
    expect(readLocale()).toBe("vi");
    expect(() => writeLocale("vi")).not.toThrow();
  });
  it("switches language with the keyboard and syncs html lang, labels and persistence", async () => {
    const user = userEvent.setup();
    const view = mount();
    const select = screen.getByRole("combobox", { name: "Language" });
    select.focus();
    await user.selectOptions(select, "vi");
    expect(document.documentElement.lang).toBe("vi");
    expect(
      screen.getByRole("button", { name: "Theo hệ thống" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(localStorage.getItem("aas.locale")).toBe("vi");
    view.unmount();
    mount();
    expect(screen.getByRole("combobox", { name: "Ngôn ngữ" })).toHaveValue(
      "vi",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Ngôn ngữ" }),
      "en",
    );
    expect(document.documentElement.lang).toBe("en");
  });
});
