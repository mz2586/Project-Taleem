// View models for the path, unit check and record screens. Pure: every string the screens show is
// decided here (from the catalog), so the honesty rules are unit-tested without a browser:
// - every state is a symbol AND words (never colour alone), and "practice done" is never "mastered";
// - the unit check is always "Taleem unit check — not a certificate"; nothing claims certification;
// - a result that is not a pass is "not yet", with what to practise next — never a "fail";
// - an unfinished sitting is "not finished", never failed; offline says plainly it needs internet.

import { formatDate } from "../guardian/format";
import type { Locale } from "../i18n/config";
import type { LocalizedText } from "../i18n/content";
import type { MessageKey } from "../i18n/messages";
import type { Translator } from "../i18n/translate";
import { lessonHref } from "../student/chosenLesson";
import { ApiError } from "../student/types";
import type { LessonState, UnitState } from "./types";
import type { AcademicRecord, CheckResult, CheckSummary, LessonView, RecordSitting, UnitView } from "./wire";

export interface ViewContext {
  t: Translator;
  locale: Locale;
  /** A 0–1 ratio as a percentage in the interface locale. */
  formatPercent: (ratio: number) => string;
}

export interface Badge {
  /** Decorative shape (aria-hidden); the label carries the meaning. */
  symbol: string;
  label: string;
  /** For data-state / styling hooks. */
  state: string;
}

const LESSON_SYMBOL: Record<LessonState, string> = {
  not_started: "○",
  in_progress: "◐",
  practised: "✓",
  mastered: "★",
};

const UNIT_SYMBOL: Record<UnitState, string> = {
  not_started: "○",
  in_progress: "◐",
  ready_for_check: "⚑",
  completed: "★",
};

export function lessonBadge(state: LessonState, t: Translator): Badge {
  return { symbol: LESSON_SYMBOL[state], label: t(`progression.lessonState.${state}`), state };
}

export function unitBadge(state: UnitState, t: Translator): Badge {
  return { symbol: UNIT_SYMBOL[state], label: t(`progression.unitState.${state}`), state };
}

/** The legend: each lesson state with what it means, so "practice done" and "mastered" read apart. */
export function lessonLegend(t: Translator): Array<Badge & { meaning: string }> {
  return (["not_started", "in_progress", "practised", "mastered"] as const).map((s) => ({
    ...lessonBadge(s, t),
    meaning: t(`progression.lessonMeaning.${s}`),
  }));
}

export function pct(ctx: Pick<ViewContext, "formatPercent">, score: number): string {
  return ctx.formatPercent(Math.max(0, Math.min(100, score)) / 100);
}

export function titleOr(text: LocalizedText | null, fallback: string): LocalizedText {
  return text ?? { text: fallback, locale: "" };
}

export function lessonTitle(lesson: LessonView, t: Translator): LocalizedText {
  return titleOr(lesson.title, t("progression.path.untitledLesson", { code: lesson.objectiveCode || "—" }));
}

export function unitProgress(unit: UnitView, t: Translator): string {
  const practised = unit.lessons.filter((l) => l.state === "practised" || l.state === "mastered").length;
  const mastered = unit.lessons.filter((l) => l.state === "mastered").length;
  return t("progression.path.unitProgress", { practised, mastered, total: unit.lessons.length });
}

export function checkHref(unitKey: string): string {
  return `/student/subjects/${encodeURIComponent(unitKey)}/check`;
}

export interface CheckEntry {
  href: string;
  label: string;
  /** "Taleem unit check — not a certificate". */
  claim: string;
  best: string | null;
  note: string | null;
}

/** The "Unit check" entry on a unit, or null when the server says no check is available yet. */
export function checkEntry(unit: UnitView, ctx: ViewContext, hasStoredSitting = false): CheckEntry | null {
  const c = unit.check;
  if (!c.available) return null;
  const { t } = ctx;
  const open = hasStoredSitting || c.openSittingId !== null;
  const tried = c.bestScore !== null;
  const labelKey: MessageKey = open
    ? "progression.check.entryContinue"
    : tried && !c.passed
      ? "progression.check.entryRetake"
      : tried
        ? "progression.check.entryAgain"
        : "progression.check.entryStart";
  const best = tried
    ? t("progression.check.entryBest", {
        score: pct(ctx, c.bestScore ?? 0),
        outcome: t(c.passed ? "progression.result.passedShort" : "progression.result.notYetShort"),
      })
    : null;
  return {
    href: checkHref(unit.key),
    label: t(labelKey),
    claim: t("progression.check.claim"),
    best,
    note: tried && !c.passed && !open ? retakeRule(c, ctx) : null,
  };
}

/** §2 retake rule, in words: after practising the missed ideas, or after 24 hours. */
export function retakeRule(c: Pick<CheckSummary, "canRetake" | "retakeAfter">, ctx: ViewContext): string {
  if (c.canRetake === true) return ctx.t("progression.check.retakeNow");
  if (c.retakeAfter !== null) {
    return ctx.t("progression.check.retakeAfterDate", { date: formatDate(c.retakeAfter, ctx.locale) });
  }
  return ctx.t("progression.check.retakeRule");
}

/** "Question n of N" while answering (n is the next unanswered question). */
export function questionOf(answered: number, total: number, t: Translator): string {
  const n = total > 0 ? Math.min(answered + 1, total) : answered + 1;
  return t("progression.check.questionOf", { current: n, total: Math.max(total, n) });
}

/** The honest offline line for the check screen (online only, §2). */
export function checkOfflineMessage(inSitting: boolean, t: Translator): { title: string; body: string } {
  return {
    title: t("progression.check.offlineTitle"),
    body: t(inSitting ? "progression.check.offlineBodySitting" : "progression.check.offlineBodyStart"),
  };
}

export interface ResultView {
  title: string;
  body: string;
  score: string;
  passMark: string;
  outcome: "passed" | "not_yet";
  claim: string;
  breakdown: Array<{ code: string; title: LocalizedText; line: string; allRight: boolean }>;
  remediation: Array<{ code: string; title: LocalizedText; href: string; action: string }>;
  retake: string | null;
}

/** The plain session (the AI teacher picks); a remediation link with a code opens that lesson. */
export const REMEDIATION_HREF = "/student/session";

export function resultView(result: CheckResult, ctx: ViewContext, retake: Pick<CheckSummary, "canRetake" | "retakeAfter"> | null = null): ResultView {
  const { t } = ctx;
  const passed = result.passed;
  const untitled = (code: string) => t("progression.path.untitledLesson", { code: code || "—" });
  return {
    title: t(passed ? "progression.result.passedTitle" : "progression.result.notYetTitle"),
    body: t(passed ? "progression.result.passedBody" : "progression.result.notYetBody"),
    score: t("progression.result.score", { score: pct(ctx, result.scorePercent) }),
    passMark: t("progression.result.passMark", { mark: pct(ctx, result.passMark) }),
    outcome: passed ? "passed" : "not_yet",
    claim: t("progression.check.claim"),
    breakdown: result.perObjective.map((o) => ({
      code: o.code,
      title: titleOr(o.title, untitled(o.code)),
      line: t("progression.result.objectiveLine", { correct: o.correct, total: o.total }),
      allRight: o.total > 0 && o.correct === o.total,
    })),
    remediation: result.remediation.map((r) => ({
      code: r.code,
      title: titleOr(r.title, untitled(r.code)),
      href: lessonHref(r.code),
      action: t("progression.result.practise"),
    })),
    retake: passed ? null : retakeRule(retake ?? { canRetake: null, retakeAfter: result.retakeAfter }, ctx),
  };
}

// ---- record ---------------------------------------------------------------------------------------

export interface RecordSittingLine {
  key: string;
  date: string | null;
  at: number | null;
  text: string;
  state: "passed" | "not_yet" | "incomplete";
}

export interface RecordUnitView {
  key: string;
  title: LocalizedText;
  badge: Badge;
  best: string;
  sittings: RecordSittingLine[];
}

export interface RecordSubjectView {
  key: string;
  title: LocalizedText;
  units: RecordUnitView[];
}

export interface RecordView {
  grade: string | null;
  gradeCompletion: { text: string; date: string | null } | null;
  subjects: RecordSubjectView[];
  hasSittings: boolean;
  lessonsMastered: { count: string; none: boolean; titles: LocalizedText[] };
  reportCards: Array<{ href: string; label: string }>;
  reportCardsHref: string;
  derivedAt: string | null;
  claim: string;
}

function sittingLine(s: RecordSitting, ctx: ViewContext, index: number): RecordSittingLine {
  const { t } = ctx;
  const date = s.at !== null ? formatDate(s.at, ctx.locale) : null;
  const state = s.state === "incomplete" ? "incomplete" : s.passed ? "passed" : "not_yet";
  const outcome =
    state === "incomplete"
      ? t("progression.record.incomplete")
      : t("progression.record.sittingScore", {
          score: pct(ctx, s.scorePercent ?? 0),
          outcome: t(state === "passed" ? "progression.result.passedShort" : "progression.result.notYetShort"),
        });
  return {
    key: s.sittingId || `${s.unitKey}-${index}`,
    date,
    at: s.at,
    text: date ? t("progression.record.sittingLine", { date, outcome }) : outcome,
    state,
  };
}

export interface RecordLinks {
  /** Where a report card opens, by id. */
  card: (cardId: string) => string;
  /** The report-card list. */
  list: string;
}

export const LEARNER_RECORD_LINKS: RecordLinks = {
  card: (id) => `/student/report-cards/${encodeURIComponent(id)}`,
  list: "/student/report-cards",
};

export function guardianRecordLinks(studentRef: string): RecordLinks {
  const base = `/guardian/children/${encodeURIComponent(studentRef)}/report-cards`;
  return { card: (id) => `${base}/${encodeURIComponent(id)}`, list: base };
}

export function gradeText(grade: number | null, t: Translator): string | null {
  if (grade === null) return null;
  return grade <= 0 ? t("progression.record.gradeKg") : t("progression.record.grade", { grade });
}

export function recordView(record: AcademicRecord, ctx: ViewContext, links: RecordLinks): RecordView {
  const { t } = ctx;
  const subjects = record.subjects.map((s) => ({
    key: s.key,
    title: titleOr(s.title, t("progression.record.otherUnits")),
    units: s.units.map((u) => ({
      key: u.key,
      title: titleOr(u.title, t("progression.path.untitledUnit")),
      badge: unitBadge(u.state, t),
      best: u.best
        ? t("progression.record.best", {
            score: pct(ctx, u.best.scorePercent),
            outcome: t(u.best.passed ? "progression.result.passedShort" : "progression.result.notYetShort"),
          })
        : t("progression.record.noSittings"),
      sittings: u.sittings.map((x, i) => sittingLine(x, ctx, i)),
    })),
  }));
  const completion = record.gradeCompletion;
  const completedGrade = completion?.grade ?? record.grade;
  return {
    grade: gradeText(record.grade, t),
    gradeCompletion: completion
      ? {
          text:
            completedGrade !== null && completedGrade > 0
              ? t("progression.record.gradeCompleted", { grade: completedGrade })
              : t("progression.record.gradeCompletedUnnumbered"),
          date: completion.at !== null ? formatDate(completion.at, ctx.locale) : null,
        }
      : null,
    subjects,
    hasSittings: subjects.some((s) => s.units.some((u) => u.sittings.length > 0)),
    lessonsMastered: {
      count: t("progression.record.lessonsMasteredCount", { count: record.lessonsMasteredCount }),
      none: record.lessonsMasteredCount === 0,
      titles: record.lessonsMastered.map((l) => titleOr(l.title, t("progression.path.untitledLesson", { code: l.objectiveCode || "—" }))),
    },
    reportCards: record.reportCards.map((c) => {
      const start = c.periodStart !== null ? formatDate(c.periodStart, ctx.locale) : null;
      const end = c.periodEnd !== null ? formatDate(c.periodEnd, ctx.locale) : null;
      const issued = c.issuedAt !== null ? formatDate(c.issuedAt, ctx.locale) : null;
      return {
        href: links.card(c.cardId),
        label:
          start && end
            ? t("progression.record.reportCardPeriod", { start, end })
            : issued
              ? t("progression.record.reportCardIssued", { date: issued })
              : t("progression.record.reportCard"),
      };
    }),
    reportCardsHref: links.list,
    derivedAt: record.derivedAt !== null ? t("progression.record.derivedAt", { date: formatDate(record.derivedAt, ctx.locale) }) : null,
    claim: t("progression.record.claim"),
  };
}

// ---- check failures -------------------------------------------------------------------------------

export type CheckFailure = "offline" | "expired" | "gone" | "retake_not_yet" | "not_available" | "signed-out" | "error";

/**
 * How a unit-check request failed. The server's error codes are matched loosely (any code naming a
 * retake, an expiry, or a unit that is not ready), so a renamed code degrades to a plain error.
 */
export function checkFailure(error: unknown): CheckFailure {
  if (!(error instanceof ApiError)) return "error";
  const code = String(error.problem.code ?? "").toUpperCase();
  if (error.status === 0) return "offline";
  if (error.status === 401) return "signed-out";
  if (error.status === 410 || code.includes("EXPIRED") || code.includes("INCOMPLETE")) return "expired";
  if (code.includes("RETAKE") || error.status === 429) return "retake_not_yet";
  if (code.includes("NOT_READY") || code.includes("NOT_AVAILABLE") || code.includes("UNAVAILABLE")) return "not_available";
  if (error.status === 404) return "gone";
  return "error";
}
