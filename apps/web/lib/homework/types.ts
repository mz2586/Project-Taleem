// Wire shapes for homework and marking (docs/10-curriculum-studio/HOMEWORK_AND_MARKING_CONTRACT.md).
//
// The contract names the endpoints and most fields; where it leaves a spelling open the type is
// written loosely (a localized map OR a plain string, an optional alias) and normalised in exactly
// one place — `./wire.ts` — so a field-name change on the server is a one-file edit here.

export type SubmissionState = "not_started" | "submitted" | "returned" | "marked";
export type MarkOutcome = "met" | "not_yet";

/**
 * §6 (the AI-led path). `self_paced`: the item comes from a lesson the learner studied — no teacher,
 * no due date, maybe no class. `assignment`: a teacher set it (it adds a due date).
 */
export type HomeworkSource = "self_paced" | "assignment";
/**
 * §6. `auto`: an exact answer key, marked on submit (met / not_yet, `reviewed_by: "auto"`).
 * `self_check`: an open answer — never scored; the child may compare it with a sample afterwards.
 * `teacher`: a class teacher may mark it (§3).
 */
export type HomeworkMarking = "auto" | "self_check" | "teacher";

/** §6: shown to the child only after a self-check submission. Either part may be missing. */
export interface CompareWire {
  sample_answer?: LocalizedWire | null;
  guidance?: LocalizedWire | null;
}

/** Authored text: a `{locale: text}` map (curriculum) or a single string. */
export type LocalizedWire = string | Record<string, string>;

// ---- learner (§2) -----------------------------------------------------------------------------------

/** The latest submission for one item, as the learner may see it (never a rubric or sample answer). */
export interface LearnerSubmissionWire {
  submission_id: string;
  state: SubmissionState;
  text?: string | null;
  /** Teacher's note: on `returned` (why to try again) and on `marked`. */
  feedback?: string | null;
  outcome?: MarkOutcome | null;
  score?: number | null;
  submitted_at?: number | null;
  marked_at?: number | null;
  returned_at?: number | null;
  /** How many times this item was submitted (1 for the first answer). */
  attempt?: number | null;
  /** §6: "auto" when Taleem's exact-answer rule marked it; otherwise a teacher (any other value). */
  reviewed_by?: string | null;
  /** §6: may also arrive on the submission rather than the item. */
  marking?: HomeworkMarking | null;
  /** §6: self-check only, after submission. */
  compare?: CompareWire | null;
  /** §6: true after an auto-marked `not_yet` — the child may try again. Missing ⇒ false. */
  can_retry?: boolean | null;
}

export interface HomeworkItemWire {
  item_ref: string;
  /** Always "written" for this surface (ItemView.kind). */
  kind?: string;
  /** Authored item type: short | long | word_problem. */
  type?: string;
  prompt: LocalizedWire;
  hints?: string[];
  /** 200 for short, 2000 otherwise. */
  max_chars: number;
  /** The latest state, either flat on the item or inside `submission`. */
  state?: SubmissionState;
  submission?: LearnerSubmissionWire | null;
  /** §6. Missing: inherited from the assignment, else inferred (a due date ⇒ assignment). */
  source?: HomeworkSource | null;
  /** §6. Missing: unknown (treated as a human may mark it — never claimed as auto). */
  marking?: HomeworkMarking | null;
  /** §6: tolerated on the item too; still shown only after submission. */
  compare?: CompareWire | null;
  /** §6: true after an auto-marked `not_yet` — the child may try again. Missing ⇒ false. */
  can_retry?: boolean | null;
}

export interface HomeworkAssignmentWire {
  assignment_id: string;
  class_id?: string;
  class_name?: string;
  objective_code: string;
  lesson_title?: LocalizedWire | null;
  /** Assignments only; self-paced entries have none (§6). */
  due_at?: number | null;
  /** §6: a whole entry may be tagged; an item's own tag wins. */
  source?: HomeworkSource | null;
  items: HomeworkItemWire[];
}

/** GET /v1/school/learners/{student_ref}/homework */
export interface LearnerHomeworkWire {
  assignments: HomeworkAssignmentWire[];
}

/** POST …/items/{item_ref}:submit — the body. */
export interface SubmitBody {
  text: string;
}

// ---- teacher (§3, §4) -------------------------------------------------------------------------------

export interface RubricLevelWire {
  score: number;
  label?: LocalizedWire | null;
  descriptor?: LocalizedWire | null;
}

export interface RubricCriterionWire {
  criterion?: LocalizedWire;
  name?: LocalizedWire;
  description?: LocalizedWire;
}

export interface RubricWire {
  criteria?: Array<LocalizedWire | RubricCriterionWire>;
  max_score: number;
  levels?: RubricLevelWire[];
}

/** One row of GET /v1/school/classes/{class_id}/submissions. */
export interface SubmissionRowWire {
  submission_id: string;
  student_ref: string;
  /** Learner display name (the contract's "learner display name"; `display_name` also accepted). */
  learner_display_name?: string;
  display_name?: string;
  assignment_id: string;
  objective_code?: string;
  lesson_title?: LocalizedWire | null;
  item_ref: string;
  item_type?: string;
  prompt: LocalizedWire;
  rubric?: RubricWire | null;
  sample_answer?: LocalizedWire | null;
  guidance?: LocalizedWire | null;
  text: string;
  state: SubmissionState;
  outcome?: MarkOutcome | null;
  score?: number | null;
  feedback?: string | null;
  submitted_at: number;
  marked_at?: number | null;
  returned_at?: number | null;
}

export interface SubmissionQueueWire {
  submissions: SubmissionRowWire[];
}

export type QueueStatus = Exclude<SubmissionState, "not_started">;

/** POST /v1/school/submissions/{submission_id}:mark */
export interface MarkBody {
  outcome: MarkOutcome;
  score: number | null;
  feedback: string;
}

/** POST /v1/school/submissions/{submission_id}:return */
export interface ReturnBody {
  feedback: string;
}
