// "Get a report" — the guardian asks Taleem to issue their child's card for a closed period
// (POST /v1/reporting/children/{student_ref}/report-cards:generate). Pure and unit-tested.
//
// Period choices are simple on purpose:
// - "Last month" and "Last 3 months" are whole UTC calendar months, the same boundaries the
//   scheduler issues on (`issue_due --period YYYY-MM`), so asking for a month Taleem already reported
//   lands on that card (409 REPORT_CARD_EXISTS → open it) instead of making a near-duplicate.
// - "This term so far" runs from the start of the current term to now, rounded DOWN to the hour, so
//   the period is closed (end ≤ now) and asking twice within the hour opens the same card.
// - "Other dates" (advanced) are two local calendar days, end exclusive, capped at now.
// Every period is `[start, end)` with start < end ≤ now, as the server requires.

import type { MessageKey } from "../i18n/messages";
import type { Translator } from "../i18n/translate";
import { ApiError } from "../student/types";
import { periodFromInputs, type Period, type PeriodInputs } from "./teacher";
import type { GenerateBody } from "./types";
import { periodText, type ViewContext } from "./view";
import type { ReportCard } from "./wire";

const HOUR = 60 * 60;

/**
 * The months (0 = January) a school term starts in. Until a school calendar is configured, a term is
 * a calendar quarter; the chosen dates are always shown beside the choice, so nothing is hidden.
 */
export const TERM_START_MONTHS: readonly number[] = [0, 3, 6, 9];

export type PeriodChoice = "last_month" | "last_3_months" | "term_to_date" | "custom";
export const PERIOD_CHOICES: readonly PeriodChoice[] = ["last_month", "last_3_months", "term_to_date", "custom"];

export interface PeriodRange {
  periodStart: number;
  periodEnd: number;
}

const utcMonth = (year: number, month: number) => Date.UTC(year, month, 1) / 1000;

/** A preset's period, or null when it would be empty right now (the first hour of a term). */
export function presetPeriod(choice: Exclude<PeriodChoice, "custom">, nowSeconds: number): PeriodRange | null {
  const now = new Date(nowSeconds * 1000);
  const y = now.getUTCFullYear();
  const m = now.getUTCMonth();
  switch (choice) {
    case "last_month":
      return { periodStart: utcMonth(y, m - 1), periodEnd: utcMonth(y, m) };
    case "last_3_months":
      return { periodStart: utcMonth(y, m - 3), periodEnd: utcMonth(y, m) };
    case "term_to_date": {
      const startMonth = [...TERM_START_MONTHS].reverse().find((s) => s <= m) ?? 0;
      const periodStart = utcMonth(y, startMonth);
      const periodEnd = Math.floor(nowSeconds / HOUR) * HOUR;
      return periodEnd > periodStart ? { periodStart, periodEnd } : null;
    }
  }
}

export interface PeriodOption {
  choice: PeriodChoice;
  label: string;
  /** "From 1 Sep 2026 to 30 Sep 2026"; null for the custom choice. */
  dates: string | null;
  /** False when the preset would be empty right now. */
  available: boolean;
}

/** The radio choices with the exact dates each one means, so nothing is hidden behind a word. */
export function periodOptions(nowSeconds: number, c: ViewContext): PeriodOption[] {
  return PERIOD_CHOICES.map((choice) => {
    const label = c.t(`guardian.reportCards.generate.choices.${choice}`);
    if (choice === "custom") return { choice, label, dates: null, available: true };
    const range = presetPeriod(choice, nowSeconds);
    return {
      choice,
      label,
      dates: range ? periodText(range.periodStart, range.periodEnd, c) : c.t("guardian.reportCards.generate.notAvailableNow"),
      available: !!range,
    };
  });
}

/** The period to ask for: a preset, or the advanced custom days (with field problems). */
export function chosenPeriod(choice: PeriodChoice, custom: PeriodInputs, nowSeconds: number): Period {
  if (choice === "custom") return periodFromInputs(custom, nowSeconds);
  const range = presetPeriod(choice, nowSeconds);
  return range ? { ok: true, ...range } : { ok: false, problems: { start: "guardian.reportCards.generate.termTooNew" } };
}

export function generateBody(period: PeriodRange): GenerateBody {
  return { period_start: period.periodStart, period_end: period.periodEnd };
}

// ---- outcomes -----------------------------------------------------------------------------------------

export type GenerateFailure =
  | "exists" // 409 REPORT_CARD_EXISTS: open the card that is already there
  | "not-eligible" // 403 LEARNER_NOT_ELIGIBLE: learning consent is not live
  | "not-yours" // 404 (and any other 403): not this guardian's child
  | "rate-limited" // 429
  | "period" // 422: the server refused the dates
  | "offline"
  | "signed-out"
  | "error";

export function generateFailure(error: unknown): GenerateFailure {
  if (!(error instanceof ApiError)) return "error";
  switch (error.status) {
    case 0:
      return "offline";
    case 401:
      return "signed-out";
    case 403:
      return error.problem.code === "LEARNER_NOT_ELIGIBLE" ? "not-eligible" : "not-yours";
    case 404:
      return "not-yours";
    case 409:
      return "exists";
    case 422:
      return "period";
    case 429:
      return "rate-limited";
    default:
      return "error";
  }
}

export const GENERATE_FAILURE_KEYS: Record<Exclude<GenerateFailure, "exists">, { title: MessageKey; body: MessageKey }> = {
  "not-eligible": { title: "guardian.reportCards.generate.notEligibleTitle", body: "guardian.reportCards.generate.notEligibleBody" },
  "not-yours": { title: "guardian.reportCards.generate.notYoursTitle", body: "guardian.reportCards.generate.notYoursBody" },
  "rate-limited": { title: "guardian.reportCards.generate.rateLimitedTitle", body: "guardian.reportCards.generate.rateLimitedBody" },
  period: { title: "guardian.reportCards.generate.periodTitle", body: "guardian.reportCards.generate.periodBody" },
  offline: { title: "guardian.reportCards.generate.offlineTitle", body: "guardian.reportCards.generate.offlineBody" },
  "signed-out": { title: "guardian.reportCards.generate.signedOutTitle", body: "guardian.reportCards.generate.signedOutBody" },
  error: { title: "guardian.reportCards.generate.errorTitle", body: "guardian.reportCards.generate.errorBody" },
};

/**
 * After 409 REPORT_CARD_EXISTS: the current card for exactly this period (a system card first, then
 * the newest), or null when the list does not show it (then the guardian is told it exists).
 */
export function existingCardFor(cards: readonly ReportCard[], period: PeriodRange): ReportCard | null {
  const matches = cards.filter(
    (c) =>
      c.cardId &&
      c.periodStart === period.periodStart &&
      c.periodEnd === period.periodEnd &&
      c.status !== "superseded" &&
      !c.supersededBy,
  );
  matches.sort((a, b) => Number(b.isSystem) - Number(a.isSystem) || (b.issuedAt ?? 0) - (a.issuedAt ?? 0));
  return matches[0] ?? null;
}

/** What the page does next with a generate answer. */
export type GenerateResult =
  | { kind: "open"; cardId: string; existed: boolean }
  | { kind: "exists-unlisted" }
  | { kind: "failed"; failure: Exclude<GenerateFailure, "exists"> };

/** A 201 body → open it. A 201 without an id would be a server fault: say so rather than guess. */
export function generatedResult(card: ReportCard): GenerateResult {
  return card.cardId ? { kind: "open", cardId: card.cardId, existed: false } : { kind: "failed", failure: "error" };
}

/** A failure → the next step; on "exists", `cards` is the freshly re-read list. */
export function failedResult(failure: GenerateFailure, period: PeriodRange, cards: readonly ReportCard[] | null): GenerateResult {
  if (failure !== "exists") return { kind: "failed", failure };
  const found = cards ? existingCardFor(cards, period) : null;
  return found ? { kind: "open", cardId: found.cardId, existed: true } : { kind: "exists-unlisted" };
}

/** The words for an answer that is not a card to open; null when the page should open a card. */
export function generateMessage(result: GenerateResult, t: Translator): { title: string; body: string } | null {
  if (result.kind === "open") return null;
  if (result.kind === "exists-unlisted")
    return { title: t("guardian.reportCards.generate.existsTitle"), body: t("guardian.reportCards.generate.existsUnlisted") };
  const keys = GENERATE_FAILURE_KEYS[result.failure];
  return { title: t(keys.title), body: t(keys.body) };
}
