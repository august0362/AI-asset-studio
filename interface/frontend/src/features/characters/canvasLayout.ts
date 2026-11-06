import type { StageId } from "../../api/characterTypes";

export type Position = [number, number];
export type CanvasLayout = Record<StageId, Position>;
export const defaultLayout: CanvasLayout = {
  s1: [32, 60], s2: [266, 60], s3: [500, 60], s4: [734, 60],
  s5: [734, 340], s6: [500, 340], s7: [266, 340],
};
export const canvasKey = (id: string) => `aas.canvas.${id}`;
export function readLayout(id: string): CanvasLayout {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(canvasKey(id)) ?? "null");
    if (value && typeof value === "object" && Object.keys(value).length === 7 &&
      Object.keys(defaultLayout).every((key) => {
        const point = (value as Record<string, unknown>)[key];
        return Array.isArray(point) && point.length === 2 && point.every((n) => typeof n === "number" && Number.isFinite(n));
      })) return value as CanvasLayout;
  } catch { /* Use the default layout when storage is unavailable. */ }
  return structuredClone(defaultLayout);
}
export function saveLayout(id: string, layout: CanvasLayout) {
  try { localStorage.setItem(canvasKey(id), JSON.stringify(layout)); }
  catch { /* Positions remain usable in memory. */ }
}
export function removeLayout(id: string) {
  try { localStorage.removeItem(canvasKey(id)); }
  catch { /* Deletion must remain usable without browser storage. */ }
}
/** Ports always face right: start at the output, end at the next input. */
export function edgePath(from: Position, to: Position): string {
  const [sx, sy] = [from[0] + 202, from[1] + 88];
  const [tx, ty] = [to[0], to[1] + 88];
  if (tx > sx)
    return `M${sx},${sy} C${sx + 24},${sy} ${tx - 24},${ty} ${tx},${ty}`;
  const lane = Math.min(from[1], to[1]) - 32;
  return `M${sx},${sy} C${sx + 24},${sy} ${sx + 24},${lane} ${sx + 24},${lane} L${tx - 24},${lane} C${tx - 24},${lane} ${tx - 24},${ty} ${tx},${ty}`;
}
