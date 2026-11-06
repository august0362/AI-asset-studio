import { expect, test, type Page } from "./mockTest";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import type { CharacterWorkflow } from "../../src/api/characterTypes";
import type { GenerationResult } from "../../src/api/types";
const sharedWorkflow = JSON.parse(
  readFileSync("tests/fixtures/contracts/v2/character_workflow.json", "utf8"),
) as CharacterWorkflow;
const sharedJob = JSON.parse(
  readFileSync("tests/fixtures/contracts/v2/job_batch_partial.json", "utf8"),
) as GenerationResult;
const titles = [
  "Concept exploration",
  "Character specification",
  "Concept validation",
  "Prompt engineering",
  "2D asset production",
  "3D reconstruction",
  "Rigging & validation",
];
async function create(
  page: Page,
  name = "DEMO Character",
  tags = "fantasy, ranger",
) {
  await page.goto("/characters");
  await page
    .getByRole("button", { name: "Create character", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Character name").fill(name);
  await dialog.getByLabel("Tags (comma separated)").fill(tags);
  await dialog
    .getByRole("button", { name: "Create character", exact: true })
    .click();
  await expect(page.getByTestId("node-s1")).toBeVisible();
  return new URL(page.url()).pathname;
}
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    if (!localStorage.getItem("aas.locale"))
      localStorage.setItem("aas.locale", "en");
  });
});
test("mock browser fixture blocks backend network access", async ({ page }) => {
  await page.goto("/characters");
  const reached = await page.evaluate(async () => {
    try {
      await fetch("http://127.0.0.1:8000/api/v1/health");
      return true;
    } catch {
      return false;
    }
  });
  expect(reached).toBe(false);
});

test("shared backend snapshots render stages and task images with byte-exact downloads", async ({
  page,
}) => {
  const id = sharedWorkflow.character.character_id;
  await page.goto(`/characters/${id}/stages/s4`);
  await expect(page.locator("main h1")).toBeVisible();
  await expect(page.locator('a[href*="bat_000000000000"]')).toHaveCount(0);
  await page.goto(`/jobs/${sharedJob.job_id}`);
  for (const artifact of sharedJob.artifacts) {
    await expect(
      page.getByText(artifact.task_id!, { exact: true }),
    ).toBeVisible();
  }
  const images = page.locator(".image-preview img");
  await expect(images).toHaveCount(sharedJob.artifacts.length);
  for (const image of await images.all()) {
    await expect
      .poll(() =>
        image.evaluate(
          (node: HTMLImageElement) => node.complete && node.naturalWidth,
        ),
      )
      .toBe(512);
  }
  const artifact = sharedJob.artifacts[0];
  const downloading = page.waitForEvent("download");
  await page
    .getByRole("button", { name: /Download PNG/ })
    .first()
    .click();
  const download = await downloading;
  const bytes = await readFile((await download.path())!);
  expect(bytes.length).toBe(artifact.size_bytes);
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(
    artifact.sha256,
  );
  await mkdir("test-results/v2/shared-fixtures", { recursive: true });
  await page.screenshot({
    path: "test-results/v2/shared-fixtures/batch-job.png",
    fullPage: true,
  });
});
test("V2 library create, search, tag/stage/status filters, rename and reload", async ({
  page,
}) => {
  const path = await create(page);
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Character name")
    .fill("Renamed Ranger");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Rename", exact: true })
    .click();
  await expect(page.locator("h1")).toHaveText("Renamed Ranger");
  await page.reload();
  await expect(page.locator("h1")).toHaveText("Renamed Ranger");
  await create(page, "DEMO Mage", "mage");
  await page.goto("/characters");
  await expect(page.locator(".character-card")).toHaveCount(4);
  await page
    .getByLabel("Search name, ID or tags")
    .fill(path.split("/").at(-1)!);
  await expect(page.locator(".character-card")).toHaveCount(1);
  await page.getByLabel("Search name, ID or tags").fill("");
  await page.getByLabel("Style / tag").selectOption("mage");
  await expect(page.locator(".character-card")).toHaveCount(2);
  await page.getByLabel("Style / tag").selectOption("");
  await page
    .getByRole("combobox", { name: "Stage", exact: true })
    .selectOption("s5");
  await expect(
    page.getByText("No characters yet", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Stage", exact: true })
    .selectOption("");
  await page
    .getByRole("combobox", { name: "Stage", exact: true })
    .selectOption("s1");
  await page.getByLabel("Editorial status").selectOption("not_started");
  await expect(page.locator(".character-card")).toHaveCount(2);
});
test("V2 all seven nodes show their own inspector, fixed graph, zoom/pan/fit and round-trip selection", async ({
  page,
}) => {
  const path = await create(page);
  await expect(page.locator(".workflow-node")).toHaveCount(7);
  await expect(page.locator(".workflow-edge")).toHaveCount(10);
  await expect(page.locator('.workflow-edge[data-kind="soft"]')).toHaveCount(3);
  for (let i = 1; i <= 7; i++) {
    await page.getByTestId(`node-s${i}`).click();
    const inspector = page.getByTestId("flow-inspector");
    await expect(inspector).toHaveAttribute("data-stage", `s${i}`);
    await expect(
      inspector.getByRole("heading", { name: titles[i - 1], exact: true }),
    ).toBeVisible();
    await expect(
      page.locator('.workflow-edge[data-connected="true"]'),
    ).not.toHaveCount(0);
  }
  await page.getByTestId("node-s4").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("node-s5")).toBeFocused();
  const plane = page.getByTestId("workflow-plane"),
    before = await plane.getAttribute("style");
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(plane).not.toHaveAttribute("style", before!);
  await page.getByRole("button", { name: "Fit to view", exact: true }).click();
  const box = await page.locator(".workflow-viewport").boundingBox();
  const fitted = await plane.getAttribute("style");
  await page.mouse.move(box!.x + 20, box!.y + 20);
  await page.mouse.down();
  await page.mouse.move(box!.x + 70, box!.y + 45);
  await page.mouse.up();
  await expect(plane).not.toHaveAttribute("style", fitted!);
  await page.getByRole("button", { name: "Fit to view", exact: true }).click();
  await page
    .getByTestId("flow-inspector")
    .getByRole("link", { name: "Open stage detail" })
    .click();
  await expect(page).toHaveURL(`${path}/stages/s5`);
  await page
    .getByRole("link", { name: "Back to workspace", exact: true })
    .click();
  await expect(page).toHaveURL(`${path}?node=s5`);
  await expect(page.getByTestId("node-s5")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByTestId("node-s5")).toBeFocused();
});
async function saveApprove(page: Page) {
  for (const checkbox of await page
    .locator('.character-approval input[type="checkbox"]')
    .all())
    await checkbox.check();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Draft saved" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Submit for review", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Decision recorded" }),
  ).toBeVisible();
}
test("V2 S1–S5 approval and production batch use actual demo state and preserve frozen images", async ({
  page,
}) => {
  test.setTimeout(150_000);
  const path = await create(page);
  await page.goto(`${path}/stages/s1`);
  await page
    .getByRole("textbox", { name: "Raw idea", exact: true })
    .fill("A silver-haired ranger");
  await page
    .getByLabel("Design directions (one per line, up to 3)")
    .fill("Calm fantasy ranger");
  await saveApprove(page);
  await page.getByRole("link", { name: "Next stage", exact: true }).click();
  await page
    .getByRole("button", { name: "Add attribute", exact: true })
    .click();
  await page.getByLabel("Attribute label", { exact: true }).fill("Hair");
  await page
    .getByRole("textbox", { name: "Value", exact: true })
    .fill("Silver");
  await saveApprove(page);
  await page.getByRole("link", { name: "Next stage", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Completed PNG job", exact: true })
    .selectOption({ index: 1 });
  await page
    .getByRole("button", { name: "Link completed job", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Verdict", exact: true })
    .selectOption("selected");
  await saveApprove(page);
  await expect(
    page.locator(".character-approval .character-image img").first(),
  ).toBeVisible();
  await page.getByRole("link", { name: "Next stage", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("mock-t2d-basic");
  for (const purpose of ["Full body", "Front", "Side", "Back"]) {
    await page.getByRole("button", { name: purpose, exact: true }).click();
    await page
      .getByRole("textbox", { name: "Canonical prompt", exact: true })
      .fill(`Ranger ${purpose}`);
    await page
      .getByRole("button", { name: "Add production task", exact: true })
      .click();
  }
  await saveApprove(page);
  await expect(
    page.getByText("Expected model loads: 1", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Next stage", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Submit production batch", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Submit production batch", exact: true })
    .click();
  await expect(
    page
      .locator(".character-working")
      .getByText("Progress: Unknown", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".character-working progress[value]")).toHaveCount(
    0,
  );
  const buttons = page.getByRole("button", { name: /^Production: task_/ });
  await expect(buttons).toHaveCount(4, { timeout: 25_000 });
  for (const button of await buttons.all()) await button.click();
  for (const checkbox of await page
    .locator('.character-gallery input[type="checkbox"]')
    .all())
    await checkbox.check();
  await saveApprove(page);
  await expect(
    page.locator(".character-approval .character-image"),
  ).toHaveCount(4);
  await mkdir("test-results/v2/acceptance", { recursive: true });
  await page.screenshot({
    path: "test-results/v2/acceptance/s5-approved.png",
    fullPage: true,
  });
  const downloadEvent = page.waitForEvent("download");
  await page
    .locator(".character-approval .character-image")
    .first()
    .getByRole("link", { name: "Download", exact: true })
    .click();
  const download = await downloadEvent;
  await download.saveAs("test-results/v2/acceptance/approved-demo.png");
  expect([
    ...(
      await readFile("test-results/v2/acceptance/approved-demo.png")
    ).subarray(0, 8),
  ]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
  await page
    .getByRole("button", { name: "Set as character cover", exact: true })
    .first()
    .click();
  await page.getByRole("link", { name: "Next stage", exact: true }).click();
  await expect(page.locator(".character-planned")).toBeVisible();
  await expect(page.locator(".character-inputs .character-image")).toHaveCount(
    4,
  );
  await expect(
    page.getByRole("button", { name: "Save draft", exact: true }),
  ).toBeDisabled();
  await page.goto("/characters");
  await expect(page.locator(".character-cover img")).toBeVisible();
});
test("V2 stale-tab conflict keeps edits; unsaved navigation requires a decision", async ({
  page,
  context,
}) => {
  const path = await create(page);
  await page.goto(`${path}/stages/s1`);
  const other = await context.newPage();
  await other.goto(new URL(`${path}/stages/s1`, page.url()).href);
  await expect(
    other.getByRole("textbox", { name: "Raw idea", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Raw idea", exact: true })
    .fill("Saved in first tab");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Draft saved" }),
  ).toBeVisible();
  await other
    .getByRole("textbox", { name: "Raw idea", exact: true })
    .fill("Unsaved second tab");
  await other.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(
    other.getByText("STAGE_DRAFT_CONFLICT", { exact: true }),
  ).toBeVisible();
  await expect(
    other.getByRole("textbox", { name: "Raw idea", exact: true }),
  ).toHaveValue("Unsaved second tab");
  other.once("dialog", (d) => d.dismiss());
  await other
    .getByRole("link", { name: "Back to workspace", exact: true })
    .click();
  await expect(other).toHaveURL(`${path}/stages/s1`);
  other.once("dialog", (d) => d.accept());
  await other
    .getByRole("button", { name: "Reload latest data", exact: true })
    .click();
  await expect(
    other.getByRole("textbox", { name: "Raw idea", exact: true }),
  ).toHaveValue("Saved in first tab");
  await other.close();
});
for (const theme of [
  { id: "latte", mode: "light", family: "coffee" },
  { id: "mint", mode: "light", family: "green" },
  { id: "caffe", mode: "dark", family: "coffee" },
  { id: "matcha", mode: "dark", family: "green" },
])
  for (const locale of ["en", "vi"]) {
    test(`V2 visual/accessibility ${theme.id} ${locale}, all templates and stages at 1024/1440`, async ({
      page,
    }) => {
      test.setTimeout(240_000);
      const path = await create(page);
      await page
        .getByRole("combobox", { name: "Language", exact: true })
        .selectOption(locale);
      await page.evaluate(
        (theme) =>
          localStorage.setItem(
            "aas.theme",
            JSON.stringify({ mode: theme.mode, family: theme.family }),
          ),
        theme,
      );
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute(
        "data-theme",
        theme.id,
      );
      const routes = [
        "/characters",
        `${path}?node=s5`,
        ...[1, 2, 3, 4, 5, 6, 7].map((n) => `${path}/stages/s${n}`),
      ];
      await mkdir(`test-results/v2/${theme.id}/${locale}`, { recursive: true });
      for (const width of [1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const [index, route] of routes.entries()) {
          await page.goto(route);
          await expect(page.locator("main h1")).toBeVisible();
          await expect(page.locator('.empty[role="status"]')).toHaveCount(0);
          await expect(page.locator("html")).toHaveAttribute("lang", locale);
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth - innerWidth,
            ),
          ).toBeLessThanOrEqual(1);
          const overflow = await page
            .locator(
              ".characters-feature .panel,.character-identity,.character-card,.character-stage-bar",
            )
            .evaluateAll((elements) =>
              elements
                .filter((e) => e.scrollWidth > e.clientWidth + 2)
                .map((e) => e.className),
            );
          expect(overflow).toEqual([]);
          expect((await new AxeBuilder({ page }).analyze()).violations).toEqual(
            [],
          );
          await page.screenshot({
            path: `test-results/v2/${theme.id}/${locale}/${index === 0 ? "library" : index === 1 ? "workspace" : `stage-s${index - 1}`}-${width}.png`,
            fullPage: true,
          });
        }
      }
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      await expect(page.locator("html")).toHaveAttribute(
        "data-theme",
        theme.id,
      );
    });
  }
