import { beforeEach, describe, expect, it, vi } from "vitest";
import { canvasKey, defaultLayout, edgePath, readLayout, removeLayout, saveLayout } from "./canvasLayout";

beforeEach(() => localStorage.clear());
describe("per-character canvas layout", () => {
  it.each([null, "broken", "null", "[]", "{}", JSON.stringify({ ...defaultLayout, s3: ["x", 10] }), JSON.stringify({ ...defaultLayout, s3: [null, 10] }), JSON.stringify({ ...defaultLayout, s8: [10, 10] })])("falls back for missing or corrupt data: %s", (value) => {
    if (value !== null) localStorage.setItem(canvasKey("a"), value);
    expect(readLayout("a")).toEqual(defaultLayout);
  });
  it("persists positions separately, resets and removes only that character", () => {
    const moved = { ...defaultLayout, s5: [-120, 900] as [number, number] };
    saveLayout("a", moved);
    saveLayout("b", moved);
    expect(readLayout("a")).toEqual(moved);
    saveLayout("a", defaultLayout);
    expect(readLayout("a")).toEqual(defaultLayout);
    removeLayout("a");
    expect(localStorage.getItem(canvasKey("a"))).toBeNull();
    expect(readLayout("b")).toEqual(moved);
  });
  it("handles storage reads, writes and removal throwing", () => {
    for (const method of ["getItem", "setItem", "removeItem"] as const)
      vi.spyOn(Storage.prototype, method).mockImplementation(() => { throw new Error("Storage blocked"); });
    expect(readLayout("a")).toEqual(defaultLayout);
    expect(() => saveLayout("a", defaultLayout)).not.toThrow();
    expect(() => removeLayout("a")).not.toThrow();
  });
  it.each([
    [defaultLayout.s5, defaultLayout.s6], [defaultLayout.s6, defaultLayout.s7],
    [[-300, 400], [800, -100]], [[800, -100], [-300, 400]], [[1, 1], [1, 1]],
  ] as [[number, number], [number, number]][])("routes from output %s to input %s, approaching the input from the left", (from, to) => {
    const path = edgePath(from, to);
    expect(path.startsWith(`M${from[0] + 202},${from[1] + 88} C${from[0] + 226},${from[1] + 88}`)).toBe(true);
    expect(path.endsWith(`${to[0] - 24},${to[1] + 88} ${to[0]},${to[1] + 88}`)).toBe(true);
  });
});
