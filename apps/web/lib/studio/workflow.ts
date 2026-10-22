// Curriculum Studio workflow rules for the review UI. Pure; unit-tested.
//
// These mirror the backend exactly so the interface never offers an action the server will refuse:
//   - contexts/curriculum_studio/domain/workflow.py: states, REVIEW_CHAIN, STATE_ROLE;
//   - application/service.py: STAGE_GATES, the no-self-approval check, publish preconditions;
//   - domain/quality.py: the 9 gates and which have automated pre-checks;
//   - auth/pdp.py: which role may author / review / publish / roll back.
// The server stays the authority. The UI only reflects the rules; it never relaxes them.

import type { MessageKey } from "../i18n/messages";
import type { GateView, LessonView, ValidationResult } from "../studio-api";
import type { StudioActor, StudioRole } from "./session";

export const REVIEW_CHAIN = ["subject_expert", "educational_qa", "accessibility", "language", "ai_safety"] as const;
export type ReviewStage = (typeof REVIEW_CHAIN)[number];

export const QUEUE_STAGES = ["draft", ...REVIEW_CHAIN, "approved", "published", "archived"] as const;
export type QueueStage = (typeof QUEUE_STAGES)[number];

/** The one role that reviews each stage (workflow.py STATE_ROLE). */
export const STAGE_ROLE: Record<ReviewStage, StudioRole> = {
  subject_expert: "subject_expert",
  educational_qa: "instructional_designer",
  accessibility: "a11y_specialist",
  language: "language_editor",
  ai_safety: "safety_officer",
};

/** Gates a human certifies by approving a stage (service.py STAGE_GATES). */
export const STAGE_GATES: Record<ReviewStage, readonly string[]> = {
  subject_expert: ["technical_accuracy"],
  educational_qa: ["educational_review", "age_appropriateness"],
  accessibility: ["accessibility"],
  language: ["language"],
  ai_safety: ["ai_safety"],
};

/** All 9 gates, in quality.py order. Publishing needs every one passed. */
export const ALL_GATES = [
  "educational_review",
  "curriculum_alignment",
  "technical_accuracy",
  "language",
  "accessibility",
  "ai_safety",
  "age_appropriateness",
  "readability",
  "performance",
] as const;

/** Gates with an automated pre-check (run by :validate). */
export const AUTOMATED_GATES: ReadonlySet<string> = new Set([
  "curriculum_alignment",
  "accessibility",
  "readability",
  "performance",
]);

export type GateName = (typeof ALL_GATES)[number];

/** Catalog key for a gate's name; null for a gate this client does not know (shown raw). */
export function gateLabelKey(gate: string): MessageKey | null {
  return (ALL_GATES as readonly string[]).includes(gate) ? (`studio.gates.${gate as GateName}` as const) : null;
}

/** Catalog key for a workflow state's name; null for an unknown state (shown raw). */
export function stageLabelKey(state: string): MessageKey | null {
  return (QUEUE_STAGES as readonly string[]).includes(state) ? (`studio.stages.${state as QueueStage}` as const) : null;
}

export function isReviewStage(state: string): state is ReviewStage {
  return (REVIEW_CHAIN as readonly string[]).includes(state);
}

/** The stage a role works in — the queue tab it lands on. */
export function homeStage(role: StudioRole): QueueStage {
  if (role === "subject_author") return "draft";
  if (role === "curriculum_architect") return "approved";
  const stage = REVIEW_CHAIN.find((s) => STAGE_ROLE[s] === role);
  return stage ?? "draft";
}

// ---- tags --------------------------------------------------------------------------------------

export function lessonTags(lesson: LessonView): string[] {
  return lesson.metadata?.tags ?? [];
}

/** Imported Grade 4 drafts carry `provisional` (curriculum_ingest.py). */
export function isProvisional(lesson: LessonView): boolean {
  return lessonTags(lesson).some((t) => t === "provisional" || t.startsWith("content-status:provisional"));
}

/** The `imported-from:<doc §section>` sources on a lesson. */
export function importedFrom(lesson: LessonView): string[] {
  return lessonTags(lesson)
    .filter((t) => t.startsWith("imported-from:"))
    .map((t) => t.slice("imported-from:".length));
}

// ---- gates -------------------------------------------------------------------------------------

export type GateStatus = "passed" | "failed" | "not-run";

export interface GateRow {
  gate: string;
  status: GateStatus;
  mode: "auto" | "human" | "auto+human";
  /** For a human gate: the stage whose reviewer certifies it. */
  certifiedAt: ReviewStage | null;
  reviewerRole: string | null;
  findings: string[];
}

function stageCertifying(gate: string): ReviewStage | null {
  return REVIEW_CHAIN.find((s) => STAGE_GATES[s].includes(gate)) ?? null;
}

/**
 * One row per gate, all 9, in order: what the lesson record says, merged with the findings of the
 * latest :validate run. A gate with no record is "not run" — never shown as passed.
 */
export function gateRows(gates: readonly GateView[], validation?: ValidationResult | null): GateRow[] {
  return ALL_GATES.map((gate) => {
    const recorded = gates.find((g) => g.gate === gate);
    const checked = validation?.gates.find((g) => g.gate === gate);
    const certifiedAt = stageCertifying(gate);
    const auto = AUTOMATED_GATES.has(gate);
    let status: GateStatus = "not-run";
    if (recorded) status = recorded.passed ? "passed" : "failed";
    // A fresh failing pre-check overrides an older pass: the content changed since.
    if (checked && !checked.passed) status = "failed";
    else if (checked && checked.passed && status === "not-run" && !certifiedAt) status = "passed";
    return {
      gate,
      status,
      mode: auto && certifiedAt ? "auto+human" : auto ? "auto" : "human",
      certifiedAt,
      reviewerRole: recorded?.reviewer_role ?? null,
      findings: checked?.findings ?? [],
    };
  });
}

export function gateSummary(gates: readonly GateView[]): { passed: number; total: number; allGreen: boolean } {
  const passed = ALL_GATES.filter((g) => gates.some((r) => r.gate === g && r.passed)).length;
  return { passed, total: ALL_GATES.length, allGreen: passed === ALL_GATES.length };
}

// ---- actions -----------------------------------------------------------------------------------

export type StudioAction = "submit" | "approve" | "request_changes" | "publish" | "rollback";

export interface ActionOption {
  action: StudioAction;
  /** False: shown, but disabled with `reason` — the role may act here, a precondition is unmet. */
  enabled: boolean;
  reason: MessageKey | null;
  /** Gates blocking a publish, by name. */
  blockingGates?: string[];
  /** Every human decision records a written reason. */
  requiresNote: boolean;
}

/**
 * The actions this actor may take on this lesson, and only those. An action the actor's role can
 * never perform here is omitted entirely, not shown disabled. One the role could perform but a
 * precondition blocks (self-approval, gates not green, validation failing) is shown disabled with
 * the exact reason.
 */
export function availableActions(
  lesson: LessonView,
  actor: StudioActor,
  validation?: ValidationResult | null,
): ActionOption[] {
  const out: ActionOption[] = [];
  const state = lesson.state;
  const authorRole = lesson.metadata?.author_role ?? null;

  if (state === "draft" && actor.role === "subject_author") {
    const failing = validation ? !validation.ok : false;
    out.push({
      action: "submit",
      enabled: !failing,
      reason: failing ? "studio.actions.reason.validationFailing" : null,
      requiresNote: false,
    });
  }

  if (isReviewStage(state) && STAGE_ROLE[state] === actor.role) {
    // The backend refuses a reviewer whose role authored the lesson. Show that up front.
    const selfReview = authorRole !== null && authorRole === actor.role;
    for (const action of ["approve", "request_changes"] as const) {
      out.push({
        action,
        enabled: !selfReview,
        reason: selfReview ? "studio.actions.reason.selfApproval" : null,
        requiresNote: true,
      });
    }
  }

  if (state === "approved" && actor.role === "curriculum_architect") {
    const blocking = ALL_GATES.filter((g) => !lesson.gates.some((r) => r.gate === g && r.passed));
    const failing = validation ? !validation.ok : false;
    out.push({
      action: "publish",
      enabled: blocking.length === 0 && !failing,
      reason:
        blocking.length > 0
          ? "studio.actions.reason.gatesNotGreen"
          : failing
            ? "studio.actions.reason.validationFailing"
            : null,
      blockingGates: blocking,
      requiresNote: true,
    });
  }

  if ((state === "approved" || state === "published") && actor.role === "curriculum_architect") {
    out.push({ action: "rollback", enabled: true, reason: null, requiresNote: true });
  }

  return out;
}

/** Validate a decision form: a human decision needs a written, non-trivial reason. */
export function noteError(option: ActionOption, note: string): MessageKey | null {
  if (!option.requiresNote) return null;
  return note.trim().length >= 3 ? null : "studio.actions.noteRequired";
}

// ---- the queue ---------------------------------------------------------------------------------

export interface QueueFilters {
  stage: QueueStage;
  subject: string | null;
  pack: string | null;
  provisional: "any" | "only" | "exclude";
  gates: "any" | "all-green" | "not-green";
  search: string;
}

export const DEFAULT_FILTERS: Omit<QueueFilters, "stage"> = {
  subject: null,
  pack: null,
  provisional: "any",
  gates: "any",
  search: "",
};

export function filterQueue(lessons: readonly LessonView[], f: QueueFilters): LessonView[] {
  const q = f.search.trim().toLowerCase();
  return lessons
    .filter((l) => l.state === f.stage)
    .filter((l) => !f.subject || l.subject === f.subject)
    .filter((l) => !f.pack || (l.curriculum_pack ?? "") === f.pack)
    .filter((l) => f.provisional === "any" || (f.provisional === "only") === isProvisional(l))
    .filter((l) => f.gates === "any" || (f.gates === "all-green") === gateSummary(l.gates).allGreen)
    .filter(
      (l) =>
        !q ||
        l.lesson_id.toLowerCase().includes(q) ||
        Object.values(l.title).some((t) => t.toLowerCase().includes(q)) ||
        l.learning_outcomes.some((o) => o.toLowerCase().includes(q)),
    )
    .sort((a, b) => a.lesson_id.localeCompare(b.lesson_id));
}

export function stageCounts(lessons: readonly LessonView[]): Record<QueueStage, number> {
  const counts = Object.fromEntries(QUEUE_STAGES.map((s) => [s, 0])) as Record<QueueStage, number>;
  for (const l of lessons) if ((QUEUE_STAGES as readonly string[]).includes(l.state)) counts[l.state as QueueStage] += 1;
  return counts;
}

/** Distinct values for the filter menus. */
export function facets(lessons: readonly LessonView[]): { subjects: string[]; packs: string[] } {
  const subjects = [...new Set(lessons.map((l) => l.subject))].sort();
  const packs = [...new Set(lessons.map((l) => l.curriculum_pack).filter((p): p is string => !!p))].sort();
  return { subjects, packs };
}
