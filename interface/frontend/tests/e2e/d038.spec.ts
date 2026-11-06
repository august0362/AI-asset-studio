import { test, expect, type Page } from "./mockTest";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import { readFileSync } from "node:fs";
import { charactersEn } from "../../src/i18n/characters.en";
import { charactersVi } from "../../src/i18n/characters.vi";
const submitted = JSON.parse(readFileSync("tests/fixtures/contracts/v2/batch_manifest_submitted.json", "utf8"));

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { if (!localStorage.getItem("aas.locale")) localStorage.setItem("aas.locale", "en"); });
});
async function create(page: Page, name = "D-038 Ranger") {
  await page.goto("/characters");
  await page.getByRole("button", { name: "Create character", exact: true }).click();
  await page.getByRole("dialog").getByLabel("Character name").fill(name);
  await page.getByRole("dialog").getByRole("button", { name: "Create character", exact: true }).click();
  await expect(page.getByTestId("node-s1")).toBeVisible();
  return new URL(page.url()).pathname.split("/").at(-1)!;
}
async function verifyEdges(page: Page) {
  const edges = await page.locator(".workflow-edge").evaluateAll((paths) => paths.map((edge) => {
    const path = edge as SVGPathElement;
    const from = document.querySelector<HTMLButtonElement>(`[data-node="${path.dataset.from}"]`)!;
    const to = document.querySelector<HTMLButtonElement>(`[data-node="${path.dataset.to}"]`)!;
    const length = path.getTotalLength(), start = path.getPointAtLength(0), end = path.getPointAtLength(length), nearEnd = path.getPointAtLength(length - 0.5);
    return { from: path.dataset.from!, to: path.dataset.to!, marker: path.getAttribute("marker-end"), start: [start.x, start.y], end: [end.x, end.y], expectedStart: [parseFloat(from.style.left) + 202, parseFloat(from.style.top) + 88], expectedEnd: [parseFloat(to.style.left), parseFloat(to.style.top) + 88], pointsRight: end.x > nearEnd.x };
  }));
  expect(edges.length).toBeGreaterThanOrEqual(6);
  for (const edge of edges) {
    expect(Number(edge.from.slice(1))).toBeLessThan(Number(edge.to.slice(1)));
    expect(edge.marker).toBe("url(#flow-arrow)");
    for (const i of [0, 1]) {
      expect(edge.start[i]).toBeCloseTo(edge.expectedStart[i], 2);
      expect(edge.end[i]).toBeCloseTo(edge.expectedEnd[i], 2);
    }
    expect(edge.pointsRight).toBe(true);
  }
}
test("node dragging moves edges without panning, persists per character, resets, and preserves keyboard selection", async ({ page }) => {
  const id = await create(page), key = `aas.canvas.${id}`;
  await verifyEdges(page);
  const node = page.getByTestId("node-s5"), plane = page.getByTestId("workflow-plane");
  const initial = await node.getAttribute("style"), transform = await plane.getAttribute("style");
  const box = (await node.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 30);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 90, box.y + 95, { steps: 12 });
  await page.mouse.up();
  expect(await node.getAttribute("style")).not.toBe(initial);
  expect(await plane.getAttribute("style")).toBe(transform);
  await expect(page.getByTestId("node-s1")).toHaveAttribute("aria-pressed", "true");
  await verifyEdges(page);
  const saved = await page.evaluate((key) => localStorage.getItem(key), key);
  await page.reload();
  await expect(node).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), key)).toBe(saved);
  await verifyEdges(page);
  await node.click();
  await expect(node).toHaveAttribute("aria-pressed", "true");
  await node.press("ArrowRight");
  await expect(page.getByTestId("node-s6")).toBeFocused();
  await expect(page.getByTestId("node-s6")).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Reset layout" }).click();
  await expect(node).toHaveAttribute("style", initial!);
  await verifyEdges(page);
  await page.reload();
  await expect(node).toHaveAttribute("style", initial!);
  await page.evaluate((key) => localStorage.setItem(key, "corrupt"), key);
  await page.reload();
  await expect(node).toHaveAttribute("style", initial!);
  const other = await create(page, "Independent layout");
  expect(other).not.toBe(id);
  await expect(page.getByTestId("node-s5")).toHaveAttribute("style", initial!);
});
test("library row deletion confirms by name, cancels safely, refreshes and survives reload", async ({ page }) => {
  const id = await create(page), key = `aas.canvas.${id}`;
  await page.goto("/characters");
  const row = page.locator(".character-card").filter({ hasText: id });
  await row.getByText("Character actions", { exact: true }).click();
  await row.getByRole("button", { name: "Delete character" }).click();
  await expect(page.getByRole("dialog", { name: "Delete D-038 Ranger?" })).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("Kaggle jobs stay in Jobs.");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(row).toHaveCount(1);
  await row.getByRole("button", { name: "Delete character" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete character" }).click();
  await expect(row).toHaveCount(0);
  expect(await page.evaluate((key) => localStorage.getItem(key), key)).toBeNull();
  await page.reload();
  await expect(row).toHaveCount(0);
  await page.goto(`/characters/${id}`);
  await expect(page.getByText("CHARACTER_NOT_FOUND", { exact: true })).toBeVisible();
});
test("workspace identity deletion returns to the library", async ({ page }) => {
  const id = await create(page);
  await page.locator(".character-identity").getByRole("button", { name: "Delete character" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete character" }).click();
  await expect(page).toHaveURL(/\/characters$/);
  await expect(page.locator(".character-card").filter({ hasText: id })).toHaveCount(0);
});
for (const theme of [
  { id: "latte", mode: "light", family: "coffee" }, { id: "mint", mode: "light", family: "green" },
  { id: "caffe", mode: "dark", family: "coffee" }, { id: "matcha", mode: "dark", family: "green" },
]) for (const locale of ["en", "vi"] as const) {
  test(`delete dialog and running-attempt error axe clean: ${theme.id} ${locale}`, async ({ page }) => {
    const id = await create(page), dict = locale === "en" ? charactersEn : charactersVi;
    await page.evaluate(({ id, submitted, theme, locale }) => {
      const records = JSON.parse(localStorage.getItem("aas.characters.demo.v1")!);
      records[id].batches = [{ ...submitted, character_id: id }];
      localStorage.setItem("aas.characters.demo.v1", JSON.stringify(records));
      localStorage.setItem("aas.theme", JSON.stringify({ mode: theme.mode, family: theme.family }));
      localStorage.setItem("aas.locale", locale);
    }, { id, submitted, theme, locale });
    await page.reload();
    await page.locator(".character-identity").getByRole("button", { name: dict["char.delete"] }).click();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.getByRole("dialog").getByRole("button", { name: dict["char.delete"] }).click();
    await expect(page.getByText("BATCH_ATTEMPT_RUNNING", { exact: true })).toBeVisible();
    await expect(page.getByText(dict["errors.BATCH_ATTEMPT_RUNNING"], { exact: true })).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`/characters/${id}$`));
    expect(await page.evaluate((key) => localStorage.getItem(key), `aas.canvas.${id}`)).not.toBeNull();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await mkdir("test-results/d038", { recursive: true });
    await page.screenshot({ path: `test-results/d038/delete-${theme.id}-${locale}.png`, fullPage: true });
    await page.getByRole("dialog").getByRole("button", { name: dict["char.cancel"] }).click();
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  });
}
