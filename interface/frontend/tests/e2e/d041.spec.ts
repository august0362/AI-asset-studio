// D-041/D-042: auto-run switch, held jobs, Run together, multi-select delete, style images; axe in every theme.
import { test, expect, type Page } from "./mockTest";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem("aas.locale"))
      localStorage.setItem("aas.locale", "en");
  });
});

async function createHeld(page: Page, prompt: string, open = true) {
  if (open) await page.goto("/generate/text-to-2d"); // the mock API lives in the page: later jobs stay in-app
  await page.locator('textarea[name="prompt"]').fill(prompt);
  const toggle = page.getByRole("switch", { name: /auto-run/i });
  if (await toggle.isChecked()) await toggle.uncheck();
  await page.locator('select[name="accelerator"]').selectOption("gpu_t4x2");
  const generate = page.locator("button.generate-button");
  await expect(generate).toBeEnabled();
  await generate.click();
  await expect(page.getByRole("link", { name: /view job/i })).toBeVisible();
}

test("auto-run off keeps jobs held; the switch is remembered; Run together reports why mocks cannot share a session", async ({
  page,
}) => {
  await createHeld(page, "First held blade");
  await page.reload();
  await expect(
    page.getByRole("switch", { name: /auto-run/i }),
  ).not.toBeChecked(); // remembered
  await createHeld(page, "Second held blade", false);
  await createHeld(page, "Third held blade", false); // a held job does not block the next one
  await page.getByRole("link", { name: "Jobs & logs" }).click();
  const held = page.locator(".job-row-wrap", { hasText: "Held" });
  await expect(held).toHaveCount(2); // the first one was created before the reload
  const together = page.getByRole("button", { name: "Run together" });
  await expect(together).toBeDisabled();
  for (const row of await held.all()) await row.getByRole("checkbox").check();
  await expect(together).toBeEnabled();
  await together.click();
  await expect(
    page.getByText("These two jobs cannot run together in one session."),
  ).toBeVisible(); // JOB_GROUP_INVALID (vram)
  // Turning auto-run on runs a held job.
  await held.first().getByRole("switch").click(); // controlled: flips once the API answers
  await expect(page.locator(".job-row-wrap", { hasText: "Held" })).toHaveCount(
    1,
  );
});

test("select all completed and delete them with one confirmation", async ({
  page,
}) => {
  await page.goto("/jobs");
  await page.getByRole("button", { name: "Select all completed" }).click();
  await expect(page.getByText(/^\d+ selected$/)).not.toHaveText("0 selected");
  let dialogs = 0;
  page.on("dialog", (dialog) => {
    dialogs += 1;
    void dialog.accept();
  });
  await page.getByRole("button", { name: "Delete selected" }).click();
  await expect(page.getByText(/^Deleted \d+ job\(s\)\.$/)).toBeVisible();
  expect(dialogs).toBe(1);
  await page.getByRole("button", { name: /^all$/i }).click();
  await expect(page.getByText("0 selected")).toBeVisible();
});

test("style images: area, hint and paste for a style-reference model; no area for a prompt-only model", async ({
  page,
}) => {
  await page.goto("/generate/text-to-2d");
  await expect(page.getByText("Style images", { exact: true })).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Model" })
    .selectOption("mock-t2d-styleref");
  await expect(page.getByText("Style images", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/use only the style of the reference images/i),
  ).toBeVisible();
  await expect(
    page.getByText("You can also paste an image with Ctrl+V."),
  ).toBeVisible();
});

test("library assets carry a mock label only for mock models and can be deleted", async ({
  page,
}) => {
  await page.goto("/library");
  const card = page.locator("article.asset-card").first();
  await expect(card.locator(".badge").first()).toContainText("MOCK"); // the seeded assets come from mock models
  page.once("dialog", (dialog) => {
    expect(dialog.message()).toMatch(
      /Delete job job_\S+ and its \d+ image\(s\)\?/,
    );
    void dialog.accept();
  });
  const before = await page.locator("article.asset-card").count();
  await card.getByRole("button", { name: /Delete the asset of job/ }).click();
  await expect(page.locator("article.asset-card")).toHaveCount(before - 1);
});

const themes = [
  { id: "latte", mode: "light", family: "coffee" },
  { id: "mint", mode: "light", family: "green" },
  { id: "caffe", mode: "dark", family: "coffee" },
  { id: "matcha", mode: "dark", family: "green" },
] as const;
for (const theme of themes)
  for (const locale of ["en", "vi"] as const)
    test(`run control and style images are axe clean · ${theme.id} ${locale}`, async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await createHeld(page, `Axe ${theme.id}`);
      await page.evaluate(
        ({ theme, locale }) => {
          localStorage.setItem(
            "aas.theme",
            JSON.stringify({ mode: theme.mode, family: theme.family }),
          );
          localStorage.setItem("aas.locale", locale);
        },
        { theme, locale },
      );
      await mkdir(`test-results/d041/${theme.id}`, { recursive: true });
      for (const width of [1024, 1440, 390]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const name of ["jobs", "generate"] as const) {
          await page.goto(name === "jobs" ? "/jobs" : "/generate/text-to-2d");
          await expect(page.locator("html")).toHaveAttribute(
            "data-theme",
            theme.id,
          );
          await expect(page.locator("main h1")).toBeVisible();
          if (name === "generate")
            await page
              .getByRole("combobox", { name: /model|mô hình/i })
              .selectOption("mock-t2d-styleref");
          else
            await page
              .locator(".job-row-wrap")
              .first()
              .getByRole("checkbox")
              .check();
          await page.evaluate(() => document.fonts.ready);
          const results = await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
            .analyze();
          expect(
            results.violations.map((v) => ({
              id: v.id,
              nodes: v.nodes.map((n) => n.target),
            })),
          ).toEqual([]);
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          ).toBe(true);
          await page.screenshot({
            path: `test-results/d041/${theme.id}/${name}-${locale}-${width}.png`,
            fullPage: true,
          });
        }
      }
    });
