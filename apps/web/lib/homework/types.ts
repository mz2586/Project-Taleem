// Wire shapes for homework and marking (docs/10-curriculum-studio/HOMEWORK_AND_MARKING_CONTRACT.md).
//
// The contract names the endpoints and most fields; where it leaves a spelling open the type is
// written loosely (a localized map OR a plain string, an optional alias) and normalised in exactly
// one place — `./wire.ts` — so a field-name change on the server is a one-file edit here.

export type SubmissionState = "not_started" | "submitted" | "returned" | "marked";
export type MarkOutcome = "met" | "not_yet";

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
}

export interface HomeworkAssignmentWire {
  assignment_id: string;
  class_id?: string;
  class_name?: string;
  objective_code: string;
  lesson_title?: LocalizedWire | null;
  due_at: number;
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
