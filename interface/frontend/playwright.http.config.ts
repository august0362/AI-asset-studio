import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

// The HTTP suite uses port 5173 because it is an approved backend CORS origin.
// It never starts or edits the independently owned backend.
export default defineConfig({
  ...base,
  testMatch: "**/http.spec.ts",
  testIgnore: [],
  outputDir: "test-results/http",
  timeout: 90_000,
  use: { ...base.use, baseURL: "http://127.0.0.1:5173" },
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      VITE_API_MODE: "http",
      VITE_API_BASE_URL: "http://127.0.0.1:8000/api/v1",
    },
  },
});
