// Student journey states — the pure rules for what Today and the session screen say when there is
// nothing (or nothing yet) to do, and how a failed load is described. No React; unit-tested.
//
// What the backend actually returns when no lesson is published (verified against core-api):
//   - `:next` -> `{decision: "complete", objective_code: null}`. The planner's last rule is "no
//     eligible objective remains", and with an empty published graph that is reached immediately —
//     so the same `complete` means both "you mastered everything" and "there is nothing to learn".
//     The old session screen showed "You did great today! 🎉" to a child who had learned nothing.
//   - `GET /students/{ref}/today` -> `next_action.reason: "complete"`, `mastery_summary.total: 0`.
//     That pair is how the two meanings are told apart: complete with nothing ever learned is "no
//     lessons yet"; complete with recorded objectives is "all caught up".
//   - `GET /students/{ref}/knowledge` -> 404 for a learner with no recorded knowledge yet. That is a
//     new learner, not a failure; the old Today screen showed every new child an error banner.
//   - `:teach` -> 404 when the chosen objective's lesson is no longer published.

import type { MessageKey } from "../i18n/messages";
import {
  ApiError,
  type DecisionView,
  type KnowledgeView,
  type ObjectiveKnowledge,
  type ProgressView,
  type TodayView,
} from "./types";

// ---- load failures ----------------------------------------------------------------------------

export type LoadFailure = "offline" | "signed-out" | "consent" | "paused" | "error";

/**
 * How to describe a failed request. Only a network failure is "offline": a 401 that survived the
 * session refresh means the session is gone (the guard will redirect), and anything else is an
 * error. Earlier screens called every 401/403 "offline", which told a signed-out child to find wifi.
 */
export function classifyLoadError(error: unknown): LoadFailure {
  if (error instanceof ApiError) {
    if (error.status === 0) return "offline";
    if (error.status === 401) return "signed-out";
    // The per-request learner gate: a guardian withdrew consent, or paused the child. Neither is
    // an error the child can retry away, so each gets its own honest message (no Retry button).
    if (error.status === 403 && error.problem.code === "CONSENT_REQUIRED") return "consent";
    if (error.status === 403 && error.problem.code === "LEARNER_INACTIVE") return "paused";
  }
  return "error";
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

/** Await `request`, substituting `fallback` for a 404 only. Every other failure still rejects. */
export async function orOnNotFound<T>(request: Promise<T>, fallback: T): Promise<T> {
  try {
    return await request;
  } catch (error) {
    if (isNotFound(error)) return fallback;
    throw error;
  }
}

export function emptyKnowledge(studentRef: string): KnowledgeView {
  return { student_ref: studentRef, objectives: {} };
}

// ---- Today ------------------------------------------------------------------------------------

export type TodayKind =
  /** Nothing has been published: no lesson exists to start. */
  | "nothing-published"
  /** Lessons exist; this learner has not started one. */
  | "first-lesson"
  /** Under way. */
  | "learning"
  /** Every available objective is done and nothing is due. */
  | "all-caught-up";

export interface TodayModel {
  kind: TodayKind;
  /** Whether the Start action leads anywhere. Never offer a button that ends in an empty session. */
  canStart: boolean;
  mastered: number;
  total: number;
  dueCount: number;
  /** 0..1, for the mastery ring. */
  masteryValue: number;
  /** 0..1, or null before any question has been answered (an accuracy of "0%" would be a lie). */
  accuracy: number | null;
  objectives: [string, ObjectiveKnowledge][];
}

const REVIEW_STATES = new Set(["needs_review", "at_risk"]);

export function todayModel(input: {
  today: TodayView | null;
  knowledge: KnowledgeView | null;
  progress: ProgressView | null;
}): TodayModel {
  const objectives = input.knowledge ? Object.entries(input.knowledge.objectives) : [];
  const total = Math.max(objectives.length, input.today?.mastery_summary.total ?? 0);
  const mastered = objectives.length
    ? objectives.filter(([, o]) => o.state === "mastered").length
    : (input.today?.mastery_summary.mastered ?? 0);
  const dueFromKnowledge = objectives.filter(([, o]) => REVIEW_STATES.has(o.state)).length;
  const dueCount = Math.max(dueFromKnowledge, input.today?.revision_due_count ?? 0);

  let kind: TodayKind;
  if (input.today?.next_action.reason === "complete") {
    kind = total === 0 ? "nothing-published" : "all-caught-up";
  } else {
    // Without the aggregate (an older server) the only safe reading is that there is something to
    // start; the session screen then says honestly if there is not.
    kind = total === 0 ? "first-lesson" : "learning";
  }

  const progress = input.progress;
  return {
    kind,
    canStart: kind === "first-lesson" || kind === "learning",
    mastered,
    total,
    dueCount,
    masteryValue: total > 0 ? mastered / total : 0,
    accuracy: progress && progress.total_attempts > 0 ? progress.accuracy : null,
    objectives,
  };
}

export const TODAY_EMPTY_COPY: Record<
  Exclude<TodayKind, "learning">,
  { title: MessageKey; body: MessageKey }
> = {
  "nothing-published": { title: "student.today.nothingTitle", body: "student.today.nothingBody" },
  "first-lesson": { title: "student.today.firstTitle", body: "student.today.firstBody" },
  "all-caught-up": { title: "student.today.allDoneTitle", body: "student.today.allDoneBody" },
};

// ---- the session: what the planner's decision means ------------------------------------------

/** Decisions the player turns into a lesson (`:teach`). Unchanged from the original page. */
export const TEACHABLE_DECISIONS: ReadonlySet<string> = new Set([
  "teach",
  "continue",
  "review",
  "remediate",
  "diagnose",
]);

export type SessionEnding =
  /** At least one lesson was taught this session: the normal, celebrated end. */
  | "finished"
  /** The planner asked for a break. */
  | "rest"
  /** No lesson was taught and nothing has ever been learned: nothing is published yet. */
  | "nothing-to-learn"
  /** No lesson was taught and the learner has done everything available. */
  | "all-mastered"
  /** No lesson was taught and we could not tell which of the two above applies. */
  | "caught-up"
  /** The chosen objective's lesson is not (or no longer) published. */
  | "unavailable";

export type PlanOutcome =
  | { kind: "teach"; objective: string }
  | { kind: "escalate" }
  | { kind: "end"; ending: SessionEnding };

/**
 * Turn a `:next` decision into what the player does. Teach and escalate behave exactly as before;
 * the difference is that an end is now described truthfully instead of always as a success.
 *
 * `taughtThisSession` is whether a lesson has already been presented in this session (the player's
 * `teach` is non-null). `today` is the dashboard aggregate, fetched only to disambiguate an end that
 * came before any lesson; null when unavailable.
 */
export function planOutcome(
  decision: DecisionView,
  context: { taughtThisSession: boolean; today?: TodayView | null },
): PlanOutcome {
  if (decision.decision === "escalate") return { kind: "escalate" };
  if (TEACHABLE_DECISIONS.has(decision.decision) && decision.objective_code) {
    return { kind: "teach", objective: decision.objective_code };
  }
  if (context.taughtThisSession) return { kind: "end", ending: "finished" };
  if (decision.decision === "rest") return { kind: "end", ending: "rest" };
  return { kind: "end", ending: endingBeforeAnyLesson(context.today ?? null) };
}

/** Whether `planOutcome` needs the dashboard aggregate to describe this decision. */
export function needsTodayToExplain(decision: DecisionView, taughtThisSession: boolean): boolean {
  const outcome = planOutcome(decision, { taughtThisSession, today: null });
  return outcome.kind === "end" && outcome.ending === "caught-up";
}

function endingBeforeAnyLesson(today: TodayView | null): SessionEnding {
  if (!today) return "caught-up";
  if (today.mastery_summary.total === 0) return "nothing-to-learn";
  return "all-mastered";
}

/** A failed `:teach`: a missing lesson is its own honest ending, anything else is a failure. */
export function teachFailureEnding(error: unknown): SessionEnding | null {
  return isNotFound(error) ? "unavailable" : null;
}

export const ENDING_COPY: Record<SessionEnding, { title: MessageKey; body: MessageKey }> = {
  finished: { title: "student.session.endings.finishedTitle", body: "student.session.endings.finishedBody" },
  rest: { title: "student.session.endings.restTitle", body: "student.session.endings.restBody" },
  "nothing-to-learn": {
    title: "student.session.endings.nothingTitle",
    body: "student.session.endings.nothingBody",
  },
  "all-mastered": {
    title: "student.session.endings.allMasteredTitle",
    body: "student.session.endings.allMasteredBody",
  },
  "caught-up": { title: "student.session.endings.caughtUpTitle", body: "student.session.endings.caughtUpBody" },
  unavailable: {
    title: "student.session.endings.unavailableTitle",
    body: "student.session.endings.unavailableBody",
  },
};

// ---- labels -----------------------------------------------------------------------------------

const MASTERY_STATES = ["not_started", "in_progress", "mastered", "needs_review", "at_risk"] as const;
type MasteryState = (typeof MASTERY_STATES)[number];

/** Catalog key for a mastery state; an unknown state reads as "not started", as before. */
export function masteryStateKey(state: string): MessageKey {
  const known = (MASTERY_STATES as readonly string[]).includes(state) ? (state as MasteryState) : "not_started";
  return `common.mastery.${known}`;
}

/** Catalog key + params for a grade level (0 = kindergarten). */
export function gradeLabel(gradeLevel: number | null | undefined): { key: MessageKey; params?: { grade: number } } | null {
  if (gradeLevel === null || gradeLevel === undefined || !Number.isFinite(gradeLevel)) return null;
  if (gradeLevel <= 0) return { key: "student.profile.gradeKg" };
  return { key: "student.profile.grade", params: { grade: gradeLevel } };
}

/** The learner's lesson-content language preference (independent of the interface locale). */
// Until enrolment records an instructional language, this preserves the player's original choice
// (Urdu, then English, then whatever the item has). It is deliberately NOT the interface locale.
export const INSTRUCTION_LOCALE_PREFERENCE: readonly string[] = ["ur", "en"];
