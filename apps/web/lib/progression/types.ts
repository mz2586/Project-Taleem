// Wire shapes for the learner's path, unit checks and academic record
// (docs/05-education/PROGRESSION_AND_EXAMINATION_CONTRACT.md).
//
// The contract names the concepts; the server was built alongside this client, so every field is
// written loosely here (optional, a localized map OR a plain string, a few aliases) and normalised
// in exactly one place — `./wire.ts`. A field-name change on the server is an edit there and here.

/** Authored text: a `{locale: text}` map (curriculum) or a single string. */
export type LocalizedWire = string | Record<string, string>;

/** Seconds since the epoch (the API's convention), milliseconds, or an ISO-8601 string. */
export type TimeWire = number | string;

// ---- path (§1) ------------------------------------------------------------------------------------

export type LessonState = "not_started" | "in_progress" | "practised" | "mastered";
export type UnitState = "not_started" | "in_progress" | "ready_for_check" | "completed";

export interface PathLessonWire {
  lesson_id?: string | null;
  objective_code?: string | null;
  title?: LocalizedWire | null;
  state?: string | null;
}

export interface UnitCheckSummaryWire {
  available?: boolean | null;
  /** Best score so far, percent 0–100 (null before any finished sitting). */
  best_score?: number | null;
  passed?: boolean | null;
  last_sitting_id?: string | null;
  /** Optional: the server's retake decision (§2 retake rule). */
  can_retake?: boolean | null;
  retake_after?: TimeWire | null;
  /** Optional: a sitting still open (resumable). */
  open_sitting_id?: string | null;
  item_count?: number | null;
  pass_mark?: number | null;
}

export interface PathUnitWire {
  unit_key?: string | null;
  title?: LocalizedWire | null;
  state?: string | null;
  lessons?: PathLessonWire[] | null;
  check?: UnitCheckSummaryWire | null;
}

export interface PathSubjectWire {
  subject_key?: string | null;
  title?: LocalizedWire | null;
  units?: PathUnitWire[] | null;
}

/** The AI's recommended next step: an object (preferred) or a bare lesson title. */
export type NextStepWire =
  | string
  | {
      kind?: string | null;
      lesson_id?: string | null;
      objective_code?: string | null;
      unit_key?: string | null;
      title?: LocalizedWire | null;
      reason?: LocalizedWire | null;
    };

export interface PathWire {
  grade?: number | null;
  grade_state?: string | null;
  subjects?: PathSubjectWire[] | null;
  next_step?: NextStepWire | null;
}

// ---- unit check (§2) ------------------------------------------------------------------------------

export interface CheckItemWire {
  item_ref: string;
  kind?: string | null;
  prompt?: LocalizedWire | null;
  options?: string[] | null;
  left_count?: number | null;
}

export interface SittingWire {
  sitting_id: string;
  unit_key?: string | null;
  expires_at?: TimeWire | null;
  total?: number | null;
  answered?: number | null;
  item?: CheckItemWire | null;
  /** Optional: `open` / `finished` / `incomplete` (expired). */
  state?: string | null;
}

export interface AnswerResultWire {
  answered?: number | null;
  total?: number | null;
  next_item?: CheckItemWire | null;
}

export interface ObjectiveResultWire {
  objective_code?: string | null;
  title?: LocalizedWire | null;
  correct?: number | null;
  total?: number | null;
}

export interface RemediationWire {
  objective_code?: string | null;
  title?: LocalizedWire | null;
  /** The lesson teaching it; the link opens it by objective code (lib/student/chosenLesson.ts). */
  lesson_id?: string | null;
}

export interface FinishWire {
  score_percent?: number | null;
  passed?: boolean | null;
  pass_mark?: number | null;
  per_objective?: ObjectiveResultWire[] | null;
  remediation?: RemediationWire[] | null;
  /** Optional, as on the path summary. */
  retake_after?: TimeWire | null;
}

// ---- academic record (§3) -------------------------------------------------------------------------

export interface RecordSittingWire {
  sitting_id?: string | null;
  unit_key?: string | null;
  unit_title?: LocalizedWire | null;
  started_at?: TimeWire | null;
  finished_at?: TimeWire | null;
  /** `finished` (scored) or `incomplete` (expired unfinished — never "failed"). */
  state?: string | null;
  score_percent?: number | null;
  passed?: boolean | null;
  per_objective?: ObjectiveResultWire[] | null;
}

export interface RecordUnitWire {
  unit_key?: string | null;
  title?: LocalizedWire | null;
  state?: string | null;
  best_score?: number | null;
  passed?: boolean | null;
  sittings?: RecordSittingWire[] | null;
}

export interface RecordSubjectWire {
  subject_key?: string | null;
  title?: LocalizedWire | null;
  units?: RecordUnitWire[] | null;
}

export interface RecordLessonWire {
  lesson_id?: string | null;
  objective_code?: string | null;
  title?: LocalizedWire | null;
  mastered_at?: TimeWire | null;
}

export interface RecordReportCardWire {
  card_id?: string | null;
  period_start?: TimeWire | null;
  period_end?: TimeWire | null;
  issued_at?: TimeWire | null;
}

export interface GradeCompletionWire {
  grade?: number | null;
  completed_at?: TimeWire | null;
}

export interface RecordWire {
  grade?: number | null;
  grade_state?: string | null;
  /** The grade-completion entry, when every unit of the grade is completed. */
  grade_completion?: GradeCompletionWire | null;
  grade_completed_at?: TimeWire | null;
  subjects?: RecordSubjectWire[] | null;
  /** All sittings (or nested per unit — both are read). */
  sittings?: RecordSittingWire[] | null;
  /** A list of lessons, or just a count. */
  lessons_mastered?: RecordLessonWire[] | number | null;
  report_cards?: RecordReportCardWire[] | null;
  derived_at?: TimeWire | null;
}
