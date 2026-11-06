// D-039: smooth node drag, data-flow edges, double-click/Enter opens Stage Detail, V2 Stitch look in every theme.
import { test, expect, type Page } from "./mockTest";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem("aas.locale")) localStorage.setItem("aas.locale", "en");
    // Count layout writes so a drag can be shown to save once, on drop.
    const original = Storage.prototype.setItem;
    (window as unknown as { canvasWrites: number }).canvasWrites = 0;
    Storage.prototype.setItem = function (key: string, value: string) {
      if (key.startsWith("aas.canvas.")) (window as unknown as { canvasWrites: number }).canvasWrites++;
      return original.call(this, key, value);
    };
  });
});
async function create(page: Page, name = "D-039 Ranger") {
  await page.goto("/characters");
  await page.getByRole("button", { name: "Create character", exact: true }).click();
  await page.getByRole("dialog").getByLabel("Character name").fill(name);
  await page.getByRole("dialog").getByRole("button", { name: "Create character", exact: true }).click();
  await expect(page.getByTestId("node-s1")).toBeVisible();
  return new URL(page.url()).pathname;
}
async function approveS1(page: Page, path: string) {
  await page.goto(`${path}/stages/s1`);
  await page.getByRole("textbox", { name: "Raw idea", exact: true }).fill("A silver-haired ranger");
  await page.getByLabel("Design directions (one per line, up to 3)").fill("Calm fantasy ranger");
  for (const box of await page.locator('.character-approval input[type="checkbox"]').all()) await box.check();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Draft saved" })).toBeVisible();
  await page.getByRole("button", { name: "Submit for review", exact: true }).click();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Decision recorded" })).toBeVisible();
}
const writes = (page: Page) => page.evaluate(() => (window as unknown as { canvasWrites: number }).canvasWrites);

test("drag moves only the node and its edges per frame, commits and saves once on drop", async ({ page }) => {
  await create(page);
  const node = page.getByTestId("node-s5"),
    edge = page.locator('.workflow-edge[data-from="s4"][data-to="s5"]');
  const style = await node.getAttribute("style"),
    d = await edge.getAttribute("d"),
    before = await writes(page);
  const box = (await node.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 30);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 - 90, box.y + 95, { steps: 15 });
  await page.evaluate(() => new Promise(requestAnimationFrame));
  // While lifted: React state (left/top) is untouched; the node moves by transform and its edge follows.
  await expect(node).toHaveAttribute("data-dragging", "true");
  expect(await node.getAttribute("style")).toContain(style!.replace(/;$/, ""));
  expect(await node.evaluate((el) => el.style.transform)).toMatch(/^translate\(/);
  expect(await edge.getAttribute("d")).not.toBe(d);
  expect(await writes(page)).toBe(before);
  await page.mouse.up();
  await expect(node).not.toHaveAttribute("data-dragging", "true");
  expect(await node.evaluate((el) => el.style.transform)).toBe("");
  expect(await node.getAttribute("style")).not.toBe(style);
  expect(await writes(page)).toBe(before + 1);
  // A drag is never a double-click, and never opens the stage.
  await expect(page).not.toHaveURL(/\/stages\//);
});

test("double-click and Enter on a node open its Stage Detail; Back keeps the node", async ({ page }) => {
  const path = await create(page);
  await page.getByTestId("node-s3").dblclick();
  await expect(page).toHaveURL(`${path}/stages/s3`);
  await page.getByRole("link", { name: "Back to workspace", exact: true }).click();
  await expect(page).toHaveURL(`${path}?node=s3`);
  await expect(page.getByTestId("node-s3")).toBeFocused();
  await page.getByTestId("node-s3").press("ArrowRight");
  await expect(page.getByTestId("node-s4")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`${path}/stages/s4`);
  // Space still only selects.
  await page.goBack();
  await page.getByTestId("node-s2").focus();
  await page.keyboard.press("Space");
  await expect(page.getByTestId("node-s2")).toHaveAttribute("aria-pressed", "true");
  await expect(page).not.toHaveURL(/\/stages\//);
});

test("data flows only from approved, non-stale upstream stages and stops under reduced motion", async ({ page }) => {
  const path = await create(page);
  await expect(page.locator(".workflow-flow")).toHaveCount(0);
  await expect(page.locator('.workflow-edge[data-flowing="true"]')).toHaveCount(0);
  await approveS1(page, path);
  await page.goto(path);
  await expect(page.getByTestId("node-s1")).toBeVisible();
  const fromS1 = await page.locator('.workflow-edge[data-from="s1"]').count();
  expect(fromS1).toBeGreaterThan(0);
  await expect(page.locator('.workflow-edge[data-flowing="true"]')).toHaveCount(fromS1);
  await expect(page.locator(".workflow-flow")).toHaveCount(fromS1);
  for (const from of await page.locator(".workflow-flow").evaluateAll((paths) => paths.map((p) => (p as SVGPathElement).dataset.from)))
    expect(from).toBe("s1");
  // The pulse follows the edge geometry exactly and animates from output to input.
  const flow = page.locator(".workflow-flow").first();
  const from = await flow.getAttribute("data-to");
  expect(await flow.getAttribute("d")).toBe(
    await page.locator(`.workflow-edge[data-from="s1"][data-to="${from}"]`).getAttribute("d"),
  );
  expect(await flow.evaluate((el) => getComputedStyle(el).animationName)).toBe("mana-flow");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await flow.evaluate((el) => getComputedStyle(el).animationName)).toBe("none");
  expect(await flow.evaluate((el) => getComputedStyle(el).strokeDasharray)).toBe("none");
});

const themes = [
  { id: "latte", mode: "light", family: "coffee" },
  { id: "mint", mode: "light", family: "green" },
  { id: "caffe", mode: "dark", family: "coffee" },
  { id: "matcha", mode: "dark", family: "green" },
] as const;
for (const theme of themes)
  for (const locale of ["en", "vi"] as const)
    test(`V2 Stitch look axe clean: library, workspace, stage detail · ${theme.id} ${locale}`, async ({ page }) => {
      test.setTimeout(120_000);
      const path = await create(page, `Look ${theme.id}`);
      await page.evaluate(({ theme, locale }) => {
        localStorage.setItem("aas.theme", JSON.stringify({ mode: theme.mode, family: theme.family }));
        localStorage.setItem("aas.locale", locale);
      }, { theme, locale });
      await mkdir(`test-results/d039/${theme.id}`, { recursive: true });
      for (const width of [1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const [name, url] of [["library", "/characters"], ["workspace", `${path}?node=s2`], ["stage", `${path}/stages/s1`]]) {
          await page.goto(url);
          await expect(page.locator("html")).toHaveAttribute("data-theme", theme.id);
          await expect(page.locator("main h1")).toBeVisible();
          await page.evaluate(() => document.fonts.ready);
          const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
          expect(results.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
          await page.screenshot({ path: `test-results/d039/${theme.id}/${name}-${locale}-${width}.png`, fullPage: true });
        }
      }
    });
