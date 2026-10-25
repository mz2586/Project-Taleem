// Types for the Learning Intelligence API (packages/contracts/learning.openapi.yaml).
// Governance-safe: the student portal operates on pseudonymous synthetic learners only.

export type DecisionKind =
  | "diagnose"
  | "teach"
  | "continue"
  | "review"
  | "remediate"
  | "advance"
  | "revise"
  | "escalate"
  | "rest"
  | "complete";

export type Outcome = "correct" | "incorrect" | "partial";

export interface SessionView {
  session_id: string;
  state: string;
}

export interface DecisionView {
  decision: DecisionKind;
  objective_code: string | null;
  rationale: string[];
}

export interface Utterance {
  kind: string; // present | ask | hint | feedback | remediate
  text: string;
}

export interface ItemView {
  item_ref: string;
  prompt: Record<string, string>; // locale -> text
  options: string[];
  /** Interaction kind (ITEM_INTERACTION_CONTRACT §2); absent means "choose" (servers before the contract). */
  kind?: string;
  /** match/sort: options[0..left_count-1] are the items/cards, the rest the matches/groups. */
  left_count?: number;
  /** Authored graduated hints available via `:hint` (absent on servers that predate it). */
  hint_count?: number;
}

export interface HintView {
  hint: string | null; // the authored hint at `level`; null once the ladder is exhausted
  level: number;
  exhausted: boolean;
}

export interface TeachView {
  utterances: Utterance[];
  items: ItemView[];
}

export interface AnswerView {
  outcome: Outcome;
  mastery: number;
  state: string;
  post_decision: DecisionKind;
  confirmed_misconceptions: string[];
  cleared_misconceptions: string[];
  feedback: string[];
}

export interface SessionEndView {
  state: string;
  interactions: number;
}

export interface ObjectiveKnowledge {
  mastery: number;
  uncertainty: number;
  state: string; // not_started | in_progress | mastered | needs_review | at_risk
}

export interface KnowledgeView {
  student_ref: string;
  objectives: Record<string, ObjectiveKnowledge>;
}

// GET /v1/learning/students/{ref}/today (student.openapi.yaml TodayView). `next_action.reason` is
// "complete" with a null objective when nothing is left to recommend — which, with a zero total, is
// what a learner sees while no lesson has been published.
export interface TodayView {
  /** `title`: the next lesson's title by locale (absent on older servers). */
  next_action: { objective_code: string | null; reason: string; title?: Record<string, string> | null };
  mastery_summary: { mastered: number; in_progress: number; total: number };
  revision_due_count: number;
  /** Lesson title by locale for each objective the learner has a state for (cohort-filtered). */
  objective_titles?: Record<string, Record<string, string>>;
}

export interface ProgressView {
  student_ref: string;
  objectives_mastered: number;
  objectives_in_progress: number;
  total_attempts: number;
  accuracy: number;
  misconceptions_detected: number;
  misconceptions_cleared: number;
  reviews_scheduled: number;
  events_by_type: Record<string, number>;
  objective_mastery: Record<string, number>;
}

// RFC 9457 problem+json (the platform's error contract).
export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  instance?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails;
  constructor(status: number, problem: ProblemDetails) {
    super(problem.detail ?? problem.title ?? problem.code ?? `HTTP ${status}`);
    this.status = status;
    this.problem = problem;
  }
  /** True when the failure is auth-related (drives silent re-sign-in). */
  get isAuth(): boolean {
    return this.status === 401 || this.status === 403;
  }
}
