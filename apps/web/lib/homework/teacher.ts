// Teacher marking view model (contract §3, §4). Pure and unit-tested; the page only renders it.
//
// - The queue is oldest first (the server's order, re-applied so a stale cache cannot reorder it).
// - A mark is `{outcome, score, feedback}`: outcome required; score required and in 0..max_score
//   when the item has a rubric, and null when it has none; feedback trimmed, at most 1000 chars.
// - "Send back to try again" needs feedback — the child has to know what to change.
// - A safeguarding concern names a category and may carry the teacher's own note. It never copies
//   the child's text: the server references the submission, and the child is never told.

import type { LocalizedText } from "../i18n/content";
import type { MessageKey } from "../i18n/messages";
import { CATEGORIES, MAX_TEXT, type Category } from "../safeguarding/categories";
import { ApiError } from "../student/types";
import { teacherFailure } from "../teacher/errors";
import type {
  LocalizedWire,
  MarkBody,
  MarkOutcome,
  QueueStatus,
  ReturnBody,
  RubricCriterionWire,
  RubricWire,
  SubmissionRowWire,
} from "./types";
import { learnerName, localized } from "./wire";

export const FEEDBACK_MAX = 1000;
/** The concern note's cap — the safeguarding free-text limit (server MAX_FREE_TEXT). */
export const CONCERN_NOTE_MAX = MAX_TEXT;

export const QUEUE_STATUSES: readonly QueueStatus[] = ["submitted", "returned", "marked"];

export const QUEUE_STATUS_KEYS: Record<QueueStatus, MessageKey> = {
  submitted: "teacher.marking.filter.submitted",
  returned: "teacher.marking.filter.returned",
  marked: "teacher.marking.filter.marked",
};

const count = (text: string) => Array.from(text).length;

// ---- the queue --------------------------------------------------------------------------------------

export interface RubricLevelView {
  score: number;
  label: LocalizedText | null;
  descriptor: LocalizedText | null;
}

export interface RubricView {
  maxScore: number;
  criteria: LocalizedText[];
  /** One choice per score 0..maxScore, with the authored descriptor when there is one. */
  levels: RubricLevelView[];
}

export interface SubmissionRowView {
  submissionId: string;
  studentRef: string;
  learnerName: string;
  assignmentId: string;
  objectiveCode: string;
  lessonTitle: LocalizedText | null;
  itemRef: string;
  prompt: LocalizedText | null;
  text: string;
  rubric: RubricView | null;
  sampleAnswer: LocalizedText | null;
  guidance: LocalizedText | null;
  state: QueueStatus;
  outcome: MarkOutcome | null;
  score: number | null;
  feedback: string | null;
  submittedAt: number;
  decidedAt: number | null;
}

function validMaxScore(rubric: RubricWire | null | undefined): number | null {
  const max = rubric?.max_score;
  return typeof max === "number" && Number.isInteger(max) && max >= 0 ? max : null;
}

/** A criterion is authored text, or an object naming it (`criterion` / `name` / `description`). */
function criterionText(c: LocalizedWire | RubricCriterionWire): LocalizedWire | undefined {
  if (typeof c === "string") return c;
  const named = c as RubricCriterionWire;
  if ("criterion" in named || "name" in named || "description" in named) return named.criterion ?? named.name ?? named.description;
  return c as Record<string, string>;
}

export function rubricView(rubric: RubricWire | null | undefined, preference: readonly string[]): RubricView | null {
  const maxScore = validMaxScore(rubric);
  if (!rubric || maxScore === null) return null;
  const criteria = (rubric.criteria ?? [])
    .map((c) => localized(criterionText(c), preference))
    .filter((c): c is LocalizedText => c !== null);
  const authored = new Map((rubric.levels ?? []).map((l) => [l.score, l]));
  const levels: RubricLevelView[] = [];
  for (let score = 0; score <= maxScore; score++) {
    const level = authored.get(score);
    levels.push({
      score,
      label: localized(level?.label, preference),
      descriptor: localized(level?.descriptor, preference),
    });
  }
  return { maxScore, criteria, levels };
}

export function rowView(row: SubmissionRowWire, preference: readonly string[]): SubmissionRowView {
  const state: QueueStatus = row.state === "returned" || row.state === "marked" ? row.state : "submitted";
  return {
    submissionId: row.submission_id,
    studentRef: row.student_ref,
    learnerName: learnerName(row),
    assignmentId: row.assignment_id,
    objectiveCode: row.objective_code ?? "",
    lessonTitle: localized(row.lesson_title, preference),
    itemRef: row.item_ref,
    prompt: localized(row.prompt, preference),
    text: row.text ?? "",
    rubric: rubricView(row.rubric, preference),
    sampleAnswer: localized(row.sample_answer, preference),
    guidance: localized(row.guidance, preference),
    state,
    outcome: row.outcome === "met" || row.outcome === "not_yet" ? row.outcome : null,
    score: typeof row.score === "number" ? row.score : null,
    feedback: row.feedback?.trim() ? row.feedback : null,
    submittedAt: row.submitted_at,
    decidedAt: row.marked_at ?? row.returned_at ?? null,
  };
}

/** Oldest submission first; ties broken by id so the order is stable. */
export function queueView(rows: readonly SubmissionRowWire[], preference: readonly string[]): SubmissionRowView[] {
  return rows
    .map((r) => rowView(r, preference))
    .sort((a, b) => a.submittedAt - b.submittedAt || a.submissionId.localeCompare(b.submissionId));
}

// ---- marking ------------------------------------------------------------------------------------------

export interface MarkDraft {
  outcome: MarkOutcome | null;
  /** The chosen rubric score, as the form holds it ("" = none chosen). */
  score: string;
  feedback: string;
}

export interface MarkProblems {
  outcome?: MessageKey;
  score?: MessageKey;
  feedback?: MessageKey;
}

export type Built<T> = { ok: true; body: T } | { ok: false; problems: MarkProblems };

export function markBody(draft: MarkDraft, rubric: Pick<RubricView, "maxScore"> | null): Built<MarkBody> {
  const problems: MarkProblems = {};
  if (draft.outcome !== "met" && draft.outcome !== "not_yet") problems.outcome = "teacher.marking.problems.outcome";

  let score: number | null = null;
  if (rubric) {
    const raw = draft.score.trim();
    const n = raw === "" ? NaN : Number(raw);
    if (raw === "") problems.score = "teacher.marking.problems.scoreRequired";
    else if (!Number.isInteger(n) || n < 0 || n > rubric.maxScore) problems.score = "teacher.marking.problems.scoreRange";
    else score = n;
  }

  const feedback = draft.feedback.trim();
  if (count(feedback) > FEEDBACK_MAX) problems.feedback = "teacher.marking.problems.feedbackTooLong";

  if (problems.outcome || problems.score || problems.feedback) return { ok: false, problems };
  return { ok: true, body: { outcome: draft.outcome as MarkOutcome, score, feedback } };
}

export function returnBody(feedback: string): Built<ReturnBody> {
  const text = feedback.trim();
  if (text === "") return { ok: false, problems: { feedback: "teacher.marking.problems.returnFeedbackRequired" } };
  if (count(text) > FEEDBACK_MAX) return { ok: false, problems: { feedback: "teacher.marking.problems.feedbackTooLong" } };
  return { ok: true, body: { feedback: text } };
}

// ---- safeguarding ------------------------------------------------------------------------------------

/** POST /v1/school/submissions/{submission_id}:concern — the server adds source, learner and submission. */
export interface ConcernBody {
  category: Category;
  text?: string;
}

export type ConcernBuilt = { ok: true; body: ConcernBody } | { ok: false; problem: MessageKey };

export function concernBody(input: { category: Category | null; note: string }): ConcernBuilt {
  if (!input.category || !CATEGORIES.includes(input.category)) return { ok: false, problem: "teacher.marking.concern.categoryRequired" };
  const note = input.note.trim();
  if (count(note) > CONCERN_NOTE_MAX) return { ok: false, problem: "teacher.marking.concern.noteTooLong" };
  return { ok: true, body: note ? { category: input.category, text: note } : { category: input.category } };
}

// ---- failures ----------------------------------------------------------------------------------------

function commonKey(error: unknown): MessageKey {
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
      if (error instanceof ApiError && error.status === 429) return "teacher.errors.tooMany";
      return "teacher.errors.generic";
  }
}

/** Mark or return: 409 means it was already decided (a correction needs a new submission). */
export function decisionErrorKey(error: unknown): MessageKey {
  if (error instanceof ApiError) {
    if (error.status === 409) return "teacher.marking.errors.alreadyDecided";
    if (error.status === 422) return "teacher.errors.checkDetails";
  }
  return commonKey(error);
}

export function concernErrorKey(error: unknown): MessageKey {
  if (error instanceof ApiError && error.status === 422) return "teacher.errors.checkDetails";
  return commonKey(error);
}
