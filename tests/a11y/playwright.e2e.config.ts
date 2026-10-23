import { defineConfig, devices } from "@playwright/test";
import { join } from "node:path";

// Browser-level end-to-end journey through the REAL UI (`make e2e-web`). Servers are started by
// scripts/e2e-web/run_e2e_web.sh: uvicorn + PostgreSQL behind a production `next build`.
const OUT = process.env.E2E_WEB_OUT ?? join(process.cwd(), "e2e-web-results");

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.journey\.spec\.ts$/,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 300_000,
  expect: { timeout: 15_000 },
  outputDir: join(OUT, "test-results"),
  reporter: [["list"], ["html", { outputFolder: join(OUT, "html-report"), open: "never" }]],
  use: {
    baseURL: process.env.E2E_WEB_URL ?? "http://127.0.0.1:3200",
    // A full trace and a screenshot for every test, kept whether it passes or fails: this run is
    // evidence, not only a regression gate.
    trace: "on",
    screenshot: "on",
    ...devices["Pixel 5"],
  },
  projects: [{ name: "chromium" }],
});
