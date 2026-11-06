import { expect, test } from "./mockTest";
import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
const choices = [
  { theme: "latte", mode: "light", family: "coffee" },
  { theme: "mint", mode: "light", family: "green" },
  { theme: "caffe", mode: "dark", family: "coffee" },
  { theme: "matcha", mode: "dark", family: "green" },
] as const;
const routes = [
  ["/generate/image-to-3d", "generate-studio"],
  ["/generate/text-to-2d", "text-to-2d"],
  ["/generate/text-to-3d", "text-to-3d"],
  ["/library", "asset-library"],
  ["/jobs", "jobs-logs"],
  ["/jobs/:first", "job-detail"],
  ["/resources?scenario=gpu_split", "kaggle-resources"],
] as const;
for (const choice of choices) {
  for (const locale of ["vi", "en"] as const) {
    test(`${choice.theme} / ${locale}: every route, accessible colors, persistence and layout`, async ({
      page,
    }) => {
      test.setTimeout(180_000);
      await page.addInitScript(
        ({ mode, family, locale }) => {
          if (!localStorage.getItem("aas.theme"))
            localStorage.setItem("aas.theme", JSON.stringify({ mode, family }));
          if (!localStorage.getItem("aas.locale"))
            localStorage.setItem("aas.locale", locale);
        },
        { ...choice, locale },
      );
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await mkdir(`test-results/themes/${choice.theme}/${locale}`, {
        recursive: true,
      });
      for (const width of locale === "vi" ? [1024, 1440] : [1440]) {
        await page.setViewportSize({ width, height: 1000 });
        for (const [path, name] of routes) {
          await page.goto(path === "/jobs/:first" ? "/jobs" : path);
          if (name === "job-detail") {
            await page.locator(".job-row").first().click();
            await expect(
              page.locator(".job-detail-stack .terminal"),
            ).toBeVisible();
          }
          await expect(page.locator("html")).toHaveAttribute(
            "data-theme",
            choice.theme,
          );
          await expect(page.locator("html")).toHaveAttribute("lang", locale);
          await expect(page.locator("main h1")).toBeVisible();
          await expect(page.locator(".empty[role=status]")).toHaveCount(0);
          if (name === "generate-studio")
            await expect(page.locator(".viewer-status")).toContainText(
              locale === "vi" ? "Đã tải GLB" : "GLB loaded",
            );
          if (name === "asset-library")
            await expect(
              page.locator(".asset-thumb img").first(),
            ).toBeVisible();
          if (name === "kaggle-resources")
            await expect(
              page.locator('[role=meter][aria-valuenow="23"]'),
            ).toBeVisible();
          await page.evaluate(() => document.fonts.ready);
          const overflow = await page.evaluate(() => {
            const elements = [
              ...document.querySelectorAll<HTMLElement>(
                ".panel, .panel *, .asset-card, .asset-card *, header, header *, .summary-strip, .summary-strip *, .profile-banner, .profile-banner *",
              ),
            ];
            return elements
              .filter((element) => {
                const style = getComputedStyle(element);
                return (
                  !element.classList.contains("sr-only") &&
                  element.clientWidth > 0 &&
                  style.display !== "inline" &&
                  !["INPUT", "TEXTAREA", "CANVAS", "SELECT", "SVG"].includes(
                    element.tagName,
                  ) &&
                  element.scrollWidth > element.clientWidth + 1
                );
              })
              .map((element) => ({
                tag: element.tagName,
                class: element.className,
                text: element.textContent?.slice(0, 80),
                width: element.clientWidth,
                scroll: element.scrollWidth,
              }));
          });
          expect(overflow).toEqual([]);
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          ).toBe(true);
          expect(
            await page.locator("main .primary").count(),
          ).toBeLessThanOrEqual(1);
          const results = await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
            .analyze();
          expect(
            results.violations.map((violation) => ({
              id: violation.id,
              nodes: violation.nodes.map((node) => node.target),
            })),
          ).toEqual([]);
          await page.screenshot({
            path: `test-results/themes/${choice.theme}/${locale}/${name}-${width}.png`,
            fullPage: true,
          });
        }
      }
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute(
        "data-theme",
        choice.theme,
      );
      await expect(page.locator("html")).toHaveAttribute("lang", locale);
      if (locale === "vi") {
        const loaded = await page.evaluate(async () => {
          const check = async (font: string, family: string) =>
            (await document.fonts.load(font, "Tiếng Việt ếộữ")).some(
              (face) =>
                face.family.includes(family) &&
                face.status === "loaded" &&
                face.unicodeRange.toLowerCase().includes("1ea0"),
            );
          return [
            await check('400 14px "Be Vietnam Pro"', "Be Vietnam Pro"),
            await check('600 16px "Plus Jakarta Sans"', "Plus Jakarta Sans"),
          ];
        });
        expect(loaded).toEqual([true, true]);
      }
      expect(errors).toEqual([]);
    });
  }
  test(`${choice.theme}: preference bootstrap precedes the React module`, async ({
    page,
  }) => {
    await page.addInitScript(({ mode, family }) => {
      localStorage.setItem("aas.theme", JSON.stringify({ mode, family }));
      localStorage.setItem("aas.locale", "vi");
    }, choice);
    let release: () => void = () => {};
    const blocked = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/src/main.tsx", async (route) => {
      await blocked;
      await route.continue();
    });
    await page.goto("/generate/text-to-2d", { waitUntil: "commit" });
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      choice.theme,
    );
    await expect(page.locator("html")).toHaveAttribute("lang", "vi");
    await expect(page.locator("#root")).toBeEmpty();
    release();
    await expect(
      page.getByRole("heading", { name: "Xưởng tạo", exact: true }),
    ).toBeVisible();
  });
}
test("theme and language switching preserves the loaded GLB and the English request values", async ({
  page,
}) => {
  await page.goto("/generate/image-to-3d");
  await expect(page.locator(".viewer-status")).toContainText("GLB loaded");
  await page.locator("canvas").evaluate((canvas) => {
    canvas.dataset.retained = "yes";
  });
  const before = await page.locator("canvas").screenshot();
  await page.getByRole("button", { name: "Dark", exact: true }).click();
  await page.getByRole("button", { name: "Green", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "matcha");
  await expect(page.locator("canvas")).toHaveAttribute("data-retained", "yes");
  expect((await page.locator("canvas").screenshot()).equals(before)).toBe(
    false,
  );
  await page.getByRole("combobox", { name: "Language" }).selectOption("vi");
  await expect(page.locator("canvas")).toHaveAttribute("data-retained", "yes");
  await expect(page.locator('select[name="model"]')).toHaveValue(
    "mock-i3d-multiview",
  );
  await expect(page.locator('select[name="asset-category"]')).toHaveValue(
    "character",
  );
  await expect(page.locator('select[name="texture_resolution"]')).toHaveValue(
    "1024",
  );
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "matcha");
  await expect(page.locator("html")).toHaveAttribute("lang", "vi");
  await page.emulateMedia({ colorScheme: "light" });
  await page
    .getByRole("button", { name: "Theo hệ thống", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "mint");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "matcha");
});
test("first-visit Vietnamese detection and storage-disabled bootstrap remain usable", async ({
  browser,
}) => {
  const context = await browser.newContext({ locale: "vi-VN" });
  const page = await context.newPage();
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new Error("disabled");
    };
    Storage.prototype.setItem = () => {
      throw new Error("disabled");
    };
  });
  await page.goto("/generate/text-to-2d");
  await expect(page.locator("html")).toHaveAttribute("lang", "vi");
  await expect(
    page.getByRole("heading", { name: "Xưởng tạo", exact: true }),
  ).toBeVisible();
  await page.getByRole("combobox", { name: "Ngôn ngữ" }).selectOption("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await context.close();
});
