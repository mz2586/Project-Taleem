// "Get a report" (lib/reporting/generate.ts): the period choices and their boundaries, the custom
// dates, the request body, and what the page does for every answer the server can give.
import { describe, expect, it } from "vitest";

import { createTranslator } from "../../i18n/translate";
import { ApiError } from "../../student/types";
import {
  chosenPeriod,
  existingCardFor,
  failedResult,
  generateBody,
  generatedResult,
  generateFailure,
  generateMessage,
  periodOptions,
  presetPeriod,
  type GenerateFailure,
} from "../generate";
import type { ReportCardWire } from "../types";
import { reportCard } from "../wire";

const utc = (y: number, m: number, d: number, h = 0, min = 0, s = 0) => Date.UTC(y, m - 1, d, h, min, s) / 1000;
const NOW = utc(2026, 10, 24, 15, 42, 17);
const en = { t: createTranslator("en"), locale: "en" as const, timeZone: "UTC" };

describe("period choices", () => {
  it("last month is the whole previous UTC calendar month, end exclusive", () => {
    expect(presetPeriod("last_month", NOW)).toEqual({ periodStart: utc(2026, 9, 1), periodEnd: utc(2026, 10, 1) });
  });

  it("last 3 months are the three whole months before this one", () => {
    expect(presetPeriod("last_3_months", NOW)).toEqual({ periodStart: utc(2026, 7, 1), periodEnd: utc(2026, 10, 1) });
  });

  it("crosses a year boundary in January", () => {
    const jan = utc(2027, 1, 10, 9);
    expect(presetPeriod("last_month", jan)).toEqual({ periodStart: utc(2026, 12, 1), periodEnd: utc(2027, 1, 1) });
    expect(presetPeriod("last_3_months", jan)).toEqual({ periodStart: utc(2026, 10, 1), periodEnd: utc(2027, 1, 1) });
  });

  it("on the very first second of a month, last month is still the closed month just ended", () => {
    const first = utc(2026, 11, 1);
    expect(presetPeriod("last_month", first)).toEqual({ periodStart: utc(2026, 10, 1), periodEnd: first });
    expect(presetPeriod("last_month", first)!.periodEnd).toBeLessThanOrEqual(first);
  });

  it("this term so far starts at the term's first day and ends at now rounded down to the hour", () => {
    expect(presetPeriod("term_to_date", NOW)).toEqual({ periodStart: utc(2026, 10, 1), periodEnd: utc(2026, 10, 24, 15) });
    expect(presetPeriod("term_to_date", utc(2026, 8, 20, 6, 59, 59))).toEqual({
      periodStart: utc(2026, 7, 1),
      periodEnd: utc(2026, 8, 20, 6),
    });
    // Asking twice in the same hour asks for the identical period (so the second opens the first card).
    expect(presetPeriod("term_to_date", utc(2026, 10, 24, 15, 0, 1))).toEqual(presetPeriod("term_to_date", NOW));
  });

  it("this term so far is unavailable in the term's first hour (start must be before end)", () => {
    expect(presetPeriod("term_to_date", utc(2026, 10, 1, 0, 0, 0))).toBeNull();
    expect(presetPeriod("term_to_date", utc(2026, 10, 1, 0, 59, 59))).toBeNull();
    expect(presetPeriod("term_to_date", utc(2026, 10, 1, 1, 0, 0))).toEqual({ periodStart: utc(2026, 10, 1), periodEnd: utc(2026, 10, 1, 1) });
    expect(chosenPeriod("term_to_date", { start: "", end: "" }, utc(2026, 10, 1, 0, 30))).toEqual({
      ok: false,
      problems: { start: "guardian.reportCards.generate.termTooNew" },
    });
  });

  it("every preset is closed: start < end <= now", () => {
    for (const now of [NOW, utc(2026, 1, 1), utc(2026, 3, 31, 23, 59, 59), utc(2026, 4, 1, 2)]) {
      for (const choice of ["last_month", "last_3_months", "term_to_date"] as const) {
        const p = presetPeriod(choice, now);
        if (!p) continue;
        expect(p.periodStart).toBeLessThan(p.periodEnd);
        expect(p.periodEnd).toBeLessThanOrEqual(now);
      }
    }
  });

  it("custom dates use the advanced fields' rules (and refuse a future last day)", () => {
    const local = (y: number, m: number, d: number) => Math.floor(new Date(y, m - 1, d).getTime() / 1000);
    const now = local(2026, 10, 24) + 15 * 3600;
    expect(chosenPeriod("custom", { start: "2026-09-01", end: "2026-09-30" }, now)).toEqual({
      ok: true,
      periodStart: local(2026, 9, 1),
      periodEnd: local(2026, 10, 1),
    });
    expect(chosenPeriod("custom", { start: "2026-09-01", end: "2026-10-25" }, now)).toEqual({
      ok: false,
      problems: { end: "teacher.reportCards.endFuture" },
    });
    expect(chosenPeriod("custom", { start: "", end: "2026-10-01" }, now)).toEqual({
      ok: false,
      problems: { start: "teacher.reportCards.startEmpty" },
    });
  });

  it("each choice shows the exact dates it means; the custom one shows none", () => {
    const options = periodOptions(NOW, en);
    expect(options.map((o) => [o.choice, o.label, o.dates, o.available])).toEqual([
      ["last_month", "Last month", "From Sep 1, 2026 to Sep 30, 2026", true],
      ["last_3_months", "Last 3 months", "From Jul 1, 2026 to Sep 30, 2026", true],
      ["term_to_date", "This term so far", "From Oct 1, 2026 to Oct 24, 2026", true],
      ["custom", "Other dates (advanced)", null, true],
    ]);
    const early = periodOptions(utc(2026, 10, 1, 0, 10), en).find((o) => o.choice === "term_to_date")!;
    expect(early).toMatchObject({ available: false, dates: "Not available yet — the term has only just started." });
    const ur = periodOptions(NOW, { t: createTranslator("ur"), locale: "ur", timeZone: "UTC" });
    expect(ur[0]!.label).toBe("پچھلا مہینہ");
  });

  it("sends exactly {period_start, period_end}", () => {
    expect(generateBody({ periodStart: 10, periodEnd: 20 })).toEqual({ period_start: 10, period_end: 20 });
  });
});

function card(over: Partial<ReportCardWire> = {}) {
  return reportCard(
    {
      card_id: "rc-1",
      student_ref: "S1",
      period_start: utc(2026, 9, 1),
      period_end: utc(2026, 10, 1),
      issued_by: "system",
      issued_by_name: "Taleem",
      issued_at: utc(2026, 10, 1, 1),
      status: "issued",
      has_evidence: true,
      subjects: [],
      ...over,
    },
    ["en"],
  );
}

describe("generate outcomes", () => {
  const period = { periodStart: utc(2026, 9, 1), periodEnd: utc(2026, 10, 1) };

  it.each([
    [409, "REPORT_CARD_EXISTS", "exists"],
    [403, "LEARNER_NOT_ELIGIBLE", "not-eligible"],
    [403, "FORBIDDEN", "not-yours"],
    [404, "NOT_FOUND", "not-yours"],
    [429, "RATE_LIMITED", "rate-limited"],
    [422, "VALIDATION", "period"],
    [0, "OFFLINE", "offline"],
    [401, "UNAUTHENTICATED", "signed-out"],
    [500, "INTERNAL", "error"],
  ] as const)("%i %s → %s", (status, code, expected) => {
    expect(generateFailure(new ApiError(status, { code }))).toBe(expected satisfies GenerateFailure);
  });

  it("a thrown non-API error is a plain error", () => {
    expect(generateFailure(new Error("boom"))).toBe("error");
  });

  it("201 opens the new card", () => {
    expect(generatedResult(card({ card_id: "rc-new" }))).toEqual({ kind: "open", cardId: "rc-new", existed: false });
    expect(generatedResult(card({ card_id: null }))).toEqual({ kind: "failed", failure: "error" });
  });

  it("409 REPORT_CARD_EXISTS opens the card already there for exactly that period — not an error", () => {
    const cards = [
      card({ card_id: "other-dates", period_end: utc(2026, 9, 30) }),
      card({ card_id: "old", superseded_by: "teacher-fix", status: "superseded" }),
      card({ card_id: "teacher-fix", issued_by: "T-7", issued_by_name: "Ms Sana", issued_at: utc(2026, 10, 2) }),
      card({ card_id: "sys" }),
    ];
    expect(existingCardFor(cards, period)?.cardId).toBe("sys");
    expect(failedResult("exists", period, cards)).toEqual({ kind: "open", cardId: "sys", existed: true });
    // Not in the list (or the list could not be read): say it exists, without an error.
    expect(failedResult("exists", period, [cards[0]!])).toEqual({ kind: "exists-unlisted" });
    expect(failedResult("exists", period, null)).toEqual({ kind: "exists-unlisted" });
  });

  it("every other failure is a message in plain words, in both languages", () => {
    const t = createTranslator("en");
    const tu = createTranslator("ur");
    expect(generateMessage(failedResult("not-eligible", period, null), t)).toEqual({
      title: "A report cannot be made right now",
      body: "Learning permission for your child is switched off, or your child's account is not active. Turn the permission back on from your child's page, then try again.",
    });
    expect(generateMessage(failedResult("not-yours", period, null), t)?.body).toBe(
      "This child is not linked to your account, so a report cannot be made.",
    );
    expect(generateMessage(failedResult("rate-limited", period, null), t)?.title).toBe("Please wait");
    expect(generateMessage(failedResult("rate-limited", period, null), tu)?.title).toBe("براہِ کرم انتظار کریں");
    expect(generateMessage(failedResult("not-eligible", period, null), tu)?.title).toBe("ابھی رپورٹ نہیں بن سکتی");
    expect(generateMessage(failedResult("exists", period, null), t)?.title).toBe("This report already exists");
    expect(generateMessage({ kind: "open", cardId: "x", existed: true }, t)).toBeNull();
    for (const f of ["period", "offline", "signed-out", "error"] as const) {
      const m = generateMessage(failedResult(f, period, null), tu)!;
      expect(m.title.length).toBeGreaterThan(0);
      expect(m.body).not.toMatch(/guardian\./);
    }
  });
});
