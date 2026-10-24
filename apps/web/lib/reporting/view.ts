// Report-card view models (REPORT_CARD_CONTRACT.md §1, §3). Pure and unit-tested; pages only render.
//
// Written for a guardian who may read little:
// - mastery is a picture (three dots, filled by how far along) AND a word — never colour alone;
// - counts are short "word: number" pairs in the interface language and its digits;
// - a card with no evidence says so in words and shows no figures at all (never a row of zeros);
// - who issued it is said plainly: "Issued by Taleem" for a system card, the teacher's name otherwise;
// - a card whose hash the server could not re-verify carries a visible warning;
// - an objective with no practice in the period says "no practice", not "0 of 0 right";
// - the curriculum version pin is kept, small, under each objective.

import type { LocalizedText } from "../i18n/content";
import type { Locale } from "../i18n/config";
import type { MessageKey } from "../i18n/messages";
import type { Translator } from "../i18n/translate";
import { formatDate } from "../guardian/format";
import { ApiError } from "../student/types";
import type { Mastery } from "./types";
import type { Feed, ObjectiveResult, ReportCard, SubjectResult, Totals } from "./wire";

// ---- mastery indicator -----------------------------------------------------------------------------

export interface MasteryMeta {
  /** How many of the three dots are filled. */
  filled: 0 | 1 | 2 | 3;
  /** Shape cue that differs per state (no colour needed). */
  symbol: string;
  labelKey: MessageKey;
}

export const MASTERY_META: Record<Mastery, MasteryMeta> = {
  mastered: { filled: 3, symbol: "●", labelKey: "common.reportCard.mastery.mastered" },
  developing: { filled: 2, symbol: "◐", labelKey: "common.reportCard.mastery.developing" },
  not_started: { filled: 0, symbol: "○", labelKey: "common.reportCard.mastery.not_started" },
};

/** "●●○" — the dots for a state (decorative; the word beside it is the meaning). */
export function masteryDots(m: Mastery): string {
  const { filled } = MASTERY_META[m];
  return "●".repeat(filled) + "○".repeat(3 - filled);
}

// ---- one card ----------------------------------------------------------------------------------------

export interface ObjectiveView {
  code: string;
  title: LocalizedText | null;
  mastery: Mastery;
  masteryLabel: string;
  /** "Questions answered: 5 · Right answers: 3" — absent when nothing was practised. */
  practice: string | null;
  /** "Homework done well: 1 · Homework to try again: 0" — absent when there was no homework. */
  homework: string | null;
  /** Shown instead of the two lines above when there was neither. */
  noPractice: string | null;
  /** "Learned from lesson L-12 v3". */
  pin: string | null;
}

export interface SubjectView {
  key: string;
  name: string;
  nameText: LocalizedText | null;
  /** "Learned well: 2 · Still learning: 1 · Not started yet: 0". */
  summary: string;
  objectives: ObjectiveView[];
}

export interface CardView {
  cardId: string;
  learnerName: string;
  className: string | null;
  period: string;
  /** "Issued by Taleem on …" / "Issued by Ms Sana on …"; null on a preview. */
  issued: string | null;
  isSystem: boolean;
  /** A short plain summary of the whole card; empty when there is no evidence. */
  totals: string[];
  /** The server re-checked the card and it did not match: show a warning. */
  integrityWarning: boolean;
  isPreview: boolean;
  superseded: boolean;
  supersededBy: string | null;
  corrects: boolean;
  hasEvidence: boolean;
  subjects: SubjectView[];
  comment: string | null;
  commentBy: string | null;
  curriculum: string | null;
  reference: string | null;
}

export interface ViewContext {
  t: Translator;
  locale: Locale;
  timeZone?: string;
}

const DAY = 24 * 60 * 60;
const date = (s: number, c: ViewContext) => formatDate(s, c.locale, c.timeZone ? { timeZone: c.timeZone } : {});

/**
 * One period boundary as a date. The end is exclusive, so the last day shown is the second before
 * it. A boundary on a UTC midnight (Taleem's calendar months, see ./generate.ts) is read in UTC so
 * "1 Sep – 1 Oct (exclusive)" shows as "1 Sep to 30 Sep" in every time zone; any other boundary (a
 * teacher's local days, "now") is read in the viewer's zone.
 */
function boundary(seconds: number, isEnd: boolean, c: ViewContext): string {
  const aligned = seconds % DAY === 0;
  const at = isEnd ? seconds - 1 : seconds;
  return formatDate(at, c.locale, aligned ? { timeZone: "UTC" } : c.timeZone ? { timeZone: c.timeZone } : {});
}

export function periodText(start: number, end: number, c: ViewContext): string {
  return c.t("common.reportCard.period", { start: boundary(start, false, c), end: boundary(Math.max(end, start + 1), true, c) });
}

/** Who issued the card, in words. */
export function issuerText(card: Pick<ReportCard, "isSystem" | "issuedByName" | "issuedAt">, c: ViewContext): string | null {
  if (card.issuedAt === null) return null;
  const on = date(card.issuedAt, c);
  if (card.isSystem) return c.t("common.reportCard.issuedBySystem", { date: on });
  return card.issuedByName
    ? c.t("common.reportCard.issuedBy", { name: card.issuedByName, date: on })
    : c.t("common.reportCard.issuedByTeacher", { date: on });
}

/** The whole card in two or three short lines; nothing at all when there is no evidence. */
export function totalsLines(totals: Totals | null, hasEvidence: boolean, c: ViewContext): string[] {
  if (!hasEvidence || !totals) return [];
  const lines: string[] = [];
  if (totals.objectives > 0)
    lines.push(c.t("common.reportCard.totalsTopics", { mastered: totals.objectivesMastered, objectives: totals.objectives }));
  if (totals.attempts > 0) lines.push(c.t("common.reportCard.practice", { attempts: totals.attempts, correct: totals.correct }));
  if (totals.homeworkMet + totals.homeworkNotYet > 0)
    lines.push(c.t("common.reportCard.homework", { met: totals.homeworkMet, notYet: totals.homeworkNotYet }));
  return lines;
}

export function objectiveView(o: ObjectiveResult, c: ViewContext): ObjectiveView {
  const practised = o.attempts > 0;
  const homework = o.homeworkMet + o.homeworkNotYet > 0;
  return {
    code: o.code,
    title: o.title,
    mastery: o.mastery,
    masteryLabel: c.t(MASTERY_META[o.mastery].labelKey),
    practice: practised ? c.t("common.reportCard.practice", { attempts: o.attempts, correct: o.correct }) : null,
    homework: homework ? c.t("common.reportCard.homework", { met: o.homeworkMet, notYet: o.homeworkNotYet }) : null,
    noPractice: !practised && !homework ? c.t("common.reportCard.noPractice") : null,
    pin: o.lessonId
      ? o.lessonVersion
        ? c.t("common.reportCard.pin", { lesson: o.lessonId, version: o.lessonVersion })
        : c.t("common.reportCard.pinNoVersion", { lesson: o.lessonId })
      : null,
  };
}

export function subjectView(s: SubjectResult, c: ViewContext): SubjectView {
  const tally = { mastered: 0, developing: 0, not_started: 0 };
  for (const o of s.objectives) tally[o.mastery]++;
  return {
    key: s.key,
    name: s.name?.text ?? s.key,
    nameText: s.name,
    summary: c.t("common.reportCard.summary", {
      mastered: tally.mastered,
      developing: tally.developing,
      notStarted: tally.not_started,
    }),
    objectives: s.objectives.map((o) => objectiveView(o, c)),
  };
}

export function cardView(card: ReportCard, c: ViewContext, opts: { supersededIds?: ReadonlySet<string> } = {}): CardView {
  const isPreview = card.status === "preview" || !card.cardId;
  const superseded =
    card.status === "superseded" || !!card.supersededBy || (!!card.cardId && !!opts.supersededIds?.has(card.cardId));
  return {
    cardId: card.cardId,
    learnerName: card.learnerName || c.t("common.reportCard.unnamedLearner"),
    className: card.className ? c.t("common.reportCard.className", { name: card.className }) : null,
    period: periodText(card.periodStart, card.periodEnd, c),
    issued: isPreview ? null : issuerText(card, c),
    isSystem: card.isSystem,
    totals: totalsLines(card.totals, card.hasEvidence, c),
    integrityWarning: card.hashVerified === false,
    isPreview,
    superseded,
    supersededBy: card.supersededBy,
    corrects: !!card.supersedes,
    hasEvidence: card.hasEvidence,
    // No evidence: no figures at all, so nothing can be read as a score of zero.
    subjects: card.hasEvidence ? card.subjects.map((s) => subjectView(s, c)) : [],
    comment: card.comment,
    commentBy:
      card.comment && !card.isSystem && card.issuedByName ? c.t("common.reportCard.commentBy", { name: card.issuedByName }) : null,
    curriculum: card.curriculumPack ? c.t("common.reportCard.curriculum", { pack: card.curriculumPack }) : null,
    reference:
      card.cardId || card.contentHash
        ? c.t("common.reportCard.reference", { id: card.cardId || "—", hash: card.contentHash.slice(0, 12) || "—" })
        : null,
  };
}

// ---- lists -------------------------------------------------------------------------------------------

/** Ids replaced by another card in the same list (in case `superseded_by` is not filled in). */
export function supersededIds(cards: readonly ReportCard[]): Set<string> {
  const ids = new Set<string>();
  for (const card of cards) {
    if (card.supersedes) ids.add(card.supersedes);
    if (card.supersededBy && card.cardId) ids.add(card.cardId);
  }
  return ids;
}

/** Newest first: by issue time, then period end, then id (stable). */
export function sortCards(cards: readonly ReportCard[]): ReportCard[] {
  return [...cards].sort(
    (a, b) =>
      (b.issuedAt ?? 0) - (a.issuedAt ?? 0) || b.periodEnd - a.periodEnd || a.cardId.localeCompare(b.cardId),
  );
}

export interface CardListItem {
  cardId: string;
  period: string;
  issued: string | null;
  superseded: boolean;
  seen: boolean;
  /** The server could not re-verify this card. */
  unverified: boolean;
}

export function cardListView(cards: readonly ReportCard[], c: ViewContext): CardListItem[] {
  const replaced = supersededIds(cards);
  return sortCards(cards)
    .filter((card) => card.cardId)
    .map((card) => {
      const view = cardView(card, c, { supersededIds: replaced });
      return {
        cardId: card.cardId,
        period: view.period,
        issued: view.issued,
        superseded: view.superseded,
        seen: card.acknowledgedAt !== null,
        unverified: view.integrityWarning,
      };
    });
}

// ---- "I have seen this" (guardian, once) --------------------------------------------------------------

export type AckState =
  | { status: "unseen" }
  | { status: "sending" }
  | { status: "seen"; at: number; justNow: boolean }
  | { status: "failed"; error: MessageKey };

export type AckAction =
  | { type: "loaded"; state: AckState }
  | { type: "send" } | { type: "done"; at: number } | { type: "failed"; error: unknown; now: number };

export function initialAck(card: Pick<ReportCard, "acknowledgedAt">): AckState {
  return card.acknowledgedAt !== null ? { status: "seen", at: card.acknowledgedAt, justNow: false } : { status: "unseen" };
}

/** Only an unseen card (or one whose send failed) may send; never twice, never while sending. */
export function canAcknowledge(state: AckState): boolean {
  return state.status === "unseen" || state.status === "failed";
}

export function ackReducer(state: AckState, action: AckAction): AckState {
  switch (action.type) {
    case "loaded":
      return action.state;
    case "send":
      return canAcknowledge(state) ? { status: "sending" } : state;
    case "done":
      return state.status === "seen" ? state : { status: "seen", at: action.at, justNow: true };
    case "failed": {
      if (state.status === "seen") return state;
      // 409 ALREADY_ACKNOWLEDGED (a second tap from another device): that is "seen", not an error.
      if (action.error instanceof ApiError && action.error.status === 409) return { status: "seen", at: action.now, justNow: true };
      const offline = action.error instanceof ApiError && action.error.status === 0;
      return { status: "failed", error: offline ? "common.reportCard.ackOffline" : "common.reportCard.ackFailed" };
    }
  }
}

/** The time the server recorded, or `fallback` when it answered with no body. */
export function acknowledgedAt(body: { acknowledged_at?: number | null } | undefined, fallback: number): number {
  return typeof body?.acknowledged_at === "number" ? body.acknowledged_at : fallback;
}

/** Superseded cards are not acknowledged: the guardian is pointed at the newer one instead. */
export function showAcknowledge(view: Pick<CardView, "superseded" | "isPreview">): boolean {
  return !view.superseded && !view.isPreview;
}

// ---- the guardian's feed --------------------------------------------------------------------------

/** "New report card" / "New report cards: 3" on the child page; null when nothing is unread. */
export function feedBadge(f: Feed | null, t: Translator): string | null {
  if (!f || f.unread <= 0) return null;
  return f.unread === 1 ? t("guardian.child.newReportOne") : t("guardian.child.newReportMany", { count: f.unread });
}

// ---- reads -------------------------------------------------------------------------------------------

export type ReadFailure = "offline" | "signed-out" | "not-available" | "consent" | "error";

/** A failed report-card read. 403/404 read the same ("not available"), so nothing is revealed. */
export function readFailure(error: unknown): ReadFailure {
  if (!(error instanceof ApiError)) return "error";
  if (error.status === 0) return "offline";
  if (error.status === 401) return "signed-out";
  if (error.status === 403 && error.problem.code === "CONSENT_REQUIRED") return "consent";
  if (error.status === 403 || error.status === 404) return "not-available";
  return "error";
}

/** Subject and objective names for the reader: the interface language first, then the other. */
export function namePreference(locale: Locale): readonly string[] {
  return locale === "ur" ? ["ur", "en"] : ["en", "ur"];
}
