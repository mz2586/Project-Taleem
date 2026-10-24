// Teacher issuing view model (REPORT_CARD_CONTRACT.md §2). Pure and unit-tested; the page renders it.
//
// - The period is two date inputs. `period_start` is the start of the first day; `period_end` is
//   EXCLUSIVE (`period_rule: start_inclusive_end_exclusive`): the start of the day after the last
//   day — or "now" when the last day is today, because the server refuses a `period_end` in the
//   future. A last day after today is refused here first, with a plain message.
// - Issue sends exactly the learners that were previewed (so a learner who joined since the preview
//   is not issued a card the teacher never looked at), each with an optional comment of at most
//   1000 characters and an optional card it supersedes (a correction).
// - A correction names the card the server reported in `skipped` (`already_issued` + `card_id`);
//   the preview is re-run with that `supersedes`, so the teacher sees the replacement before issuing.

import type { MessageKey } from "../i18n/messages";
import { ApiError } from "../student/types";
import { localDateInput } from "../teacher/assignments";
import { teacherFailure } from "../teacher/errors";
import type { IssueBody, PreviewBody } from "./types";
import type { Skipped, SkipReason } from "./wire";

export const COMMENT_MAX = 1000;
const DAY = 24 * 60 * 60;

const length = (text: string) => Array.from(text).length;

// ---- the period ----------------------------------------------------------------------------------------

export interface PeriodInputs {
  start: string;
  end: string;
}

/** Default: the last three months, ending today (roughly one school term). */
export function defaultPeriod(nowSeconds: number): PeriodInputs {
  const now = new Date(nowSeconds * 1000);
  const start = new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
  // 31 May minus three months is "31 Feb" → rolls into March; clamp to the month's last day instead.
  if (start.getMonth() !== (((now.getMonth() - 3) % 12) + 12) % 12) start.setDate(0);
  return { start: localDateInput(Math.floor(start.getTime() / 1000)), end: localDateInput(nowSeconds) };
}

function parseDay(value: string): { y: number; m: number; d: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const [y, m, d] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const check = new Date(y, m - 1, d);
  if (check.getFullYear() !== y || check.getMonth() !== m - 1 || check.getDate() !== d) return null;
  return { y, m, d };
}

export type Period =
  | { ok: true; periodStart: number; periodEnd: number }
  | { ok: false; problems: { start?: MessageKey; end?: MessageKey } };

export function periodFromInputs(inputs: PeriodInputs, nowSeconds: number): Period {
  const problems: { start?: MessageKey; end?: MessageKey } = {};
  const s = inputs.start.trim() ? parseDay(inputs.start) : null;
  const e = inputs.end.trim() ? parseDay(inputs.end) : null;
  if (!inputs.start.trim()) problems.start = "teacher.reportCards.startEmpty";
  else if (!s) problems.start = "teacher.reportCards.dateInvalid";
  if (!inputs.end.trim()) problems.end = "teacher.reportCards.endEmpty";
  else if (!e) problems.end = "teacher.reportCards.dateInvalid";
  if (!s || !e) return { ok: false, problems };

  const periodStart = Math.floor(new Date(s.y, s.m - 1, s.d).getTime() / 1000);
  const startOfEndDay = Math.floor(new Date(e.y, e.m - 1, e.d).getTime() / 1000);
  if (startOfEndDay > nowSeconds) return { ok: false, problems: { end: "teacher.reportCards.endFuture" } };
  // Exclusive end: the first second of the next day (Date handles month ends and DST).
  const nextDay = Math.floor(new Date(e.y, e.m - 1, e.d + 1).getTime() / 1000);
  const periodEnd = Math.min(nextDay, nowSeconds);
  if (periodStart >= periodEnd) return { ok: false, problems: { start: "teacher.reportCards.order" } };
  return { ok: true, periodStart, periodEnd };
}

/** Roughly how many days a period covers — for the confirm step's sanity check. */
export function periodDays(periodStart: number, periodEnd: number): number {
  return Math.max(1, Math.round((periodEnd - periodStart) / DAY));
}

// ---- comments ------------------------------------------------------------------------------------------

export function commentLength(text: string): number {
  return length(text.trim());
}

export function commentProblem(text: string): MessageKey | null {
  return commentLength(text) > COMMENT_MAX ? "teacher.reportCards.commentTooLong" : null;
}

// ---- bodies ----------------------------------------------------------------------------------------------

/**
 * The whole class (no `student_refs`) unless learners are named. Corrections ride along so the
 * preview already shows the replacing card instead of skipping the learner as `already_issued`.
 */
export function previewBody(
  period: { periodStart: number; periodEnd: number },
  studentRefs?: readonly string[],
  supersedes?: Readonly<Record<string, string>>,
): PreviewBody {
  const body: PreviewBody = { period_start: period.periodStart, period_end: period.periodEnd };
  if (studentRefs && studentRefs.length > 0) body.student_refs = [...studentRefs];
  const wanted = Object.entries(supersedes ?? {}).filter(([ref, id]) => ref && id.trim());
  if (wanted.length > 0) body.supersedes = Object.fromEntries(wanted.map(([ref, id]) => [ref, id.trim()]));
  return body;
}

export interface IssueDraft {
  periodStart: number;
  periodEnd: number;
  /** The learners in the preview the teacher looked at. */
  studentRefs: readonly string[];
  comments: Readonly<Record<string, string>>;
  supersedes: Readonly<Record<string, string>>;
}

export type IssueBuild = { ok: true; body: IssueBody } | { ok: false; problem: MessageKey; studentRef?: string };

export function issueBody(draft: IssueDraft): IssueBuild {
  if (draft.studentRefs.length === 0) return { ok: false, problem: "teacher.reportCards.nothingToIssue" };
  const refs = new Set(draft.studentRefs);
  const comments: Record<string, string> = {};
  for (const [ref, raw] of Object.entries(draft.comments)) {
    if (!refs.has(ref)) continue;
    const problem = commentProblem(raw);
    if (problem) return { ok: false, problem, studentRef: ref };
    const text = raw.trim();
    if (text) comments[ref] = text;
  }
  const supersedes: Record<string, string> = {};
  for (const [ref, cardId] of Object.entries(draft.supersedes)) {
    if (refs.has(ref) && cardId.trim()) supersedes[ref] = cardId.trim();
  }
  const body: IssueBody = {
    period_start: draft.periodStart,
    period_end: draft.periodEnd,
    student_refs: [...draft.studentRefs],
  };
  if (Object.keys(comments).length > 0) body.comments = comments;
  if (Object.keys(supersedes).length > 0) body.supersedes = supersedes;
  return { ok: true, body };
}

// ---- skipped learners and errors ---------------------------------------------------------------------------

/** The server's exact reason codes, each in plain words (wire.ts maps anything else to "other"). */
export const SKIP_REASON_KEYS: Record<SkipReason, MessageKey> = {
  consent_withdrawn: "teacher.reportCards.skipped.consentWithdrawn",
  inactive: "teacher.reportCards.skipped.inactive",
  not_in_class: "teacher.reportCards.skipped.notInClass",
  already_issued: "teacher.reportCards.skipped.alreadyIssued",
  other: "teacher.reportCards.skipped.other",
};

export function skippedReasonKey(reason: SkipReason): MessageKey {
  return SKIP_REASON_KEYS[reason];
}

export interface SkippedRow extends Skipped {
  reasonKey: MessageKey;
  /** `already_issued` with a card id: the teacher may correct (supersede) that card. */
  canCorrect: boolean;
}

export function skippedRows(list: readonly Skipped[]): SkippedRow[] {
  return list.map((s) => ({
    ...s,
    reasonKey: skippedReasonKey(s.reason),
    canCorrect: s.reason === "already_issued" && !!s.cardId,
  }));
}

export function issueErrorKey(error: unknown): MessageKey {
  if (!(error instanceof ApiError)) return "teacher.errors.generic";
  if (error.status === 422) return "teacher.reportCards.periodRejected";
  // 409 ALREADY_SUPERSEDED: the card chosen for correction was replaced meanwhile.
  if (error.status === 409) return "teacher.reportCards.supersedeConflict";
  switch (teacherFailure(error)) {
    case "offline":
      return "teacher.errors.offline";
    case "signed-out":
      return "teacher.errors.signedOut";
    case "inactive":
      return "teacher.errors.inactive";
    case "not-available":
      return "teacher.errors.notAvailable";
    default:
      return error.status === 429 ? "teacher.errors.tooMany" : "teacher.errors.generic";
  }
}
