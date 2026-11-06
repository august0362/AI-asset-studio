import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import tokens from "./tokens.json";

const doc = readFileSync("../../docs/UI.md", "utf8");
const themes = ["latte", "mint", "caffe", "matcha"] as const;
const rows = [
  ...doc.matchAll(
    /\| `(--[^`]+)` \|[^\n]+?\| `(#[\da-f]+)` \| `(#[\da-f]+)` \| `(#[\da-f]+)` \| `(#[\da-f]+)` \|/g,
  ),
];
const css = readFileSync("src/styles/app.css", "utf8");
const themeBlocks = [
  ...css.matchAll(
    /:root\[data-theme="(latte|mint|caffe|matcha)"\]\s*\{([^}]+)\}/g,
  ),
];
const documented = Object.fromEntries(
  themes.map((theme, index) => [
    theme,
    Object.fromEntries(rows.map((row) => [row[1], row[index + 2]])),
  ]),
);
function luminance(hex: string) {
  const channels = [1, 3, 5]
    .map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255)
    .map((value) =>
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
    );
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}
function contrast(first: string, second: string) {
  const [low, high] = [luminance(first), luminance(second)].sort(
    (a, b) => a - b,
  );
  return (high + 0.05) / (low + 0.05);
}
const text = [
  "--text",
  "--text-muted",
  "--primary",
  "--secondary",
  "--success",
  "--warning",
  "--error",
  "--info",
  "--mana",
];
const backgrounds = [
  "--canvas",
  "--surface",
  "--surface-2",
  "--surface-3",
  "--accent-soft",
];
const pairs: [string, string, number][] = [
  ...text.flatMap((fg) =>
    backgrounds.map((bg) => [fg, bg, 4.5] as [string, string, number]),
  ),
  ...["--primary", "--primary-hover"].map(
    (bg) => ["--on-primary", bg, 4.5] as [string, string, number],
  ),
  ...["--border-control", "--focus-ring"].flatMap((fg) =>
    ["--canvas", "--surface", "--surface-2"].map(
      (bg) => [fg, bg, 3] as [string, string, number],
    ),
  ),
  ...["--text", "--mana"].map(
    (fg) => [fg, "--mana-soft", 4.5] as [string, string, number],
  ),
];
describe("canonical theme tokens", () => {
  it("mirrors all 24 documentation tokens exactly in JSON and each CSS theme block", () => {
    expect(rows).toHaveLength(24);
    expect(tokens).toEqual(documented);
    expect(themeBlocks).toHaveLength(4);
    for (const [whole, theme, block] of themeBlocks) {
      expect(whole).toContain(
        `color-scheme: ${["latte", "mint"].includes(theme) ? "light" : "dark"}`,
      );
      const declarations = Object.fromEntries(
        [...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((row) => [
          row[1],
          row[2],
        ]),
      );
      expect(declarations).toEqual(documented[theme]);
    }
    // Guard the pair list itself against drift from the canonical Contrast check.
    const check = doc.split("**Contrast check")[1].split("## 3.")[0];
    for (const token of [
      ...text,
      ...backgrounds,
      "--on-primary",
      "--primary-hover",
      "--border-control",
      "--focus-ring",
      "--mana-soft",
    ])
      expect(check).toContain(`\`${token}\``);
    expect(pairs).toHaveLength(55);
  });
  for (const theme of themes)
    it.each(pairs)(
      `${theme}: %s on %s meets %s:1`,
      (foreground, background, threshold) => {
        expect(
          contrast(
            documented[theme][foreground],
            documented[theme][background],
          ),
        ).toBeGreaterThanOrEqual(threshold);
      },
    );
  it("has no hex literals in TS/TSX or CSS outside the four theme blocks", () => {
    const walk = (path: string): string[] =>
      readdirSync(path, { withFileTypes: true }).flatMap((entry) =>
        entry.isDirectory()
          ? walk(join(path, entry.name))
          : /\.tsx?$/.test(entry.name)
            ? [join(path, entry.name)]
            : [],
      );
    for (const path of walk("src"))
      expect(readFileSync(path, "utf8"), path).not.toMatch(
        /#[\da-f]{3,8}\b|\b0x[\da-f]+/i,
      );
    const remaining = themeBlocks.reduce(
      (rest, match) => rest.replace(match[0], ""),
      css,
    );
    expect(remaining).not.toMatch(/#[\da-f]{3,8}\b|rgba?\(|hsla?\(/i);
    expect(css).toContain("outline: 2px solid var(--focus-ring)");
    for (const status of ["success", "warning", "error", "info"])
      expect(css).toContain(
        `color-mix(in srgb, var(${`--${status}`}) 14%, var(--surface))`,
      );
  });
});
