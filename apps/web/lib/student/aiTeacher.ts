// AI Teacher on the student screens — "Explain it another way" and "Why this next?". Pure; tested.
//
// Contract: packages/contracts/ai-teacher.openapi.yaml. What the backend does (verified against
// services/core-api learning/application/ai_teacher_service.py):
//
// - `:explain` returns `utterances`: a deterministic arrangement of AUTHORED lesson content in one of
//   four styles. That is verified curriculum text and is shown exactly like the lesson itself.
// - Only when the generative flag is on (it is off in every environment today), a provider is
//   configured, consent allows `ai_teaching`, and quota remains, the response gains `generation`.
//   Its `explanation.text` is an AI-written rephrase: NOT verified. It is shown only beside the
//   catalog text for its `notice_key` (today always "ai_teacher.generated_explanation_unverified"),
//   in a visually distinct block, and never without that notice. An unknown notice key still gets a
//   generic "written by a computer, not checked" notice — generated text is never shown bare.
//   A refused or unavailable rephrase (`explanation: null`) shows nothing extra.
// - `/ai-teacher/capabilities` reports the offline matrix. `lesson_explanation` other than
//   available/cached hides the feature; with no capabilities answer the server stays the gate.
// - `/ai-teacher/plan` explains the next step. Its `rationale` notes are English engine strings and
//   are never shown. The "Why this next?" view renders the plan's structured `reasons` (stable codes
//   + parameters, lib/learning/rationale.ts) in the child's language; an older server without them
//   falls back to the plan's machine-readable state fields — never to matching English text.
//
// None of this changes lib/student/lessonPlayer.ts: the explanation has its own small reducer.

import type { MessageKey } from "../i18n/messages";
import {
  reasonLines,
  type ExplainedRecommendationWire,
  type PlacementSummaryWire,
  type ReasonWire,
} from "../learning/rationale";
import { ApiError, type DecisionKind } from "./types";

// ---- contract types ------------------------------------------------------------------------------

export const EXPLAIN_STYLES = ["direct", "worked_example_led", "concrete_to_abstract", "question_led"] as const;
export type ExplainStyle = (typeof EXPLAIN_STYLES)[number];

export interface ExplainUtterance {
  kind: string;
  text: string;
  locale?: string;
}

export interface GeneratedExplanationWire {
  text: string;
  locale: string;
  generated: boolean;
  verified: boolean;
  verified_source?: string;
  notice_key: string;
  source?: string;
  lesson_id?: string;
  objective_code?: string;
  grounded_on: string[];
  provider?: string;
  tier?: string;
}

export interface GenerationWire {
  status: "accepted" | "refused" | "unavailable";
  fallback: "authored" | null;
  explanation: GeneratedExplanationWire | null;
}

export interface ExplanationWire {
  objective_code: string;
  style: ExplainStyle;
  utterances: ExplainUtterance[];
  confidence?: "low" | "medium" | "high";
  grounded?: boolean;
  guardrail?: { escalate?: boolean; escalate_reason?: string } & Record<string, unknown>;
  rationale?: string[];
  generation?: GenerationWire;
}

export interface AdaptivePlanWire {
  next_action: {
    kind: string;
    objective_code: string | null;
    rationale?: Array<{ rule_id: string; note: string }>;
    /** Additive: the structured, localizable rationale. */
    reasons?: ReasonWire[];
  };
  weak_topics: Array<{
    objective_code: string;
    state: string;
    mastery: number;
    active_misconceptions: string[];
    reason: string;
    reasons?: ReasonWire[];
  }>;
  revision_due: string[];
  practice: Array<{ objective_code: string; difficulty: string; confidence: string }>;
  confidence: "low" | "medium" | "high";
  rationale: string[];
  /** Additive: each recommendation with its reasons, confidence and evidence. */
  recommendations?: ExplainedRecommendationWire[];
  placement?: PlacementSummaryWire;
}

export interface CapabilitiesWire {
  offline: Record<string, string>;
}

// ---- availability ----------------------------------------------------------------------------------

export type ExplainAvailability =
  | { available: true; styles: readonly ExplainStyle[] }
  | { available: false; reason: "offline" | "disabled" };

const USABLE = new Set(["available", "cached"]);

/** Whether "Explain it another way" is offered. `:explain` is a server call, so it needs a network. */
export function explainAvailability(capabilities: CapabilitiesWire | null, online: boolean): ExplainAvailability {
  const state = capabilities?.offline?.["lesson_explanation"];
  if (state !== undefined && !USABLE.has(state)) return { available: false, reason: "disabled" };
  if (!online) return { available: false, reason: "offline" };
  return { available: true, styles: EXPLAIN_STYLES };
}

/**
 * The style to ask for next. The first request sends none, so the server's policy picks by learner
 * state (it favours a worked example after a wrong answer). Each further press moves to the next
 * style after the one just shown, so "another way" is always different.
 */
export function nextStyle(shown: ExplainStyle | null, styles: readonly ExplainStyle[] = EXPLAIN_STYLES): ExplainStyle | null {
  if (styles.length === 0) return null;
  if (shown === null) return null;
  const i = styles.indexOf(shown);
  return styles[(i + 1) % styles.length] ?? styles[0]!;
}

export function styleLabel(style: ExplainStyle): MessageKey {
  return `student.aiTeacher.style.${style}`;
}

// ---- the explanation view ---------------------------------------------------------------------

export interface GeneratedView {
  text: string;
  locale: string;
  /** The catalog notice that MUST be shown beside the text. */
  notice: MessageKey;
  /** Plain-language provenance ("the lesson explanation", "worked example, step 3"). */
  groundedOn: Array<{ key: MessageKey; params?: Record<string, number> }>;
}

export interface ExplanationView {
  style: ExplainStyle;
  /** Verified, authored curriculum text — shown like the lesson. */
  utterances: Array<{ kind: string; text: string; locale: string | null }>;
  /** The AI-written rephrase, if any. Never present without `notice`. */
  generated: GeneratedView | null;
  /** The teacher thinks a mentor should step in. */
  escalate: boolean;
}

const NOTICE_KEYS: Record<string, MessageKey> = {
  "ai_teacher.generated_explanation_unverified": "student.aiTeacher.notice.generatedUnverified",
};

export function noticeFor(noticeKey: string | null | undefined): MessageKey {
  return (noticeKey && NOTICE_KEYS[noticeKey]) || "student.aiTeacher.notice.generatedOther";
}

/** "lesson.explanation.en" -> "the lesson explanation"; "lesson.worked_example_steps[2]" -> step 3. */
export function groundingLabel(field: string): { key: MessageKey; params?: Record<string, number> } {
  const step = /worked_example_steps\[(\d+)\]/.exec(field);
  if (step) return { key: "student.aiTeacher.grounding.workedStep", params: { step: Number(step[1]) + 1 } };
  if (/explanation/.test(field)) return { key: "student.aiTeacher.grounding.explanation" };
  if (/title/.test(field)) return { key: "student.aiTeacher.grounding.title" };
  if (/hint/.test(field)) return { key: "student.aiTeacher.grounding.hint" };
  return { key: "student.aiTeacher.grounding.other" };
}

function dedupe<T extends { key: MessageKey; params?: Record<string, number> }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((i) => {
    const id = `${i.key}:${JSON.stringify(i.params ?? {})}`;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

export function explanationView(wire: ExplanationWire): ExplanationView {
  const utterances = (wire.utterances ?? [])
    .filter((u) => typeof u.text === "string" && u.text.trim() !== "")
    .map((u) => ({ kind: u.kind, text: u.text, locale: u.locale ?? null }));

  // Any generated text is treated as generated — whatever its flags say, it is never promoted to
  // verified content. Only an accepted rephrase with text is shown at all.
  const g = wire.generation;
  const e = g?.status === "accepted" ? g.explanation : null;
  const generated: GeneratedView | null =
    e && typeof e.text === "string" && e.text.trim() !== ""
      ? {
          text: e.text,
          locale: e.locale,
          notice: noticeFor(e.notice_key),
          groundedOn: dedupe((e.grounded_on ?? []).map(groundingLabel)),
        }
      : null;

  return {
    style: wire.style,
    utterances,
    generated,
    escalate: wire.guardrail?.escalate === true,
  };
}

// ---- the explanation panel state -------------------------------------------------------------------

/** Where the request came from: the lesson steps, or the feedback after a wrong answer. */
export type ExplainContext = "presenting" | "feedback";
export type ExplainFailure = "offline" | "unavailable" | "error";

export type ExplainState =
  | { status: "closed"; lastStyle: ExplainStyle | null }
  | { status: "loading"; context: ExplainContext; lastStyle: ExplainStyle | null }
  | { status: "shown"; context: ExplainContext; view: ExplanationView; lastStyle: ExplainStyle }
  | { status: "failed"; context: ExplainContext; error: ExplainFailure; lastStyle: ExplainStyle | null };

export type ExplainAction =
  | { type: "request"; context: ExplainContext }
  | { type: "loaded"; view: ExplanationView }
  | { type: "failed"; error: ExplainFailure }
  | { type: "close" }
  /** A new objective was taught: styles start over. */
  | { type: "reset" };

export const initialExplainState: ExplainState = { status: "closed", lastStyle: null };

export function explainReducer(state: ExplainState, action: ExplainAction): ExplainState {
  switch (action.type) {
    case "request":
      if (state.status === "loading") return state;
      return { status: "loading", context: action.context, lastStyle: state.lastStyle };
    case "loaded":
      if (state.status !== "loading") return state;
      return { status: "shown", context: state.context, view: action.view, lastStyle: action.view.style };
    case "failed":
      if (state.status !== "loading") return state;
      return { status: "failed", context: state.context, error: action.error, lastStyle: state.lastStyle };
    case "close":
      return { status: "closed", lastStyle: state.lastStyle };
    case "reset":
      return initialExplainState;
  }
}

/** The style to send with the next request from this state. */
export function styleToRequest(state: ExplainState, styles: readonly ExplainStyle[] = EXPLAIN_STYLES): ExplainStyle | null {
  return nextStyle(state.lastStyle, styles);
}

export function classifyExplainError(error: unknown): ExplainFailure {
  if (error instanceof ApiError) {
    if (error.status === 0) return "offline";
    // 404: no published lesson for the objective any more.
    if (error.status === 404) return "unavailable";
  }
  return "error";
}

export const EXPLAIN_FAILURE_COPY: Record<ExplainFailure, MessageKey> = {
  offline: "student.aiTeacher.failed.offline",
  unavailable: "student.aiTeacher.failed.unavailable",
  error: "student.aiTeacher.failed.error",
};

// ---- "Why this next?" -----------------------------------------------------------------------------

export interface WhyNextModel {
  /** What the teacher chose, in words. */
  choice: MessageKey;
  objective: string | null;
  /** Short "because" lines, most important first. */
  reasons: Array<{ key: MessageKey; params?: Record<string, number> }>;
  certainty: MessageKey;
}

const KINDS: readonly DecisionKind[] = [
  "diagnose",
  "teach",
  "continue",
  "review",
  "remediate",
  "advance",
  "revise",
  "escalate",
  "rest",
  "complete",
];

function isKind(value: string): value is DecisionKind {
  return (KINDS as readonly string[]).includes(value);
}

/** An older server's weak topic, read from its state fields (never its English `reason`). */
function weakTopicReason(w: AdaptivePlanWire["weak_topics"][number]): MessageKey {
  if ((w.active_misconceptions ?? []).length > 0) return "student.whyNext.because.misconception";
  if (w.state === "at_risk") return "student.whyNext.because.atRisk";
  return "student.whyNext.because.stillLearning";
}

export function whyNextModel(plan: AdaptivePlanWire): WhyNextModel {
  const kind = plan.next_action?.kind ?? "";
  const reasons: WhyNextModel["reasons"] = [];

  const objective = plan.next_action?.objective_code ?? null;
  const structured = plan.next_action?.reasons ?? [];
  if (structured.length > 0) {
    for (const line of reasonLines(structured, "student")) {
      const params: Record<string, number> = {};
      for (const [k, v] of Object.entries(line.params ?? {})) if (typeof v === "number") params[k] = v;
      reasons.push(Object.keys(params).length ? { key: line.key, params } : { key: line.key });
    }
  } else {
    const focus = objective ? plan.weak_topics?.find((w) => w.objective_code === objective) : undefined;
    if (focus) reasons.push({ key: weakTopicReason(focus) });
  }

  const due = plan.revision_due?.length ?? 0;
  if (due > 0) reasons.push({ key: "student.whyNext.because.reviewsDue", params: { count: due } });
  const weak = plan.weak_topics?.length ?? 0;
  if (weak > 0) reasons.push({ key: "student.whyNext.because.weakTopics", params: { count: weak } });
  if (reasons.length === 0) {
    reasons.push({ key: kind === "complete" ? "student.whyNext.because.allDone" : "student.whyNext.because.nextInOrder" });
  }

  return {
    choice: isKind(kind) ? `student.whyNext.kind.${kind}` : "student.whyNext.kind.other",
    objective,
    reasons,
    certainty: `student.whyNext.certainty.${plan.confidence === "high" || plan.confidence === "medium" ? plan.confidence : "low"}`,
  };
}
