// Normalising the report-card wire into plain values. Pure. Every tolerance for an open field
// spelling in the contract lives here (see ./types.ts), so the view models never touch wire objects.
//
// Honesty rules applied at the edge: an unknown mastery state reads as "not started" (never as
// mastered); a missing count is 0 but `hasEvidence` is decided from the server's flag (and the
// `no_evidence_in_period` notice always wins), falling back to "is there any attempt or homework at
// all" only when both are absent; `hashVerified` is `false` only when the server said so.

import { pickLocalized, type LocalizedText } from "../i18n/content";
import {
  SYSTEM_ISSUER,
  type IssueResultWire,
  type LocalizedWire,
  type Mastery,
  type NotificationListWire,
  type NotificationWire,
  type ObjectiveWire,
  type ReportCardListWire,
  type ReportCardWire,
  type SkippedWire,
  type SkipReasonWire,
  type SubjectWire,
  type TotalsWire,
} from "./types";

export interface ObjectiveResult {
  code: string;
  title: LocalizedText | null;
  mastery: Mastery;
  attempts: number;
  correct: number;
  homeworkMet: number;
  homeworkNotYet: number;
  lessonId: string | null;
  lessonVersion: string | null;
}

export interface SubjectResult {
  key: string;
  name: LocalizedText | null;
  objectives: ObjectiveResult[];
}

export interface Totals {
  objectives: number;
  objectivesMastered: number;
  attempts: number;
  correct: number;
  homeworkMet: number;
  homeworkNotYet: number;
}

export type CardStatus = "issued" | "superseded" | "preview";

export interface ReportCard {
  /** Empty on a preview (nothing is stored yet). */
  cardId: string;
  studentRef: string;
  learnerName: string;
  /** Empty on a system card (no class needed). */
  classId: string;
  className: string;
  organizationName: string;
  periodStart: number;
  /** Exclusive. */
  periodEnd: number;
  issuedAt: number | null;
  /** `"system"` or a teacher ref. */
  issuedBy: string;
  /** Issued by Taleem itself, not by a teacher. */
  isSystem: boolean;
  issuedByName: string;
  status: CardStatus;
  /** Teacher-issued cards only. */
  comment: string | null;
  supersedes: string | null;
  supersededBy: string | null;
  acknowledgedAt: number | null;
  contentHash: string;
  curriculumPack: string;
  hasEvidence: boolean;
  /** Null when the card has no evidence (or the server sent none). */
  totals: Totals | null;
  /** `false` only when the server re-checked the hash and it did not match. */
  hashVerified: boolean | null;
  subjects: SubjectResult[];
}

/** The server's skip reasons; anything else reads as "other" (never guessed from its wording). */
export type SkipReason = SkipReasonWire | "other";

export interface Skipped {
  studentRef: string;
  /** Empty when the server hid the name. */
  learnerName: string;
  reason: SkipReason;
  /** For `already_issued`: the current card a correction must name. */
  cardId: string | null;
}

export const NO_EVIDENCE_NOTICE = "no_evidence_in_period";
const SKIP_REASONS: readonly SkipReasonWire[] = ["consent_withdrawn", "inactive", "not_in_class", "already_issued"];

const MASTERY: readonly Mastery[] = ["mastered", "developing", "not_started"];

/** One rendition of authored text. A plain string carries no declared locale (direction is read from it). */
export function localized(value: LocalizedWire | null | undefined, preference: readonly string[]): LocalizedText | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.trim() ? { text: value, locale: "" } : null;
  return pickLocalized(value, preference);
}

const count = (n: unknown): number => (typeof n === "number" && Number.isFinite(n) && n > 0 ? Math.floor(n) : 0);
const text = (s: unknown): string => (typeof s === "string" ? s.trim() : "");
const orNull = (s: unknown): string | null => text(s) || null;

export function masteryOf(raw: unknown): Mastery {
  // "in_progress" is the learning service's word for the same state.
  if (raw === "in_progress") return "developing";
  return MASTERY.includes(raw as Mastery) ? (raw as Mastery) : "not_started";
}

function objective(o: ObjectiveWire, preference: readonly string[]): ObjectiveResult {
  const attempts = count(o.attempts);
  const version = o.lesson_version;
  return {
    code: text(o.objective_code),
    title: localized(o.title, preference),
    mastery: masteryOf(o.mastery),
    attempts,
    // Never more right than tried.
    correct: Math.min(count(o.correct), attempts),
    homeworkMet: count(o.homework_met),
    homeworkNotYet: count(o.homework_not_yet),
    lessonId: orNull(o.lesson_id),
    lessonVersion: version === null || version === undefined || String(version).trim() === "" ? null : String(version).trim(),
  };
}

function subject(s: SubjectWire, preference: readonly string[]): SubjectResult {
  return {
    key: text(s.subject_key),
    name: localized(s.subject_name, preference),
    objectives: (s.objectives ?? []).map((o) => objective(o, preference)),
  };
}

function totals(w: TotalsWire | null | undefined): Totals | null {
  if (!w || typeof w !== "object") return null;
  const attempts = count(w.attempts);
  const objectives = count(w.objectives);
  return {
    objectives,
    objectivesMastered: Math.min(count(w.objectives_mastered), objectives),
    attempts,
    correct: Math.min(count(w.correct), attempts),
    homeworkMet: count(w.homework_met),
    homeworkNotYet: count(w.homework_not_yet),
  };
}

function statusOf(raw: unknown, cardId: string, supersededBy: string | null): CardStatus {
  if (raw === "issued" || raw === "superseded" || raw === "preview") return raw;
  if (!cardId) return "preview";
  return supersededBy ? "superseded" : "issued";
}

export function reportCard(wire: ReportCardWire, preference: readonly string[]): ReportCard {
  const subjects = (wire.subjects ?? []).map((s) => subject(s, preference));
  const anyEvidence = subjects.some((s) => s.objectives.some((o) => o.attempts + o.homeworkMet + o.homeworkNotYet > 0));
  const noticeSaysNone = wire.notice === NO_EVIDENCE_NOTICE;
  const hasEvidence = noticeSaysNone ? false : typeof wire.has_evidence === "boolean" ? wire.has_evidence : anyEvidence;
  const cardId = text(wire.card_id);
  const supersededBy = orNull(wire.superseded_by);
  const issuedBy = text(wire.issued_by);
  return {
    cardId,
    studentRef: text(wire.student_ref),
    learnerName: text(wire.learner_display_name) || text(wire.display_name),
    classId: text(wire.class_id),
    className: text(wire.class_name),
    organizationName: text(wire.organization_name),
    periodStart: wire.period_start,
    periodEnd: wire.period_end,
    issuedAt: typeof wire.issued_at === "number" ? wire.issued_at : null,
    issuedBy,
    isSystem: issuedBy === SYSTEM_ISSUER,
    issuedByName: text(wire.issued_by_name),
    status: statusOf(wire.status, cardId, supersededBy),
    // Only a teacher writes a note; a system card never shows one.
    comment: issuedBy === SYSTEM_ISSUER ? null : orNull(wire.comment),
    supersedes: orNull(wire.supersedes),
    supersededBy,
    acknowledgedAt: typeof wire.acknowledged_at === "number" ? wire.acknowledged_at : null,
    contentHash: text(wire.content_hash),
    curriculumPack: text(wire.curriculum_pack),
    hasEvidence,
    totals: hasEvidence ? totals(wire.totals) : null,
    hashVerified: typeof wire.hash_verified === "boolean" ? wire.hash_verified : null,
    subjects,
  };
}

export function cardList(wire: ReportCardListWire | null | undefined): ReportCardWire[] {
  if (!wire) return [];
  if (Array.isArray(wire)) return wire;
  return wire.report_cards ?? wire.cards ?? [];
}

/** The bodies in a :preview or issue answer, whichever key the server used. */
export function resultCards(wire: IssueResultWire | null | undefined): ReportCardWire[] {
  if (!wire) return [];
  return wire.report_cards ?? wire.issued ?? wire.previews ?? wire.cards ?? [];
}

export function skipReason(raw: unknown): SkipReason {
  return SKIP_REASONS.includes(raw as SkipReasonWire) ? (raw as SkipReasonWire) : "other";
}

export function skipped(wire: IssueResultWire | null | undefined): Skipped[] {
  return (wire?.skipped ?? []).map((s: SkippedWire) => {
    const reason = skipReason(s.reason);
    return {
      studentRef: text(s.student_ref),
      learnerName: text(s.learner_display_name) || text(s.display_name),
      reason,
      cardId: reason === "already_issued" ? orNull(s.card_id) : null,
    };
  });
}

// ---- the guardian's in-app feed ------------------------------------------------------------------

export interface FeedItem {
  cardId: string;
  periodStart: number | null;
  periodEnd: number | null;
  issuedAt: number | null;
  read: boolean;
}

export interface Feed {
  items: FeedItem[];
  /** How many current cards the guardian has not acknowledged yet. */
  unread: number;
}

/**
 * `{notifications, unread}` (tolerated: a bare array). Entries without a card id are dropped.
 * `unread` is counted from the entries when the server leaves it out, and is never more than the
 * entries it describes.
 */
export function feed(wire: NotificationListWire | null | undefined): Feed {
  const list: NotificationWire[] = !wire ? [] : Array.isArray(wire) ? wire : (wire.notifications ?? []);
  const items = list
    .filter((n) => n && text(n.card_id) && (n.kind === undefined || n.kind === null || n.kind === "report_card_issued"))
    .map((n) => ({
      cardId: text(n.card_id),
      periodStart: typeof n.period_start === "number" ? n.period_start : null,
      periodEnd: typeof n.period_end === "number" ? n.period_end : null,
      issuedAt: typeof n.issued_at === "number" ? n.issued_at : null,
      read: n.read === true,
    }));
  const counted = items.filter((i) => !i.read).length;
  const stated = !wire || Array.isArray(wire) ? null : wire.unread;
  const unread = typeof stated === "number" && Number.isFinite(stated) ? Math.min(count(stated), items.length || count(stated)) : counted;
  return { items, unread };
}
