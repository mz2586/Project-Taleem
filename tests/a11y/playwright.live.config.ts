import { defineConfig, devices } from "@playwright/test";
import { join } from "node:path";

const OUT = process.env.LIVE_OUT ?? join(process.cwd(), "live-demo-results");

// The live demo check: the deployed frontend, signed in with the synthetic demo accounts.
export default defineConfig({
  testDir: ".",
  testMatch: /live\.demo\.spec\.ts$/,
  workers: 1,
  retries: 0,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  outputDir: join(OUT, "test-results"),
  reporter: [["list"], ["html", { outputFolder: join(OUT, "html-report"), open: "never" }]],
  use: {
    baseURL: process.env.LIVE_WEB_URL ?? "https://taleem-web-phi.vercel.app",
    trace: "on",
    screenshot: "on",
    ...devices["Pixel 5"],
  },
  projects: [{ name: "chromium" }],
});
