// Automated WCAG 2.2 A/AA scan of every apps/web route, in Urdu (RTL) and English.
//
// How signed-in pages are reached: beforeAll creates a synthetic guardian and learner through the
// REAL identity API (register, enrol, consent, family-code + PIN sign-in), then each scan starts in
// a fresh browser context whose localStorage already holds that session (`taleem.session.v1`), the
// matching device id, and the interface-locale choice. That is exactly the state the app's own
// sign-in screens leave behind; the forms themselves are scanned signed-out. Protected routes are
// also scanned signed-out, to cover the redirect/sign-in-prompt state a child actually sees.
//
// A scan FAILS on any violation with impact "serious" or "critical". Every violation (any impact)
// is written to $A11Y_OUT/a11y-report.{json,md} with route, locale, rule, and CSS selectors.
//
// Synthetic data only: an @example.invalid guardian and a made-up learner, created for this run.
// Tokens are never written to the report.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { randomBytes, randomInt } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const API = process.env.A11Y_API_URL ?? "http://127.0.0.1:8766";
const OUT = process.env.A11Y_OUT ?? join(process.cwd(), "a11y-results");
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];
const BLOCKING = new Set(["serious", "critical"]);
const LOCALES = ["ur", "en"] as const;
const DEVICE_ID = randomBytes(16).toString("hex");
// Each run presents its own RFC 5737 documentation address, so the shared sign-in limiter gives it
// a fresh budget (the API is started with TALEEM_CLIENT_IP_HEADER=x-real-ip, as on Vercel).
const CLIENT_IP = `198.51.100.${randomInt(1, 255)}`;

type Locale = (typeof LOCALES)[number];
type Auth = "signed-out" | "guardian" | "student";

interface Envelope {
  session: { access_token: string; expires_at: number; role: string; subject: string };
  refresh_token: string;
  learner?: unknown;
  guardian?: unknown;
}

interface Finding {
  route: string;
  locale: Locale;
  auth: Auth;
  dir: string;
  lang: string;
  rule: string;
  impact: string;
  help: string;
  helpUrl: string;
  wcag: string[];
  selectors: string[];
}

const sessions: Partial<Record<Exclude<Auth, "signed-out">, Envelope>> = {};
let studentRef = "";
const findings: Finding[] = [];
const scanned: {
  route: string;
  locale: Locale;
  auth: Auth;
  dir: string;
  heading: string;
  violations: number;
  needsReview: number;
  overflowPx: number;
  urduFont: string;
}[] = [];
const reviews: { route: string; locale: Locale; auth: Auth; rule: string; selectors: string[] }[] =
  [];

async function api<T>(path: string, body: unknown, token?: string): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-real-ip": CLIENT_IP,
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return (await response.json()) as T;
}

function syntheticPin(): string {
  for (;;) {
    const pin = String(randomInt(0, 10_000)).padStart(4, "0");
    if (new Set(pin).size === 4 && !["1234", "4321", "0123"].includes(pin)) return pin;
  }
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  const email = `a11y-${randomBytes(6).toString("hex")}@example.invalid`;
  const passphrase = randomBytes(18).toString("base64url");
  const pin = syntheticPin();
  const learnerName = "Synthetic Learner";

  const guardian = await api<Envelope & { guardian: { family_code: string } }>(
    "/v1/identity/guardians",
    { email, passphrase, displayName: "Synthetic Guardian", locale: "ur" },
  );
  const learner = await api<{ student_ref: string }>(
    "/v1/identity/learners",
    { displayName: learnerName, pin, gradeLevel: 4 },
    guardian.session.access_token,
  );
  studentRef = learner.student_ref;
  await api(
    "/v1/identity/consents",
    { studentRef, scopes: ["learning_data"], attestation: "Synthetic a11y scan - no real child." },
    guardian.session.access_token,
  );
  sessions.guardian = await api<Envelope>("/v1/identity/guardians:signin", { email, passphrase });
  sessions.student = await api<Envelope>("/v1/identity/learners:signin", {
    familyCode: guardian.guardian.family_code,
    displayName: learnerName,
    pin,
    deviceId: DEVICE_ID,
  });
});

test.afterAll(() => {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(
    join(OUT, "a11y-report.json"),
    JSON.stringify({ scanned, findings, needs_review: reviews }, null, 2),
  );
  writeFileSync(join(OUT, "a11y-report.md"), renderMarkdown());
});

function renderMarkdown(): string {
  const blocking = findings.filter((f) => BLOCKING.has(f.impact));
  const lines = [
    "# Automated accessibility scan (axe-core, WCAG 2.2 A/AA)",
    "",
    `Scans: ${scanned.length} (route x locale x auth state). Violations: ${findings.length}, of which ` +
      `serious/critical: ${blocking.length}.`,
    "",
    "Automated checks find a subset of WCAG failures; this is not an accessibility audit (EV-05).",
    "",
    "Control: a deliberately broken page is scanned first and must be flagged, so a clean result",
    "here means the scanner ran, not that it was blind. Screenshots of every scan are saved next to",
    "this report.",
    "",
    "## Scans",
    "",
    "| Route | Locale | Auth | dir | First heading | Violations | Needs review |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    ...scanned.map(
      (s) =>
        `| \`${s.route}\` | ${s.locale} | ${s.auth} | ${s.dir} | ${s.heading.replace(/\|/g, "/")} | ` +
        `${s.violations} | ${s.needsReview} |`,
    ),
    "",
    "## Violations",
    "",
    "| Impact | Rule | Route | Locale | Auth | Selectors |",
    "| --- | --- | --- | --- | --- | --- |",
    ...(findings.length ? [] : ["| - | none | - | - | - | - |"]),
    ...findings.map(
      (f) =>
        `| ${f.impact} | [${f.rule}](${f.helpUrl}) | \`${f.route}\` | ${f.locale} | ${f.auth} | ` +
        `${f.selectors.map((s) => `\`${s.replace(/\|/g, "\\|")}\``).join("<br>")} |`,
    ),
    "",
    "## Supplementary checks (non-blocking, not axe)",
    "",
    "Horizontal overflow at the 393 px phone viewport (WCAG 1.4.10 Reflow candidate), and whether the",
    'Urdu face named by the design tokens ("Noto Nastaliq Urdu") was available to the browser. The app',
    "ships no @font-face, so Urdu rendering depends on fonts installed on the device.",
    "",
    "| Route | Locale | Auth | Overflow (px) | Urdu font |",
    "| --- | --- | --- | --- | --- |",
    ...scanned
      .filter((s) => s.overflowPx > 0 || (s.locale === "ur" && s.urduFont === "missing"))
      .map((s) => `| \`${s.route}\` | ${s.locale} | ${s.auth} | ${s.overflowPx} | ${s.urduFont} |`),
    "",
    "## Needs manual review (axe could not decide automatically)",
    "",
    "| Rule | Route | Locale | Auth | Selectors |",
    "| --- | --- | --- | --- | --- |",
    ...(reviews.length ? [] : ["| none | - | - | - | - |"]),
    ...reviews.map(
      (r) =>
        `| ${r.rule} | \`${r.route}\` | ${r.locale} | ${r.auth} | ` +
        `${r.selectors.map((s) => `\`${s.replace(/\|/g, "\\|")}\``).join("<br>")} |`,
    ),
    "",
  ];
  return lines.join("\n");
}

async function prepare(page: Page, locale: Locale, auth: Auth): Promise<void> {
  const envelope = auth === "signed-out" ? undefined : sessions[auth];
  const stored = envelope
    ? {
        role: envelope.session.role,
        subject: envelope.session.subject,
        accessToken: envelope.session.access_token,
        expiresAt: envelope.session.expires_at,
        refreshToken: envelope.refresh_token,
        learner: envelope.learner,
        guardian: envelope.guardian,
      }
    : null;
  await page.addInitScript(
    ([loc, device, session]) => {
      window.localStorage.setItem("taleem.uiLocale.v1", loc as string);
      window.localStorage.setItem("taleem.device.v1", device as string);
      if (session) window.localStorage.setItem("taleem.session.v1", session as string);
    },
    [locale, DEVICE_ID, stored ? JSON.stringify(stored) : ""],
  );
}

async function scan(page: Page, route: string, locale: Locale, auth: Auth): Promise<void> {
  await prepare(page, locale, auth);
  await page.goto(route, { waitUntil: "networkidle" });
  // Client components hydrate, read the session, and fetch; give them a moment to settle.
  await page.waitForTimeout(750);
  const { dir, lang, heading, overflowPx, urduFont } = await page.evaluate(() => ({
    dir: document.documentElement.dir || "(unset)",
    lang: document.documentElement.lang || "(unset)",
    heading: (document.querySelector("h1, h2")?.textContent ?? "(no heading)").trim().slice(0, 60),
    // Supplementary (non-blocking): horizontal overflow at the phone viewport (WCAG 1.4.10 Reflow)
    // and whether the Urdu face the design tokens name is actually available to the browser.
    overflowPx: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
    // document.fonts.check() is true when no matching face is declared at all, so probe instead:
    // if text set in the named face measures the same as the monospace fallback, it is not there.
    urduFont: (() => {
      const ctx = document.createElement("canvas").getContext("2d");
      if (!ctx) return "unknown";
      const sample = "اردو زبان سیکھیں";
      ctx.font = "32px monospace";
      const fallback = ctx.measureText(sample).width;
      ctx.font = '32px "Noto Nastaliq Urdu", monospace';
      return ctx.measureText(sample).width === fallback ? "missing" : "available";
    })(),
  }));
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const landed = new URL(page.url()).pathname;
  const label = landed === route.split("?")[0] ? route : `${route} -> ${landed}`;
  for (const v of results.violations) {
    findings.push({
      route: label,
      locale,
      auth,
      dir,
      lang,
      rule: v.id,
      impact: v.impact ?? "unknown",
      help: v.help,
      helpUrl: v.helpUrl,
      wcag: v.tags.filter((t) => t.startsWith("wcag")),
      selectors: v.nodes.map((n) => n.target.join(" ")),
    });
  }
  for (const r of results.incomplete) {
    reviews.push({
      route: label,
      locale,
      auth,
      rule: r.id,
      selectors: r.nodes.map((n) => n.target.join(" ")),
    });
  }
  scanned.push({
    route: label,
    locale,
    auth,
    dir,
    heading,
    violations: results.violations.length,
    needsReview: results.incomplete.length,
    overflowPx,
    urduFont,
  });
  mkdirSync(join(OUT, "screenshots"), { recursive: true });
  const shot = `${locale}-${auth}-${route.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home"}`;
  await page.screenshot({ path: join(OUT, "screenshots", `${shot}.png`), fullPage: true });
  const blocking = results.violations
    .filter((v) => BLOCKING.has(v.impact ?? ""))
    .map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(blocking, `serious/critical WCAG violations on ${label} (${locale}, ${auth})`).toEqual([]);
}

// Control: the scanner must flag a page that is broken on purpose (an image with no text
// alternative, an unlabeled button, an input with no label). Guards against a vacuous clean run.
test("control: a deliberately inaccessible page is flagged", async ({ page }) => {
  await page.setContent(
    '<html lang="en"><body><main><img src="x.png"><button></button><input type="text"></main></body></html>',
  );
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const rules = results.violations.map((v) => v.id);
  expect(rules).toEqual(expect.arrayContaining(["image-alt", "button-name", "label"]));
});

const PUBLIC_ROUTES = ["/", "/join", "/signin", "/guardian/signin"];
const STUDENT_ROUTES = [
  "/student/today",
  "/student/subjects",
  "/student/homework",
  "/student/progress",
  "/student/profile",
  "/student/session",
  "/student/offline",
  // The fixture lesson is published but not downloaded into this fresh browser, so this scans the
  // player's "not saved on this phone" state, not a lesson mid-play.
  "/student/offline/play?lesson=E2E-SYNTHETIC-FIXTURE-fractions",
];
const GUARDIAN_ROUTES = ["/guardian", "/guardian/family", "/guardian/children/:studentRef"];

for (const locale of LOCALES) {
  test.describe(`locale ${locale}`, () => {
    for (const route of PUBLIC_ROUTES) {
      test(`${route} signed-out`, async ({ page }) => scan(page, route, locale, "signed-out"));
    }
    for (const route of STUDENT_ROUTES) {
      test(`${route} as learner`, async ({ page }) => scan(page, route, locale, "student"));
    }
    for (const route of GUARDIAN_ROUTES) {
      test(`${route} as guardian`, async ({ page }) =>
        scan(page, route.replace(":studentRef", encodeURIComponent(studentRef)), locale, "guardian"));
    }
    // The signed-out state of the protected areas: what a child or guardian sees before sign-in.
    for (const route of ["/student/today", "/guardian"]) {
      test(`${route} signed-out`, async ({ page }) => scan(page, route, locale, "signed-out"));
    }
  });
}
