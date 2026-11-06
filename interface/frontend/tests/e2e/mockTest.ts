import { test as base } from "@playwright/test";
export { expect, type Page } from "@playwright/test";

// Mock browser tests must never reach a backend, even if a dev server is replaced.
// HTTP integration tests deliberately use the original Playwright fixture instead.
export const test = base.extend({
  context: async ({ context }, runFixture) => {
    await context.route("**/api/v1/**", (route) =>
      route.abort("blockedbyclient"),
    );
    await runFixture(context);
  },
});
