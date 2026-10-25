// View-model for the safeguarding console and for a guardian's own list. Pure; unit-tested.
//
// The server decides who may see what; these functions only arrange what it returned: queue order,
// age, the SLA banner (never a number the server did not send), which actions a status allows, and
// the coarse status words a guardian sees.

import type { MessageKey } from "../i18n/messages";
import type { Category, Priority } from "./categories";

export type Status = "open" | "acknowledged" | "escalated" | "resolved";
export type Outcome = "no_further_action" | "support_given" | "referred_externally" | "duplicate";
export type GuardianStatus = "received" | "in_review" | "closed";

export interface SlaWire {
  configured: boolean;
  acknowledge_within_seconds: Partial<Record<Priority, number | null>>;
  notice: string | null;
}

export interface ConcernSummaryWire {
  concern_id: string;
  subject_ref: string;
  raised_by_role: "student" | "guardian" | "teacher" | "system";
  category: Category;
  priority: Priority;
  status: Status;
  created_at: number;
  age_seconds: number;
  overdue: boolean | null;
  has_text: boolean;
  context: { screen: string; lesson_id: string | null; submission_id?: string | null };
}

export interface QueueWire {
  generated_at: number;
  sla: SlaWire;
  concerns: ConcernSummaryWire[];
}

export interface NoteWire {
  note_id: string;
  author_ref: string;
  body: string;
  created_at: number;
}

export interface AuditWire {
  action: string;
  actor_ref: string;
  actor_role: string;
  at: number;
  detail: Record<string, string>;
}

export interface ConcernDetailWire extends ConcernSummaryWire {
  text: string | null;
  raised_by_ref: string;
  outcome: Outcome | null;
  external_referral_needed: boolean;
  guardian_informed: boolean;
  household_caution: boolean;
  notes: NoteWire[];
  audit: AuditWire[];
  contacted: string[];
  contact_notice: string;
}

export interface GuardianConcernWire {
  concern_id: string;
  student_ref: string;
  category: Category;
  text: string | null;
  raised_at: number;
  status: GuardianStatus;
}

const RANK: Record<Priority, number> = { T1: 1, T2: 2, T3: 3 };

/** Highest priority first; oldest first within a priority (the server's order, re-asserted). */
export function sortQueue<T extends Pick<ConcernSummaryWire, "priority" | "created_at" | "concern_id">>(
  concerns: readonly T[],
): T[] {
  return [...concerns].sort(
    (a, b) =>
      (RANK[a.priority] ?? 9) - (RANK[b.priority] ?? 9) ||
      a.created_at - b.created_at ||
      a.concern_id.localeCompare(b.concern_id),
  );
}

export interface AgeLabel {
  key: MessageKey;
  params: { n: number };
}

/** "just now" under a minute, then whole minutes, hours, days (floored — never rounded down to 0). */
export function ageLabel(seconds: number): AgeLabel {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return { key: "safeguarding.console.age.justNow", params: { n: 0 } };
  if (s < 3600) return { key: "safeguarding.console.age.minutes", params: { n: Math.floor(s / 60) } };
  if (s < 86_400) return { key: "safeguarding.console.age.hours", params: { n: Math.floor(s / 3600) } };
  return { key: "safeguarding.console.age.days", params: { n: Math.floor(s / 86_400) } };
}

export type SlaBanner =
  | { kind: "unset"; key: MessageKey; bodyKey: MessageKey }
  | { kind: "partial"; key: MessageKey; bodyKey: MessageKey; thresholds: Array<{ priority: Priority; seconds: number }> }
  | { kind: "set"; thresholds: Array<{ priority: Priority; seconds: number }> };

/** The SLA banner. Anything short of a threshold for every tier still shows "not set — FD-06". */
export function slaBanner(sla: SlaWire): SlaBanner {
  const thresholds = (["T1", "T2", "T3"] as const)
    .map((priority) => ({ priority, seconds: sla.acknowledge_within_seconds[priority] ?? null }))
    .filter((t): t is { priority: Priority; seconds: number } => typeof t.seconds === "number");
  if (thresholds.length === 0 || !sla.configured) {
    return { kind: "unset", key: "safeguarding.console.slaNotSet", bodyKey: "safeguarding.console.slaNotSetBody" };
  }
  if (thresholds.length < 3 || sla.notice) {
    return {
      kind: "partial",
      key: "safeguarding.console.slaNotSet",
      bodyKey: "safeguarding.console.slaPartialBody",
      thresholds,
    };
  }
  return { kind: "set", thresholds };
}

/** "T1 30 min, T2 4 h" — only the thresholds the server sent, in the interface language. */
export function thresholdText(
  banner: SlaBanner,
  t: (key: MessageKey, params?: Record<string, string | number>) => string,
): string {
  if (banner.kind === "unset") return "";
  return banner.thresholds
    .map(({ priority, seconds }) => {
      const age = ageLabel(seconds);
      return `${priority} ${t(age.key, age.params)}`;
    })
    .join(", ");
}

export function overdueKey(overdue: boolean | null): MessageKey {
  if (overdue === null) return "safeguarding.console.overdue.unknown";
  return overdue ? "safeguarding.console.overdue.yes" : "safeguarding.console.overdue.no";
}

export interface AllowedActions {
  acknowledge: boolean;
  note: boolean;
  escalate: boolean;
  resolve: boolean;
}

export function allowedActions(status: Status): AllowedActions {
  const live = status !== "resolved";
  return {
    acknowledge: status === "open",
    note: live,
    escalate: live && status !== "escalated",
    resolve: live,
  };
}

/** Outcomes a lead may choose now: "referred externally" only after a recorded escalation. */
export function outcomeOptions(status: Status): Outcome[] {
  const base: Outcome[] = ["no_further_action", "support_given", "duplicate"];
  return status === "escalated" ? ["referred_externally", ...base] : base;
}

export function statusKey(status: Status): MessageKey {
  return `safeguarding.console.status.${status}` as MessageKey;
}

export function guardianStatusKey(status: GuardianStatus): MessageKey {
  return `safeguarding.guardian.status.${status}` as MessageKey;
}

export function outcomeKey(outcome: Outcome): MessageKey {
  return `safeguarding.console.outcomes.${outcome}` as MessageKey;
}

/** A guardian's failed send: offline, a learner not in their family (404), or anything else. */
export function guardianErrorKey(error: unknown): MessageKey {
  const status = (error as { status?: unknown } | null)?.status;
  if (status === 0) return "safeguarding.guardian.errors.offline";
  if (status === 404) return "safeguarding.guardian.errors.notFound";
  return "safeguarding.guardian.errors.generic";
}

/** A concern's action error, as a catalog key: a lost race, a closed concern, or a refusal. */
export function actionErrorKey(error: unknown): MessageKey {
  const status = (error as { status?: unknown } | null)?.status;
  const code = (error as { problem?: { code?: unknown } } | null)?.problem?.code;
  if (status === 0) return "safeguarding.console.offline";
  if (status === 409 && (code === "CONCERN_CLOSED" || code === "CONCERN_NOT_ESCALATED")) {
    return "safeguarding.console.detail.notAllowed";
  }
  if (status === 409) return "safeguarding.console.detail.conflict";
  if (status === 403) return "safeguarding.console.denied";
  return "safeguarding.console.detail.refused";
}

// ------------------------------------------------------------- the flagged homework behind a concern

export interface MatchedPhraseWire {
  phrase_id: string;
  lang: string;
  category: Category;
  phrase: string;
}

/** GET /v1/safeguarding/concerns/{id}/context — safeguarding lead only; every read is audited. */
export interface ConcernContextWire {
  concern_id: string;
  submission: {
    submission_id: string;
    source: "assignment" | "self_paced";
    objective_code: string;
    item_ref: string;
    text: string;
    attempt: number;
    submitted_at: number;
    item_prompt: Record<string, string>;
    lesson_title: Record<string, string>;
  };
  matched_phrases: MatchedPhraseWire[];
  resubmitted_since_raised: boolean;
  read_recorded: boolean;
  notice?: string;
}

export interface FlaggedWorkView {
  text: string;
  lessonTitle: string | null;
  prompt: string | null;
  submittedAt: number;
  attempt: number;
  matched: { id: string; phrase: string; lang: string }[];
  resubmitted: boolean;
}

/** The concern names a homework submission, so there is flagged work the lead may open. */
export function hasFlaggedWork(concern: Pick<ConcernSummaryWire, "context">): boolean {
  return typeof concern.context.submission_id === "string" && concern.context.submission_id !== "";
}

/** A localised string map in the reader's locale, else Urdu, else English, else any; null if empty. */
export function pickLocalised(map: Record<string, string> | null | undefined, locale: string): string | null {
  if (!map) return null;
  for (const key of [locale, "ur", "en"]) {
    const v = map[key];
    if (typeof v === "string" && v.trim()) return v;
  }
  const any = Object.values(map).find((v) => typeof v === "string" && v.trim());
  return any ?? null;
}

export function flaggedWorkView(wire: ConcernContextWire, locale: string): FlaggedWorkView {
  return {
    text: wire.submission.text,
    lessonTitle: pickLocalised(wire.submission.lesson_title, locale),
    prompt: pickLocalised(wire.submission.item_prompt, locale),
    submittedAt: wire.submission.submitted_at,
    attempt: wire.submission.attempt,
    matched: wire.matched_phrases.map((m) => ({ id: m.phrase_id, phrase: m.phrase, lang: m.lang })),
    resubmitted: wire.resubmitted_since_raised,
  };
}

/** A failed read: 404 means there is no answer to read (none named, or erased). */
export function flaggedWorkErrorKey(error: unknown): MessageKey {
  const status = (error as { status?: unknown } | null)?.status;
  if (status === 404) return "safeguarding.console.detail.flagged.gone";
  return actionErrorKey(error);
}
