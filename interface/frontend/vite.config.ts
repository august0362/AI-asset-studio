import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

// Serve the same binary fixtures in dev, tests and production; no duplicate source assets.
const fixture = (name: string) =>
  fileURLToPath(new URL(`./tests/fixtures/artifacts/${name}`, import.meta.url));
export default defineConfig({
  plugins: [
    react(),
    {
      name: "mock-artifacts",
      configureServer(server) {
        server.middlewares.use("/mock-artifacts", async (req, res, next) => {
          const name = req.url?.split("?")[0]?.replace(/^\//, "");
          if (name !== "mock.png" && name !== "mock.glb") return next();
          res.setHeader(
            "Content-Type",
            name.endsWith("png") ? "image/png" : "model/gltf-binary",
          );
          res.end(await readFile(fixture(name)));
        });
      },
      async generateBundle() {
        for (const name of ["mock.png", "mock.glb"]) {
          this.emitFile({
            type: "asset",
            fileName: `mock-artifacts/${name}`,
            source: await readFile(fixture(name)),
          });
        }
      },
    },
  ],
  test: {
    env: { VITE_API_MODE: "mock" },
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three"],
          viewer: [
            "three/examples/jsm/loaders/GLTFLoader.js",
            "three/examples/jsm/controls/OrbitControls.js",
          ],
        },
      },
    },
  },
});
