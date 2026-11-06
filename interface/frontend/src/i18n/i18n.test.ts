import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { en } from "./en";
import { vi } from "./vi";
import { createI18n } from "./core";
import { issue } from "../api/errors";
import { validationIssue } from "./validation";
describe("canonical localization", () => {
  it("creates English validation messages from the source dictionary and renders the same code in Vietnamese", () => {
    const item = validationIssue(
      "MODEL_INPUT_COUNT_EXCEEDED",
      "inputs",
      "error",
      { max_images: 1, provided: 3 },
    );
    expect(item.message).toBe(
      "This model accepts at most 1 image(s); 3 were provided.",
    );
    expect(createI18n("vi").errorText(item)).toContain(
      "tối đa 1 ảnh; đã có 3 ảnh",
    );
    expect(item.details).toEqual({ max_images: 1, provided: 3 });
  });
  it("keeps frontend validators free of independent UI messages", () => {
    for (const path of [
      "src/validation/validate.ts",
      "src/validation/planner.ts",
    ]) {
      const tree = ts.createSourceFile(
        path,
        readFileSync(path, "utf8"),
        ts.ScriptTarget.Latest,
        true,
      );
      const messages: string[] = [];
      const visit = (node: ts.Node) => {
        if (ts.isStringLiteral(node) && /[a-z] [A-Za-z]/.test(node.text))
          messages.push(node.text);
        ts.forEachChild(node, visit);
      };
      visit(tree);
      expect(messages, path).toEqual([]);
    }
  });
  it("keeps exactly the same English/Vietnamese keys and nonempty values", () => {
    expect(Object.keys(vi).sort()).toEqual(Object.keys(en).sort());
    for (const value of Object.values(vi)) expect(value.trim()).not.toBe("");
  });
  it("covers exactly every CONTRACTS §8.2 and §13.7 error code in both dictionaries", () => {
    const section = readFileSync("../../docs/CONTRACTS.md", "utf8")
      .split("### 8.2 Error codes")[1]
      .split("### 8.3")[0];
    const additions = readFileSync("../../docs/CONTRACTS.md", "utf8")
      .split("### 13.7 Error codes (additions)")[1]
      .split("All other codes")[0];
    const codes = [
      ...new Set(
        [...(section + additions).matchAll(/`([A-Z][A-Z0-9_]+)`/g)].map(
          (match) => match[1],
        ),
      ),
    ].sort();
    for (const dictionary of [en, vi])
      expect(
        Object.keys(dictionary)
          .filter((key) => key.startsWith("errors."))
          .map((key) => key.slice(7))
          .sort(),
      ).toEqual(codes);
  });
  it("translates details and localizes role names without changing the ErrorItem", () => {
    const error = issue(
      "MODEL_REQUIRED_VIEW_MISSING",
      "inputs",
      "English fallback",
      "error",
      { missing_roles: ["front", "side"] },
    );
    expect(createI18n("vi").errorText(error)).toBe(
      "Hãy thêm ảnh góc Mặt trước và Mặt bên theo yêu cầu.",
    );
    expect(error.details.missing_roles).toEqual(["front", "side"]);
    expect(
      createI18n("vi").errorText(
        issue("MODEL_INPUT_COUNT_EXCEEDED", "inputs", "fallback", "error", {
          max_images: 1,
          provided: 3,
        }),
      ),
    ).toContain("tối đa 1 ảnh; đã có 3 ảnh");
  });
  it("falls back to the backend message for unknown codes or missing placeholders", () => {
    const translate = createI18n("vi").errorText;
    expect(
      translate({
        code: "FUTURE_CODE" as "INTERNAL_ERROR",
        message: "The backend explains the new condition.",
        details: {},
      }),
    ).toBe("The backend explains the new condition.");
    expect(
      translate(
        issue(
          "MODEL_INPUT_COUNT_EXCEEDED",
          "inputs",
          "Only one image is supported.",
          "error",
          { max_images: 1 },
        ),
      ),
    ).toBe("Only one image is supported.");
  });
  it("formats numbers, dates and units in the active app locale", () => {
    const vietnamese = createI18n("vi"),
      english = createI18n("en");
    expect(vietnamese.number(18.5)).toBe("18,5");
    expect(english.number(18.5)).toBe("18.5");
    expect(vietnamese.duration(66600)).toBe("18,5 giờ");
    expect(english.duration(66600)).toBe("18.5 h");
    expect(vietnamese.date("2026-11-06T00:00:00Z")).toBe(
      new Intl.DateTimeFormat("vi-VN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date("2026-11-06T00:00:00Z")),
    );
  });
  it("has no JSX text or label/title/placeholder literals outside dictionaries, apart from the brand", () => {
    const walk = (path: string): string[] =>
      readdirSync(path, { withFileTypes: true }).flatMap((entry) =>
        entry.isDirectory()
          ? walk(join(path, entry.name))
          : entry.name.endsWith(".tsx") && !entry.name.includes(".test.")
            ? [join(path, entry.name)]
            : [],
      );
    const violations: string[] = [];
    for (const path of walk("src")) {
      const tree = ts.createSourceFile(
        path,
        readFileSync(path, "utf8"),
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );
      const visit = (node: ts.Node) => {
        if (
          ts.isJsxText(node) &&
          /\p{L}/u.test(node.text) &&
          !["AI Asset", "Studio"].includes(node.text.trim())
        )
          violations.push(`${path}: ${node.text.trim()}`);
        if (
          ts.isJsxAttribute(node) &&
          ["aria-label", "title", "placeholder"].includes(
            node.name.getText(tree),
          ) &&
          node.initializer &&
          ts.isStringLiteral(node.initializer)
        )
          violations.push(`${path}: ${node.getText(tree)}`);
        ts.forEachChild(node, visit);
      };
      visit(tree);
    }
    expect(violations).toEqual([]);
  });
});
