import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import { CATALOGS } from "../../i18n/messages";
import { SUPPORTED_LOCALES } from "../../i18n/config";
import { CATEGORIES, CATEGORY_OPTIONS, cleanText, isCategory, MAX_TEXT } from "../categories";
import { childPayload, childReducer, failureOutcome, initialChildState, type ChildState } from "../childFlow";
import { cleanLessonId, helpHref, readHelpContext, screenFromPath } from "../context";
import { parseLeadToken } from "../session";
import {
  actionErrorKey,
  ageLabel,
  allowedActions,
  guardianErrorKey,
  guardianStatusKey,
  outcomeOptions,
  overdueKey,
  slaBanner,
  sortQueue,
  statusKey,
  thresholdText,
} from "../triage";

function jwt(claims: Record<string, unknown>): string {
  const enc = (v: unknown) => Buffer.from(JSON.stringify(v)).toString("base64url");
  return `${enc({ alg: "none" })}.${enc(claims)}.sig`;
}

describe("categories", () => {
  it("mirrors the server's fixed list, each with a picture and both wordings", () => {
    expect(CATEGORIES).toEqual(["felt_unsafe", "very_sad", "bullying", "upsetting_lesson", "other"]);
    expect(CATEGORY_OPTIONS.map((o) => o.value)).toEqual([...CATEGORIES]);
    for (const option of CATEGORY_OPTIONS) {
      expect(option.symbol).not.toBe("");
      for (const locale of SUPPORTED_LOCALES) {
        expect(translate(locale, option.childKey)).not.toBe(option.childKey);
        expect(translate(locale, option.adultKey)).not.toBe(option.adultKey);
      }
    }
    expect(CATEGORY_OPTIONS.some((o) => (o.priority as string) === "T0")).toBe(false);
    expect(isCategory("bullying")).toBe(true);
    expect(isCategory("made_up")).toBe(false);
  });

  it("bounds text without silently cutting it", () => {
    expect(cleanText("   ")).toEqual({ ok: true, text: null });
    expect(cleanText(" hi ")).toEqual({ ok: true, text: "hi" });
    expect(cleanText("ب".repeat(MAX_TEXT))).toEqual({ ok: true, text: "ب".repeat(MAX_TEXT) });
    expect(cleanText("x".repeat(MAX_TEXT + 1))).toEqual({ ok: false, reason: "too-long" });
  });
});

describe("context", () => {
  it("keeps plain screen names and drops anything carrying an identifier", () => {
    expect(screenFromPath("/student/today")).toBe("student/today");
    expect(screenFromPath("/student/offline/play?lesson=L-1")).toBe("student/offline/play");
    expect(screenFromPath("/guardian/children/stu_0193abc")).toBe("");
    expect(screenFromPath("/x/0193a6f2-1b2c-7d3e-8f90-1234567890ab")).toBe("");
    expect(screenFromPath("javascript:alert(1)")).toBe("");
    expect(cleanLessonId("L-math-g4-intro-fractions")).toBe("L-math-g4-intro-fractions");
    expect(cleanLessonId("<b>")).toBeNull();
  });

  it("builds the help link and reads it back, validated", () => {
    expect(helpHref("/student/today")).toBe("/student/help?from=student%2Ftoday");
    expect(helpHref("/student/session", "L-1")).toBe("/student/help?from=student%2Fsession&lesson=L-1");
    expect(helpHref("/student/help")).toBe("/student/help");
    expect(readHelpContext("?from=student%2Ftoday&lesson=L-1")).toEqual({ screen: "student/today", lessonId: "L-1" });
    expect(readHelpContext("?from=stu_123&lesson=%3Cb%3E")).toEqual({ screen: "", lessonId: null });
  });
});

describe("child flow", () => {
  const ctx = { screen: "student/today", lessonId: null };

  it("sends with a single tap and no typing", () => {
    let s = childReducer(initialChildState, { type: "choose", category: "felt_unsafe" });
    expect(s.step).toBe("confirm");
    expect(childPayload(s, ctx)).toEqual({ category: "felt_unsafe", context: { screen: "student/today" } });
    s = childReducer(s, { type: "send" });
    expect(s.step).toBe("sending");
    s = childReducer(s, { type: "sent" });
    expect(s).toEqual({ ...initialChildState, step: "sent" }); // nothing kept to show back
  });

  it("adds optional words and refuses over-long ones without sending", () => {
    let s: ChildState = childReducer(initialChildState, { type: "choose", category: "other" });
    s = childReducer(s, { type: "openWords" });
    expect(s.wordsOpen).toBe(true);
    s = childReducer(s, { type: "setText", text: "x".repeat(MAX_TEXT + 1) });
    expect(s.textTooLong).toBe(true);
    expect(childReducer(s, { type: "send" }).step).toBe("confirm");
    s = childReducer(s, { type: "setText", text: "  a boy pushed me  " });
    expect(childPayload(s, { screen: "", lessonId: "L-1" })).toEqual({
      category: "other",
      text: "a boy pushed me",
      context: { lessonId: "L-1" },
    });
    expect(JSON.stringify(childPayload(s, ctx))).not.toMatch(/stu_|student_ref|studentRef/);
  });

  it("explains a failure honestly and lets the child try again", () => {
    expect(failureOutcome({ status: 0 })).toBe("offline");
    expect(failureOutcome({ status: 429 })).toBe("busy");
    expect(failureOutcome({ status: 500 })).toBe("error");
    expect(failureOutcome(new Error("x"))).toBe("error");
    let s = childReducer(childReducer(initialChildState, { type: "choose", category: "bullying" }), { type: "send" });
    s = childReducer(s, { type: "failed", outcome: "offline" });
    expect(s.step).toBe("offline");
    expect(childReducer(s, { type: "retry" }).step).toBe("confirm");
    expect(childReducer(s, { type: "back" })).toEqual(initialChildState);
  });

  it("says offline means nothing was sent or kept, and never promises a response time", () => {
    for (const locale of SUPPORTED_LOCALES) {
      const c = CATALOGS[locale].safeguarding.child;
      expect(c.offlineBody.length).toBeGreaterThan(0);
      for (const text of [c.sentBody, c.sentNow, c.offlineBody]) expect(text).not.toMatch(/\d/);
    }
    expect(CATALOGS.en.safeguarding.child.offlineBody).toMatch(/not sent|wasn't sent/i);
    expect(CATALOGS.en.safeguarding.child.offlineBody).toMatch(/nothing was (saved|kept)/i);
  });
});

describe("console view-model", () => {
  const concern = (id: string, priority: "T1" | "T2" | "T3", created_at: number) => ({
    concern_id: id,
    priority,
    created_at,
  });

  it("orders by priority, then oldest first", () => {
    const sorted = sortQueue([concern("c", "T3", 1), concern("b", "T1", 5), concern("a", "T1", 2), concern("d", "T2", 0)]);
    expect(sorted.map((c) => c.concern_id)).toEqual(["a", "b", "d", "c"]);
  });

  it("labels age without rounding a waiting concern down to nothing", () => {
    expect(ageLabel(5).key).toBe("safeguarding.console.age.justNow");
    expect(ageLabel(119)).toEqual({ key: "safeguarding.console.age.minutes", params: { n: 1 } });
    expect(ageLabel(7200)).toEqual({ key: "safeguarding.console.age.hours", params: { n: 2 } });
    expect(ageLabel(3 * 86_400 + 5)).toEqual({ key: "safeguarding.console.age.days", params: { n: 3 } });
  });

  it("shows 'SLA not set — FD-06' unless every tier has a threshold, and never invents one", () => {
    const unset = slaBanner({ configured: false, acknowledge_within_seconds: { T1: null, T2: null, T3: null }, notice: "x" });
    expect(unset.kind).toBe("unset");
    const partial = slaBanner({ configured: true, acknowledge_within_seconds: { T1: 1800, T2: null, T3: null }, notice: "x" });
    expect(partial).toMatchObject({ kind: "partial", thresholds: [{ priority: "T1", seconds: 1800 }] });
    const set = slaBanner({ configured: true, acknowledge_within_seconds: { T1: 1, T2: 2, T3: 3 }, notice: null });
    expect(set).toEqual({
      kind: "set",
      thresholds: [
        { priority: "T1", seconds: 1 },
        { priority: "T2", seconds: 2 },
        { priority: "T3", seconds: 3 },
      ],
    });
    expect(CATALOGS.en.safeguarding.console.slaNotSet).toBe("SLA not set — owner decision FD-06");
    const en = (key: Parameters<typeof translate>[1], params?: Record<string, string | number>) =>
      translate("en", key, params);
    expect(thresholdText(unset, en)).toBe("");
    expect(thresholdText(partial, en)).toBe("T1 30 min");
    expect(thresholdText(set, en)).toBe("T1 under a minute, T2 under a minute, T3 under a minute");
    expect(overdueKey(null)).toBe("safeguarding.console.overdue.unknown");
    expect(overdueKey(true)).toBe("safeguarding.console.overdue.yes");
  });

  it("offers only the actions a status allows; referral only after escalation", () => {
    expect(allowedActions("open")).toEqual({ acknowledge: true, note: true, escalate: true, resolve: true });
    expect(allowedActions("escalated")).toEqual({ acknowledge: false, note: true, escalate: false, resolve: true });
    expect(allowedActions("resolved")).toEqual({ acknowledge: false, note: false, escalate: false, resolve: false });
    expect(outcomeOptions("acknowledged")).not.toContain("referred_externally");
    expect(outcomeOptions("escalated")[0]).toBe("referred_externally");
  });

  it("maps statuses and errors to catalog keys that exist in every locale", () => {
    const keys = [
      statusKey("escalated"),
      guardianStatusKey("in_review"),
      actionErrorKey({ status: 409, problem: { code: "CONCERN_CLOSED" } }),
      actionErrorKey({ status: 409, problem: { code: "CONFLICT" } }),
      actionErrorKey({ status: 403 }),
      actionErrorKey({ status: 0 }),
      actionErrorKey({ status: 500 }),
      guardianErrorKey({ status: 0 }),
      guardianErrorKey({ status: 404 }),
      guardianErrorKey({ status: 422 }),
    ];
    for (const locale of SUPPORTED_LOCALES) {
      for (const key of keys) expect(translate(locale, key)).not.toBe(key);
    }
    expect(new Set(keys.slice(2)).size).toBe(8);
  });
});

describe("lead session", () => {
  it("adopts only a safeguarding_lead token", () => {
    expect(parseLeadToken(jwt({ sub: "stf_1", role: "safeguarding_lead", exp: 200 }), 100)).toEqual({
      ok: true,
      actor: { subject: "stf_1", expiresAt: 200 },
    });
    expect(parseLeadToken(jwt({ sub: "stf_1", role: "safety_officer", exp: 200 }), 100)).toEqual({ ok: false, reason: "not-lead" });
    expect(parseLeadToken(jwt({ sub: "stf_1", role: "safeguarding_lead", exp: 50 }), 100)).toEqual({ ok: false, reason: "expired" });
    expect(parseLeadToken("nope", 100)).toEqual({ ok: false, reason: "malformed" });
  });
});
