// Live check of the DEPLOYED application with the designated synthetic demo accounts
// (docs/03-security-privacy/DEMO_COHORT_CONTRACT.md). Real browser, real frontend, real API: no
// fixtures, no mocks. Run by .github/workflows/live-demo-check.yml (manual) with credentials from
// repository secrets; screenshots and a findings log are uploaded as the run's artifact.
//
//   LIVE_WEB_URL, LIVE_API_URL, DEMO_GUARDIAN_EMAIL, DEMO_GUARDIAN_PASSPHRASE,
//   DEMO_FAMILY_CODE, DEMO_LEARNER_NAME, DEMO_LEARNER_PIN, DEMO_STUDENT_REF
import { devices, expect, test, type Browser, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { en } from "../../apps/web/lib/i18n/messages/en";

const OUT = process.env.LIVE_OUT ?? join(process.cwd(), "live-demo-results");
const API = process.env.LIVE_API_URL ?? "https://taleem-api.vercel.app";
const need = (k: string): string => {
  const v = process.env[k];
  if (!v) throw new Error(`${k} is not set`);
  return v;
};
const findings: string[] = [];
const note = (s: string): void => {
  findings.push(s);
};
let shotNo = 0;

function t(key: string): string {
  let node: unknown = en;
  for (const part of key.split(".")) node = (node as Record<string, unknown>)?.[part];
  if (typeof node !== "string") throw new Error(`missing message ${key}`);
  return node;
}

async function shot(page: Page, name: string): Promise<void> {
  mkdirSync(OUT, { recursive: true });
  shotNo += 1;
  await page.screenshot({ path: join(OUT, `${String(shotNo).padStart(2, "0")}-${name}.png`), fullPage: true });
}

async function device(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ ...devices["Pixel 5"] });
  await context.addInitScript(() => window.localStorage.setItem("taleem.uiLocale.v1", "en"));
  const page = await context.newPage();
  page.on("response", (res) => {
    if (res.status() >= 400 && res.url().startsWith(API)) {
      note(`[api] ${res.request().method()} ${new URL(res.url()).pathname} -> ${res.status()}`);
    }
  });
  return page;
}

async function visit(page: Page, path: string, name: string): Promise<string> {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await shot(page, name);
  const text = (await page.locator("main").first().innerText().catch(() => "")).replace(/\s+/g, " ");
  note(`[page] ${path}: ${text.slice(0, 400)}`);
  return text;
}

test.afterAll(() => {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, "findings.md"), findings.map((f) => `- ${f}`).join("\n") + "\n");
});

test("guardian signs in and sees only the demo learner", async ({ browser }) => {
  const page = await device(browser);
  await page.goto("/guardian/signin");
  await page.locator("#email").fill(need("DEMO_GUARDIAN_EMAIL"));
  await page.locator("#passphrase").fill(need("DEMO_GUARDIAN_PASSPHRASE"));
  await page.getByRole("button", { name: t("auth.guardianSignIn.submit") }).click();
  await page.waitForURL("**/guardian", { timeout: 30_000 });
  const home = await visit(page, "/guardian", "guardian-home");
  expect(home).toContain(need("DEMO_LEARNER_NAME"));
  const ref = encodeURIComponent(need("DEMO_STUDENT_REF"));
  await visit(page, `/guardian/children/${ref}`, "guardian-child");
  await visit(page, `/guardian/children/${ref}/report-cards`, "guardian-report-cards");
  await visit(page, "/guardian/family", "guardian-family");
  // Isolation: another learner's page must not render that learner's data.
  const other = await visit(page, "/guardian/children/stu_00000000-0000-0000-0000-000000000000", "guardian-other-child");
  expect(other).not.toContain(need("DEMO_LEARNER_NAME"));
});

test("learner signs in with family code + PIN and explores", async ({ browser }) => {
  const page = await device(browser);
  await page.goto("/signin");
  await page.locator("#family-code").fill(need("DEMO_FAMILY_CODE"));
  await page.getByRole("button", { name: t("auth.learner.next"), exact: true }).click();
  await page.getByRole("button", { name: need("DEMO_LEARNER_NAME") }).click();
  await page.locator("#pin").fill(need("DEMO_LEARNER_PIN"));
  await page.getByRole("button", { name: t("auth.learner.start") }).click();
  await page.waitForURL("**/student/today", { timeout: 30_000 });
  for (const [path, name] of [
    ["/student/today", "learner-today"],
    ["/student/subjects", "learner-subjects"],
    ["/student/progress", "learner-progress"],
    ["/student/homework", "learner-homework"],
    ["/student/report-cards", "learner-report-cards"],
    ["/student/offline", "learner-offline"],
  ] as const) {
    await visit(page, path, name);
  }
  // Start a lesson from Today, step through it and answer one question.
  await page.goto("/student/today");
  // The control's accessible name includes its "▶" icon, so match the label text, link or button.
  const label = new RegExp(`(^|\\s)${t("student.today.start")}$`);
  await page.getByRole("link", { name: label }).or(page.getByRole("button", { name: label })).first().click();
  await page.waitForURL("**/student/session**", { timeout: 30_000 });
  await page.waitForLoadState("networkidle");
  await shot(page, "learner-lesson-start");
  const group = page.getByRole("group", { name: t("student.session.answers") });
  for (let i = 0; i < 12 && !(await group.isVisible()); i++) {
    const ready = page.getByRole("button", { name: t("student.session.ready") });
    const next = page.getByRole("button", { name: t("common.next"), exact: true });
    if (await ready.isVisible()) await ready.click();
    else if (await next.isVisible()) await next.click();
    else break;
    await page.waitForTimeout(500);
  }
  await shot(page, "learner-lesson-question");
  expect(await group.isVisible()).toBe(true);
  await group.getByRole("button").first().click();
  await page.waitForLoadState("networkidle");
  await shot(page, "learner-lesson-answered");
  note(`[lesson] answered one question at ${page.url()}`);
  note(`[lesson] after answering: ${(await page.locator("main").first().innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
});
