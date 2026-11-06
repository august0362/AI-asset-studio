import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
const png = resolve("tests/fixtures/artifacts/mock.png");
test("upload decoding rejects corrupt content and uses bytes instead of filename or MIME header", async ({
  page,
}) => {
  await page.goto("/generate/image-to-3d");
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "not-an-image.png",
      mimeType: "image/png",
      buffer: Buffer.from("plain text"),
    });
  await expect(page.getByText("UPLOAD_UNSUPPORTED_TYPE · file")).toBeVisible();
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "corrupt.png",
      mimeType: "image/png",
      buffer: Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    });
  await expect(page.getByText("UPLOAD_CORRUPT · file")).toBeVisible();
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "valid-but-named.jpg",
      mimeType: "image/jpeg",
      buffer: await readFile(png),
    });
  await expect(
    page.getByText("valid-but-named.jpg", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove valid-but-named.jpg" }),
  ).toBeVisible();
  await expect(page.getByText(/MODEL_UNSUPPORTED_FILE_FORMAT/)).toHaveCount(0);
});
test("keyboard skip link and reduced motion are available", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/generate/text-to-2d");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to workspace" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
  await expect(
    page.getByRole("button", { name: "Generate 2D image" }),
  ).toHaveCSS("transition-property", "none");
});
test("GLB loads, orbit/zoom/pan/presets/reset alter the canvas, and downloads valid bytes", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/generate/image-to-3d");
  await expect(page.getByText("GLB loaded · textured fixture")).toBeVisible();
  const canvas = page.locator("canvas");
  const before = await canvas.screenshot();
  await canvas.focus();
  await page.keyboard.press("ArrowLeft");
  expect((await canvas.screenshot()).equals(before)).toBe(false);
  const orbit = await canvas.screenshot();
  await page.keyboard.press("-");
  expect((await canvas.screenshot()).equals(orbit)).toBe(false);
  const zoom = await canvas.screenshot();
  await page.keyboard.press("Shift+ArrowRight");
  expect((await canvas.screenshot()).equals(zoom)).toBe(false);
  await page.getByRole("button", { name: "front", exact: true }).click();
  const front = await canvas.screenshot();
  await page.getByRole("button", { name: "Reset view" }).click();
  expect((await canvas.screenshot()).equals(front)).toBe(false);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download GLB", exact: true }).click();
  const result = await download;
  expect(result.suggestedFilename()).toMatch(
    /^job_\d{8}T\d{6}Z_[\da-f]{6}_art_01\.glb$/,
  );
  const bytes = await readFile((await result.path())!);
  expect(bytes.subarray(0, 4).toString()).toBe("glTF");
  expect(bytes.readUInt32LE(4)).toBe(2);
  expect(bytes.readUInt32LE(8)).toBe(bytes.length);
  expect(errors).toEqual([]);
});
test("real multi-image uploads survive switching and produce a completed mock GLB job", async ({
  page,
}) => {
  await page.goto("/generate/image-to-3d");
  await page.locator("input[type=file]").setInputFiles([
    { name: "front.png", mimeType: "image/png", buffer: await readFile(png) },
    { name: "side.png", mimeType: "image/png", buffer: await readFile(png) },
    { name: "back.png", mimeType: "image/png", buffer: await readFile(png) },
  ]);
  await expect(page.getByText("back.png", { exact: true })).toBeVisible();
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("mock-i3d-single");
  await expect(
    page.getByText("MODEL_INPUT_COUNT_EXCEEDED · inputs"),
  ).toBeVisible();
  expect(await page.getByRole("button", { name: /Remove .*png/ }).count()).toBe(
    3,
  );
  await page
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption("mock-i3d-multiview");
  await page
    .getByRole("button", { name: "Generate 3D asset", exact: true })
    .click();
  await expect(page.getByText("completed", { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("GLB loaded · textured fixture")).toBeVisible();
  await page.getByRole("link", { name: "View job & logs" }).click();
  await expect(page.getByRole("log", { name: "Execution logs" })).toContainText(
    "Fixture artifacts validated",
  );
  await expect(page.getByRole("log", { name: "Execution logs" })).toContainText(
    "uploading",
  );
  await expect(page.getByRole("button", { name: "Retry job" })).toHaveCount(0);
});
test("Text → 2D generates a PNG; library search, filters and download work", async ({
  page,
}) => {
  await page.goto("/generate/text-to-2d");
  await page
    .getByRole("textbox", { name: /Prompt/ })
    .fill("Ornate frost greatsword concept");
  await page
    .getByRole("combobox", { name: "Asset category" })
    .selectOption("weapon");
  await page
    .getByRole("button", { name: "Generate 2D image", exact: true })
    .click();
  await expect(page.getByText("completed", { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".image-preview img")).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download PNG", exact: true }).click();
  const download = await pending;
  const bytes = await readFile((await download.path())!);
  expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Asset library" })
    .click();
  await page
    .getByRole("combobox", { name: "Format", exact: true })
    .selectOption("png");
  await page
    .getByRole("combobox", { name: "Category", exact: true })
    .selectOption("weapon");
  await expect(
    page.getByRole("heading", { name: "Weapon concept study" }),
  ).toBeVisible();
  await page
    .getByRole("searchbox", { name: "Search assets" })
    .fill("no-matching-asset");
  await expect(
    page.getByRole("heading", { name: "No assets match your filters" }),
  ).toBeVisible();
});
test("retry is restricted to a failed retryable job and keeps the old record", async ({
  page,
}) => {
  await page.goto("/jobs?status=failed");
  await page.locator(".job-row").first().click();
  await expect(page.getByRole("button", { name: "Retry job" })).toBeVisible();
  const old = page.url();
  await page.getByRole("button", { name: "Retry job" }).click();
  await expect(page).not.toHaveURL(old);
  await expect(page.getByText("Original job", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry job" })).toHaveCount(0);
});
for (const width of [1440, 1024, 390])
  test(`responsive screens and WCAG automated checks at ${width}px`, async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 1000 });
    await mkdir("test-results/screenshots", { recursive: true });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const [path, name] of [
      ["/generate/image-to-3d", "generate-studio"],
      ["/library", "asset-library"],
      ["/jobs", "jobs-logs"],
      ["/resources?scenario=gpu_split", "kaggle-resources"],
    ]) {
      await page.goto(path);
      await expect(page.locator("main h1")).toBeVisible();
      await expect(page.getByText("Loading workspace…")).toHaveCount(0);
      if (name === "generate-studio")
        await expect(
          page.getByText("GLB loaded · textured fixture"),
        ).toBeVisible();
      if (name === "asset-library")
        await expect(page.locator(".asset-thumb img").first()).toBeVisible();
      if (name === "kaggle-resources")
        await expect(
          page.getByRole("meter", { name: "GPU1 utilization" }),
        ).toHaveAttribute("aria-valuenow", "23");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      ).toBe(true);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect(
        results.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => n.target),
        })),
      ).toEqual([]);
      await page.screenshot({
        path: `test-results/screenshots/${name}-${width}.png`,
        fullPage: true,
      });
    }
    expect(errors).toEqual([]);
  });
test("all resource scenarios and planned route remain honest", async ({
  page,
}) => {
  await page.goto("/resources");
  for (const scenario of [
    "fresh",
    "no_session",
    "quota_missing",
    "telemetry_stale",
    "telemetry_unavailable",
    "gpu_split",
    "quota_low",
  ]) {
    await page
      .getByRole("combobox", { name: "Development scenario" })
      .selectOption(scenario);
    await expect(page).toHaveURL(new RegExp(`scenario=${scenario}`));
    if (scenario === "no_session")
      await expect(page.getByText("No active session")).toBeVisible();
    if (scenario === "telemetry_stale")
      await expect(
        page.getByText("stale", { exact: true }).first(),
      ).toBeVisible();
    if (scenario === "telemetry_unavailable")
      await expect(
        page.getByText("COMPUTE_TELEMETRY_UNAVAILABLE · host"),
      ).toBeVisible();
    if (scenario === "quota_missing")
      await expect(
        page.getByText("Quota was not reported in this mock scenario."),
      ).toBeVisible();
    if (scenario === "quota_low")
      await expect(
        page.getByText("COMPUTE_QUOTA_INSUFFICIENT · compute.accelerator_id"),
      ).toBeVisible();
  }
  await page.goto("/generate/text-to-3d");
  await expect(
    page.getByText("PIPELINE_NOT_AVAILABLE · pipeline_type").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Generate 3D asset" }),
  ).toBeDisabled();
});
