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
