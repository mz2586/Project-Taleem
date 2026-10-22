import { defineConfig, devices } from "@playwright/test";

// The servers are started by scripts/a11y/run_a11y.sh (`make a11y`), not by Playwright: the web app
// must be built against a real API, and that API needs PostgreSQL and migrations first.
export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts$/,
  // One worker: the suite signs in once (beforeAll) and every scan reuses those synthetic accounts.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.A11Y_WEB_URL ?? "http://127.0.0.1:3100",
    trace: "off",
    // A small phone viewport: the product is mobile-first (reference device: low-end Android).
    ...devices["Pixel 5"],
  },
  projects: [{ name: "chromium" }],
});
