// Browser-level end-to-end journey through the REAL UI (`make e2e-web`).
//
// Everything a person does here goes through the rendered app — forms, buttons, the service worker —
// against a real uvicorn + PostgreSQL. The only things done outside the UI are reading evidence:
// the child's attempt count and the pinned signing key are checked against the API directly.
//
//   1. Guardian: /join -> register -> /guardian/family enrol a child -> consent -> family code
//   2. Child: /signin family code -> tap name -> PIN -> Today -> lesson (hint, answers) -> progress
//   3. Offline: save the package -> network off -> player loads from the service worker -> answer ->
//      badge "saved on this phone" -> network on -> badge reaches server-confirmed -> API evidence
//   4. Guardian sees progress; withdraws consent (confirmation dialog) -> child's next action
//
// Steps 1-2 run in Urdu (RTL) and English; steps 3-4 run in English. UI strings come from the app's
// own catalogs, so a copy change does not break the test and both locales use the same script.
// The device language is set the way the app stores it (localStorage `taleem.uiLocale.v1`).
//
// Product defects are recorded with expect.soft (the run continues) and written, with route, step
// and screenshot path, to $E2E_WEB_OUT/e2e-web-findings.md. Synthetic data only.
import {
  devices,
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
} from "@playwright/test";
import { randomBytes, randomInt } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { en } from "../../apps/web/lib/i18n/messages/en";
import { ur } from "../../apps/web/lib/i18n/messages/ur";

const API = process.env.E2E_WEB_API_URL ?? "http://127.0.0.1:8767";
const OUT = process.env.E2E_WEB_OUT ?? join(process.cwd(), "e2e-web-results");
const SHOTS = join(OUT, "screenshots");
const FIXTURE = "E2E-SYNTHETIC-FIXTURE-fractions";
const PINNED = process.env.E2E_WEB_PINNED_KEYS ?? "";

type Locale = "ur" | "en";
const CATALOGS: Record<Locale, unknown> = { ur, en };

interface Finding {
  step: string;
  route: string;
  problem: string;
  screenshot: string;
}
const findings: Finding[] = [];
const log: string[] = [];

/** The app's own string for `key` in `locale`, with {params} filled in. */
function t(locale: Locale, key: string, params: Record<string, string | number> = {}): string {
  let node: unknown = CATALOGS[locale];
  for (const part of key.split(".")) node = (node as Record<string, unknown>)?.[part];
  if (typeof node !== "string") throw new Error(`missing message ${key} (${locale})`);
  return node.replace(/\{(\w+)\}/g, (_, name: string) => String(params[name] ?? `{${name}}`));
}

/** The static text of a message before its first {placeholder} (counts are locale-formatted). */
function prefix(locale: Locale, key: string): string {
  const full = (() => {
    let node: unknown = CATALOGS[locale];
    for (const part of key.split(".")) node = (node as Record<string, unknown>)?.[part];
    return String(node);
  })();
  return full.split("{")[0].trim();
}

let shotCount = 0;
async function shot(page: Page, name: string): Promise<string> {
  mkdirSync(SHOTS, { recursive: true });
  shotCount += 1;
  // Worker-prefixed: numbering restarts when a failed test restarts the worker.
  const file = join(SHOTS, `w${test.info().workerIndex}-${String(shotCount).padStart(2, "0")}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

/** Record a product defect without stopping the run. */
async function defect(page: Page, step: string, problem: string): Promise<void> {
  const file = await shot(page, `DEFECT-${step.replace(/[^a-z0-9]+/gi, "_")}`);
  findings.push({ step, route: new URL(page.url()).pathname + new URL(page.url()).search, problem, screenshot: file });
  expect.soft(false, `${step}: ${problem} (screenshot ${file})`).toBe(true);
}

function note(line: string): void {
  log.push(line);
  console.log(`   ${line}`);
}

/**
 * Click like a person: bring the control to the middle of the screen first. Playwright's default
 * scroll leaves a control at the viewport edge, where the student app's fixed bottom navigation
 * covers it; a child scrolls a little further before tapping. (Test-infra, not a product defect.)
 */
let currentStep = "";
const reportedCovered = new Set<string>();
/** Enabled right now: a control that vanished (the lesson just ended) reads as not enabled
 * instead of Playwright waiting indefinitely for it to reappear. */
async function enabledNow(target: Locator): Promise<boolean> {
  return target.isEnabled({ timeout: 1_000 }).catch(() => false);
}

async function tap(target: Locator): Promise<void> {
  await target.evaluate((el) => el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" }));
  // Let any smooth scrolling settle before deciding the control is covered.
  await target.page().waitForTimeout(400);
  try {
    await target.click({ timeout: 5_000 });
    return;
  } catch (error) {
    if (!String(error).includes("intercepts pointer events")) throw error;
  }
  // The control cannot be tapped: something sits on top of it even after scrolling. Record the
  // defect once per control, with what covers it and whether the page can scroll, then activate it
  // from the keyboard so the rest of the journey can still be exercised.
  const page = target.page();
  const info = await target.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const cover = top ? `${top.tagName.toLowerCase()}${top.closest("nav") ? " inside <nav>" : ""}` : "nothing";
    const root = document.scrollingElement ?? document.documentElement;
    return {
      label: (el.textContent ?? "").trim().slice(0, 40),
      cover,
      box: `${Math.round(r.top)}..${Math.round(r.bottom)} of ${window.innerHeight}px viewport`,
      scroll: `page scrollHeight ${root.scrollHeight}, clientHeight ${root.clientHeight}`,
    };
  });
  const key = `${new URL(page.url()).pathname}|${info.label}`;
  if (!reportedCovered.has(key)) {
    reportedCovered.add(key);
    await defect(
      page,
      currentStep,
      `"${info.label}" cannot be tapped: covered by ${info.cover} (control at ${info.box}; ${info.scroll})`,
    );
  }
  await target.focus();
  await page.keyboard.press("Enter");
}

/** Flag visible text that is cut off by the viewport edge (WCAG 1.4.10 Reflow candidate). */
async function checkClipping(page: Page, step: string): Promise<void> {
  const clipped = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    const out: string[] = [];
    for (const el of Array.from(document.querySelectorAll("h1, h2, h3, p, a, button, label, strong"))) {
      const r = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      if (!r.width || style.visibility === "hidden" || style.position === "fixed") continue;
      // Skip links sit off-screen by design until focused.
      if (el.tagName === "A" && (el.getAttribute("href") ?? "").startsWith("#")) continue;
      if (r.right > width + 1 || r.left < -1) {
        const text = (el.textContent ?? "").trim().replace(/\s+/g, " ").slice(0, 40);
        out.push(`<${el.tagName.toLowerCase()}> "${text}" spans ${Math.round(r.left)}..${Math.round(r.right)} of ${width}px`);
      }
    }
    return out.slice(0, 5);
  });
  if (clipped.length) await defect(page, step, `text cut off at the screen edge: ${clipped.join("; ")}`);
}

async function newDevice(browser: Browser, locale: Locale): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ ...devices["Pixel 5"], serviceWorkers: "allow" });
  await context.addInitScript((loc) => window.localStorage.setItem("taleem.uiLocale.v1", loc), locale);
  const page = await context.newPage();
  // Browser-side evidence: console errors and requests the browser refused or lost (URL only —
  // never headers or bodies, which carry tokens).
  page.on("console", (msg) => {
    if (msg.type() === "error") note(`[console ${locale}] ${msg.text().slice(0, 300)}`);
  });
  page.on("response", async (res) => {
    if (res.status() < 400 || !res.url().startsWith(API)) return;
    const req = res.request();
    const path = new URL(res.url()).pathname;
    let problem = "";
    try {
      const body = (await res.json()) as { code?: string; detail?: string };
      problem = ` ${body.code ?? ""} ${String(body.detail ?? "").slice(0, 120)}`;
    } catch {
      /* no JSON body */
    }
    // The session-start body is only {student_ref}; safe to record. No other bodies are logged.
    const sent = path === "/v1/learning/sessions" ? ` body=${req.postData() ?? ""}` : "";
    note(`[api ${locale}] ${req.method()} ${path} -> ${res.status()}${problem}${sent}`);
  });
  page.on("requestfailed", (req) => {
    note(`[request failed ${locale}] ${req.method()} ${req.url().split("?")[0]} — ${req.failure()?.errorText ?? "?"}`);
  });
  return { context, page };
}

async function readSession(page: Page): Promise<{ subject: string; accessToken: string }> {
  return page.evaluate(() => JSON.parse(window.localStorage.getItem("taleem.session.v1") ?? "{}"));
}

async function apiGet<T>(path: string, token: string): Promise<{ status: number; body: T }> {
  const response = await fetch(`${API}${path}`, { headers: { authorization: `Bearer ${token}` } });
  return { status: response.status, body: (await response.json().catch(() => ({}))) as T };
}

function syntheticPin(): string {
  for (;;) {
    const pin = String(randomInt(0, 10_000)).padStart(4, "0");
    if (new Set(pin).size === 4 && !["1234", "4321", "0123"].includes(pin)) return pin;
  }
}

// Not serial: a soft failure (a recorded defect) in the Urdu run must not skip the English run.
// One worker (playwright.e2e.config.ts) keeps them in order.

test.afterAll(() => {
  mkdirSync(OUT, { recursive: true });
  // A failed test restarts the worker process, so each worker adds to what earlier ones recorded
  // (workers run one at a time) instead of overwriting it.
  const store = join(OUT, "e2e-web-findings.json");
  const prior = existsSync(store)
    ? (JSON.parse(readFileSync(store, "utf8")) as { findings: Finding[]; log: string[] })
    : { findings: [], log: [] };
  const all = { findings: [...prior.findings, ...findings], log: [...prior.log, ...log] };
  writeFileSync(store, JSON.stringify(all, null, 2));
  findings.length = 0;
  log.length = 0;
  findings.push(...all.findings);
  log.push(...all.log);
  const lines = [
    "# Browser journey findings (real UI, real API)",
    "",
    "Synthetic data only. A finding is a product defect observed through the UI; the run continues",
    "past it (expect.soft) so every defect in one run is listed. Trace and screenshots are in this",
    "directory (`test-results/`, `screenshots/`, `html-report/`).",
    "",
    "## Defects",
    "",
    "| Step | Route | Problem | Screenshot |",
    "| --- | --- | --- | --- |",
    ...(findings.length ? [] : ["| - | - | none | - |"]),
    ...findings.map((f) => `| ${f.step} | \`${f.route}\` | ${f.problem.replace(/\|/g, "/")} | \`${f.screenshot}\` |`),
    "",
    "## Log",
    "",
    ...log.map((l) => `- ${l}`),
    "",
  ];
  writeFileSync(join(OUT, "e2e-web-findings.md"), lines.join("\n"));
});

// ------------------------------------------------------------------------------------- step 1

interface Family {
  guardian: Page;
  guardianContext: BrowserContext;
  familyCode: string;
  learnerName: string;
  pin: string;
  studentRef: string;
}

async function guardianJoinsAndEnrols(browser: Browser, locale: Locale, learnerName: string): Promise<Family> {
  const { context, page } = await newDevice(browser, locale);
  const step = `1 guardian (${locale})`;
  currentStep = step;
  await page.goto("/join");
  await expect(page.getByRole("heading", { name: t(locale, "auth.join.title") })).toBeVisible();
  await page.locator("#display-name").fill(locale === "ur" ? "مصنوعی سرپرست" : "Synthetic Guardian");
  await page.locator("#email").fill(`e2e-web-${randomBytes(6).toString("hex")}@example.invalid`);
  await page.locator("#passphrase").fill(randomBytes(18).toString("base64url"));
  await shot(page, `${locale}-join-filled`);
  await tap(page.getByRole("button", { name: t(locale, "auth.join.submit") }));
  // Registration now shows the one-time recovery codes first: the guardian confirms they saved
  // them before moving on (docs/03-security-privacy/11-authentication-strategy.md §9).
  await expect(page.getByRole("heading", { name: t(locale, "guardian.recovery.title") }).first()).toBeVisible();
  await shot(page, `${locale}-join-recovery-codes`);
  await page.getByLabel(t(locale, "guardian.recovery.ack")).check();
  await tap(page.getByRole("button", { name: t(locale, "guardian.recovery.continue") }));
  await page.waitForURL("**/guardian/family");
  note(`${step}: registered through /join, saved recovery codes, landed on /guardian/family`);

  const codeCard = page.locator('section[aria-labelledby="family-code-title"]');
  await expect(codeCard.getByRole("heading", { name: t(locale, "guardian.family.codeTitle") })).toBeVisible();
  const familyCode = (await codeCard.locator("strong").innerText()).trim();
  if (!familyCode) await defect(page, step, "family code card is empty after registration");

  const pin = syntheticPin();
  await page.locator("#learner-name").fill(learnerName);
  await page.locator("#learner-pin").fill(pin);
  await tap(page.getByRole("button", { name: t(locale, "guardian.enrol.submit") }));
  const section = page.locator('section[id^="learner-"]').filter({
    has: page.getByRole("heading", { level: 3, name: learnerName }),
  });
  await expect(section).toBeVisible();
  const studentRef = ((await section.getAttribute("id")) ?? "").replace(/^learner-/, "");
  note(`${step}: enrolled "${learnerName}" (${studentRef})`);

  const required = section.locator('input[type="checkbox"][id$="-learning_data"]');
  if (!(await required.isChecked())) await required.check();
  await tap(page.getByRole("button", { name: t(locale, "guardian.consent.give") }));
  await expect(section.getByRole("button", { name: t(locale, "guardian.consent.stop") })).toBeEnabled();
  await expect(section).toContainText(t(locale, "guardian.access.given"));
  await shot(page, `${locale}-family-consented`);
  await checkClipping(page, `${step} /guardian/family`);
  note(`${step}: consent given through the consent form; family code shown (${familyCode.length} chars)`);
  return { guardian: page, guardianContext: context, familyCode, learnerName, pin, studentRef };
}

// ------------------------------------------------------------------------------------- step 2

async function childSignsInAndLearns(browser: Browser, locale: Locale, family: Family): Promise<Page> {
  const { page } = await newDevice(browser, locale);
  const step = `2 child (${locale})`;
  currentStep = step;
  await page.goto("/signin");
  await page.locator("#family-code").fill(family.familyCode);
  await tap(page.getByRole("button", { name: t(locale, "auth.learner.next"), exact: true }));
  await expect(page.getByRole("heading", { name: t(locale, "auth.learner.whoTitle") })).toBeVisible();
  await tap(page.getByRole("button", { name: family.learnerName }));
  await page.locator("#pin").fill(family.pin);
  await shot(page, `${locale}-child-pin`);
  await tap(page.getByRole("button", { name: t(locale, "auth.learner.start") }));
  await page.waitForURL("**/student/today");
  note(`${step}: signed in with family code -> roster tap -> PIN, landed on Today`);
  await shot(page, `${locale}-today`);
  await checkClipping(page, `${step} /student/today`);

  await tap(page.getByRole("link", { name: t(locale, "student.today.start"), exact: true }));
  await page.waitForURL("**/student/session");
  let hintUsed = false;
  let answers = 0;
  const finished = page.getByRole("heading", { name: t(locale, "student.session.endings.finishedTitle") });
  let idle = 0;
  let retried = false;
  const sessionError = page.getByText(t(locale, "student.session.error"));
  for (let i = 0; i < 80 && !(await finished.isVisible()); i += 1) {
    if (await sessionError.isVisible()) {
      await defect(
        page,
        step,
        "pressing Start shows 'Something went wrong': the session page starts the session on mount " +
          "before the learner ref has hydrated (POST /v1/learning/sessions with an empty student_ref -> 403)",
      );
      if (retried) break;
      // What a child would do: go back to Today and press Start again.
      retried = true;
      await tap(page.getByRole("link", { name: t(locale, "common.backToToday") }));
      await page.waitForURL("**/student/today");
      await tap(page.getByRole("link", { name: t(locale, "student.today.start"), exact: true }));
      await page.waitForURL("**/student/session");
      note(`${step}: retried Start from Today after the session error`);
      continue;
    }
    if (idle >= 25) {
      await defect(page, step, "lesson stalled: no next step, answer or continue control appeared for 10s");
      break;
    }
    const next = page.getByRole("button", { name: t(locale, "common.next"), exact: true });
    const ready = page.getByRole("button", { name: t(locale, "student.session.ready") });
    const group = page.getByRole("group", { name: t(locale, "student.session.answers") });
    const hint = page.getByRole("button", { name: t(locale, "student.session.hint") });
    const cont = page.getByRole("button", { name: t(locale, "common.continue"), exact: true });
    const again = page.getByRole("button", { name: t(locale, "common.tryAgain"), exact: true });
    if (await cont.isVisible()) await tap(cont);
    else if (await again.isVisible()) await tap(again);
    else if (await ready.isVisible()) await tap(ready);
    else if ((await next.isVisible()) && (await enabledNow(next))) await tap(next);
    else if (await group.isVisible()) {
      if (!hintUsed && (await hint.isVisible())) {
        await tap(hint);
        await expect(page.getByRole("list", { name: t(locale, "student.session.hints") })).toBeVisible();
        hintUsed = true;
        await shot(page, `${locale}-hint`);
        note(`${step}: used a hint`);
      }
      const options = group.getByRole("button");
      await tap(options.first());
      answers += 1;
      // The answer is graded by the server; the options stay disabled until its feedback (Continue /
      // Try again) renders. Wait for it, or the next iteration taps a disabled option.
      await expect(cont.or(again)).toBeVisible({ timeout: 10_000 });
    } else {
      idle += 1;
      await page.waitForTimeout(400);
      continue;
    }
    idle = 0;
  }
  const started = answers > 0;
  if (!started) note(`${step}: lesson never started, so hints, answers and progress were not reachable`);
  else {
    if (!(await finished.isVisible())) await defect(page, step, "lesson never reached the finished screen");
    if (!hintUsed) await defect(page, step, "no item offered a hint in the fixture lesson");
  }
  await shot(page, `${locale}-lesson-finished`);
  await checkClipping(page, `${step} lesson`);
  note(`${step}: lesson finished after ${answers} answers`);

  await page.goto("/student/progress");
  await expect(page.locator("h1, h2").first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, `${locale}-progress`);
  await checkClipping(page, `${step} /student/progress`);
  const session = await readSession(page);
  const progress = await apiGet<{ total_attempts?: number }>(
    `/v1/learning/students/${encodeURIComponent(session.subject)}/progress`,
    session.accessToken,
  );
  if (started && !progress.body.total_attempts) {
    await defect(page, step, `API shows no attempts after the lesson (${progress.status})`);
  }
  note(`${step}: API progress total_attempts=${progress.body.total_attempts}`);
  return page;
}

// ------------------------------------------------------------------------------------- step 3

async function offlineLesson(child: Page, context: BrowserContext): Promise<void> {
  const locale: Locale = "en";
  const step = "3 offline";
  currentStep = step;
  await child.goto("/student/offline");
  const controlled = async () =>
    child.evaluate(async () => {
      if (!("serviceWorker" in navigator)) return false;
      await navigator.serviceWorker.ready;
      return Boolean(navigator.serviceWorker.controller);
    });
  if (!(await controlled())) {
    await child.reload();
    if (!(await controlled())) await defect(child, step, "service worker never controls the page");
  }

  // The app verifies package signatures with WebCrypto Ed25519 (Chromium 137+). Record whether this
  // browser has it: on an older Chromium or Android WebView the save fails with "could not be
  // checked", which is a device-support limit, not a bad package.
  const ed25519 = await child.evaluate(async () => {
    try {
      await crypto.subtle.importKey("raw", new Uint8Array(32), { name: "Ed25519" }, false, ["verify"]);
      return "supported";
    } catch (error) {
      return `unsupported (${String(error).slice(0, 80)})`;
    }
  });
  note(`${step}: browser ${child.context().browser()?.version() ?? "?"}; WebCrypto Ed25519 ${ed25519}`);

  const session = await readSession(child);
  const keys = await apiGet<{ keys?: { key_id: string; public_key_hex?: string; public_key?: string }[] }>(
    "/v1/offline/signing-keys",
    session.accessToken,
  );
  note(`${step}: API signing keys ${JSON.stringify(keys.body)}; build pinned ${PINNED || "(none)"}`);
  if (!PINNED) await defect(child, step, "build has no NEXT_PUBLIC_OFFLINE_SIGNING_KEYS; pinned path not exercised");

  const before = await apiGet<{ total_attempts?: number }>(
    `/v1/learning/students/${encodeURIComponent(session.subject)}/progress`,
    session.accessToken,
  );
  await tap(child.getByRole("button", { name: t(locale, "student.offline.save") }).first());
  // Not the "On this phone" text: it is also a substring of the page heading "Lessons on this
  // phone". The Open link renders only once the package is installed and its signature verified.
  try {
    await expect(child.getByRole("link", { name: t(locale, "student.offline.open") }).first()).toBeVisible({
      timeout: 60_000,
    });
  } catch {
    const state = (await child.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 300);
    await defect(child, step, `saving the package never completed within 60s; library shows: "${state}"`);
    return;
  }
  await shot(child, "offline-saved");
  await checkClipping(child, `${step} /student/offline`);
  note(`${step}: package saved to this phone (signature verified by the app)`);

  await context.setOffline(true);
  const play = `/student/offline/play?lesson=${encodeURIComponent(FIXTURE)}`;
  try {
    await child.goto(play);
  } catch (error) {
    await defect(child, step, `offline navigation to the player failed: ${String(error).split("\n")[0]}`);
    await context.setOffline(false);
    return;
  }
  const notInstalled = child.getByRole("heading", { name: t(locale, "student.offline.player.notInstalledTitle") });
  const done = child.getByRole("heading", { name: t(locale, "student.offline.player.doneTitle") });
  let answered = 0;
  let idle = 0;
  for (let i = 0; i < 80 && !(await done.isVisible()); i += 1) {
    if (await notInstalled.isVisible()) break;
    if (idle >= 25) {
      await defect(child, step, "offline lesson stalled: no next step or answer control for 10s");
      break;
    }
    const startAgain = child.getByRole("button", { name: t(locale, "student.offline.player.startAgain") });
    const next = child.getByRole("button", { name: t(locale, "common.next"), exact: true });
    const ready = child.getByRole("button", { name: t(locale, "student.session.ready") });
    const group = child.getByRole("group", { name: t(locale, "student.session.answers") });
    if (await startAgain.isVisible()) await tap(startAgain);
    else if (await ready.isVisible()) await tap(ready);
    else if ((await next.isVisible()) && (await enabledNow(next))) await tap(next);
    else if (await group.isVisible()) {
      const option = group.getByRole("button").first();
      if ((await option.isVisible()) && (await enabledNow(option))) {
        await tap(option);
        answered += 1;
      } else await child.waitForTimeout(300);
    } else {
      idle += 1;
      await child.waitForTimeout(400);
      continue;
    }
    idle = 0;
  }
  await shot(child, "offline-player-end");
  if (await notInstalled.isVisible()) await defect(child, step, "player says the lesson is not on this phone");
  if (!(await done.isVisible())) await defect(child, step, "offline lesson never finished");
  note(`${step}: played offline from the service worker, ${answered} answers`);

  const savedBadge = child.getByText(prefix(locale, "student.sync.badge.offlineSaved")).first();
  if (!(await savedBadge.isVisible())) await defect(child, step, "badge does not say the work is saved on this phone");
  else note(`${step}: badge "${(await savedBadge.innerText()).trim()}"`);
  await shot(child, "offline-badge-saved");

  await context.setOffline(false);
  await child.evaluate(() => window.dispatchEvent(new Event("online")));
  const allSent = child.getByText(t(locale, "student.sync.badge.allSent")).first();
  try {
    await expect(allSent).toBeVisible({ timeout: 90_000 });
  } catch {
    await defect(child, step, "badge never reached 'All work sent' within 90s of reconnecting");
  }
  const summary = child.locator("details > summary").first();
  if (await summary.isVisible()) await tap(summary);
  const confirmed = child.getByText(prefix(locale, "student.sync.rows.confirmed")).first();
  let confirmedText = "";
  try {
    await expect(confirmed).toBeVisible({ timeout: 10_000 });
    confirmedText = (await confirmed.innerText()).trim();
  } catch {
    /* recorded below */
  }
  await shot(child, "online-badge-confirmed");
  const confirmedCount = Number((confirmedText.match(/\d+/) ?? ["0"])[0]);
  if (confirmedCount < 1) await defect(child, step, `server-confirmed row missing or zero ("${confirmedText}")`);
  else note(`${step}: badge panel "${confirmedText}"`);

  const fresh = await readSession(child);
  const after = await apiGet<{ total_attempts?: number }>(
    `/v1/learning/students/${encodeURIComponent(fresh.subject)}/progress`,
    fresh.accessToken,
  );
  note(`${step}: API total_attempts before=${before.body.total_attempts} after=${after.body.total_attempts}`);
  if ((after.body.total_attempts ?? 0) <= (before.body.total_attempts ?? 0)) {
    await defect(child, step, "offline answers are not visible as evidence through the API after sync");
  }
}

// ------------------------------------------------------------------------------------- step 4

async function guardianSeesAndWithdraws(family: Family, child: Page): Promise<void> {
  const locale: Locale = "en";
  const step = "4 guardian";
  currentStep = step;
  const g = family.guardian;
  await g.goto("/guardian");
  await g.waitForLoadState("networkidle");
  if (!(await g.getByText(family.learnerName).first().isVisible())) {
    await defect(g, step, "child not listed on the guardian dashboard");
  }
  await shot(g, "guardian-dashboard");
  await g.goto(`/guardian/children/${encodeURIComponent(family.studentRef)}`);
  await g.waitForLoadState("networkidle");
  await expect(g.getByRole("heading").first()).toContainText(family.learnerName);
  await shot(g, "guardian-child");
  await checkClipping(g, `${step} /guardian/children`);
  note(`${step}: dashboard and child page show ${family.learnerName}`);

  await g.goto("/guardian/family");
  const section = g.locator(`section[id="learner-${family.studentRef}"]`);
  await tap(section.getByRole("button", { name: t(locale, "guardian.consent.stop") }));
  const dialog = g.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await shot(g, "guardian-withdraw-dialog");
  await tap(dialog.getByRole("button", { name: t(locale, "guardian.consent.confirm.allConfirm") }));
  await expect(section).not.toContainText(t(locale, "guardian.access.given"), { timeout: 15_000 });
  await shot(g, "guardian-withdrawn");
  note(`${step}: consent withdrawn through the confirmation dialog`);

  // The child's tab is still open on the progress page. Their next action: start learning again.
  await child.goto("/student/today");
  await child.waitForTimeout(1500);
  const start = child.getByRole("link", { name: t(locale, "student.today.start"), exact: true });
  if (await start.isVisible()) {
    await tap(start);
    await child.waitForTimeout(3000);
  }
  await child.waitForLoadState("networkidle");
  const file = await shot(child, "child-after-withdrawal");
  const url = new URL(child.url()).pathname;
  const body = await child.locator("body").innerText();
  const honest = [
    t(locale, "auth.errors.consentNeeded"),
    prefix(locale, "student.sync.held.consent"),
  ].some((s) => body.includes(s));
  note(`${step}: child's next action -> ${url}; consent message shown: ${honest}; screenshot ${file}`);
  const session = await readSession(child);
  if (session.accessToken) {
    const probe = await apiGet<{ code?: string }>(
      `/v1/learning/students/${encodeURIComponent(family.studentRef)}/progress`,
      session.accessToken,
    );
    note(`${step}: API with the child's token after withdrawal -> ${probe.status} ${probe.body.code ?? ""}`);
    if (probe.status < 400) await defect(child, step, `API still serves the child after withdrawal (${probe.status})`);
  }
  if (!honest) {
    await defect(
      child,
      step,
      `after withdrawal the child's next action shows no consent message (landed on ${url}); ` +
        "expected the 'permission is needed' state",
    );
  }
}

// ------------------------------------------------------------------------------------------ tests

test("ur: guardian joins, enrols, consents; child signs in and finishes a lesson (steps 1-2)", async ({ browser }) => {
  const family = await guardianJoinsAndEnrols(browser, "ur", "مصنوعی طالب علم");
  await childSignsInAndLearns(browser, "ur", family);
});

test("en: full journey — lesson, offline play and sync, guardian view, withdrawal (steps 1-4)", async ({ browser }) => {
  const family = await guardianJoinsAndEnrols(browser, "en", "Synthetic Learner");
  const child = await childSignsInAndLearns(browser, "en", family);
  await offlineLesson(child, child.context());
  await guardianSeesAndWithdraws(family, child);
});
