import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// Defaults match the normal dev setup. Overrides allow an isolated mock backend
// and frontend without colliding with the owner's running application.
const port = Number(process.env.AAS_HTTP_FRONTEND_PORT ?? 5173);
const baseURL = `http://127.0.0.1:${port}`;
const backend = process.env.AAS_HTTP_BACKEND_URL ?? "http://127.0.0.1:8000/api/v1";
export default defineConfig({
  ...base,
  testMatch: "**/http.spec.ts",
  testIgnore: [],
  outputDir: "test-results/http",
  timeout: 90_000,
  use: { ...base.use, baseURL },
  webServer: {
    command: `npm run dev -- --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      VITE_API_MODE: "http",
      VITE_API_BASE_URL: backend,
    },
  },
});
