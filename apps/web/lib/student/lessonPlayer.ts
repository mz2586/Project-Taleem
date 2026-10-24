// Lesson player state machine — the pure core of /student/session.
//
// The page is a thin view over this reducer so the teaching rules can be tested without a browser:
//   - the lesson is presented ONE step at a time (title, explanation, each worked-example step), the
//     pacing a young reader needs, rather than as a wall of text;
//   - help is the AUTHORED graduated hint ladder from `:hint`, revealed one rung at a time and only
//     offered when the item actually has hints;
//   - every hint the child saw is reported as `hints_used` on the answer, because mastery evidence
//     that ignores help overstates what the child can do alone;
//   - a wrong answer retries the same item and never reveals the correct option.
// No content is ever constructed here: every string shown comes from an approved server response.

import type { AnswerView, ItemView, SessionEndView, TeachView, Utterance } from "./types";

export type Phase =
  | "starting"
  | "presenting"
  | "asking"
  | "feedback"
  | "complete"
  | "escalated"
  | "offline"
  | "error";

export interface PlayerState {
  phase: Phase;
  sessionId: string;
  objective: string;
  teach: TeachView | null;
  /** Index of the presentation step currently on screen (0-based). */
  step: number;
  itemIndex: number;
  /** Authored hints revealed so far for the CURRENT item, in ladder order. */
  hints: string[];
  hintsExhausted: boolean;
  answer: AnswerView | null;
  mastery: number;
  summary: SessionEndView | null;
}

export type PlayerAction =
  | { type: "started"; sessionId: string }
  | { type: "planning" }
  | { type: "taught"; objective: string; teach: TeachView }
  | { type: "nextStep" }
  | { type: "previousStep" }
  | { type: "ready" }
  | { type: "hint"; hint: string | null; exhausted: boolean }
  | { type: "answered"; answer: AnswerView }
  | { type: "retry" }
  | { type: "nextItem" }
  | { type: "completed"; summary: SessionEndView }
  | { type: "escalated" }
  | { type: "failed"; offline: boolean };

export const initialPlayerState: PlayerState = {
  phase: "starting",
  sessionId: "",
  objective: "",
  teach: null,
  step: 0,
  itemIndex: 0,
  hints: [],
  hintsExhausted: false,
  answer: null,
  mastery: 0,
  summary: null,
};

/** The presentation steps of the current lesson (the server's `present` utterances, in order). */
export function presentationSteps(state: PlayerState): Utterance[] {
  return (state.teach?.utterances ?? []).filter((u) => u.kind === "present" && u.text.trim() !== "");
}

export function currentItem(state: PlayerState): ItemView | undefined {
  return state.teach?.items[state.itemIndex];
}

export function isLastStep(state: PlayerState): boolean {
  return state.step >= presentationSteps(state).length - 1;
}

/** Whether a further authored hint may be requested for the current item. */
export function canRequestHint(state: PlayerState): boolean {
  const item = currentItem(state);
  if (!item || state.phase !== "asking" || state.hintsExhausted) return false;
  // `hint_count` is absent from servers that predate it; then ask and let `exhausted` decide.
  return item.hint_count === undefined || state.hints.length < item.hint_count;
}

/** The ladder rung to request next (0-based) — one past the hints already shown. */
export function nextHintLevel(state: PlayerState): number {
  return state.hints.length;
}

/** `hints_used` for the answer about to be submitted. */
export function hintsUsed(state: PlayerState): number {
  return state.hints.length;
}

export type ContinueStep = "retry" | "nextItem" | "plan";

/** What "Continue" does after feedback: retry on a miss, else the next item, else re-plan. */
export function continueAfterFeedback(state: PlayerState): ContinueStep {
  if (!state.answer || state.answer.outcome !== "correct") return "retry";
  const count = state.teach?.items.length ?? 0;
  return state.itemIndex + 1 < count ? "nextItem" : "plan";
}

/**
 * Skipping an item this device cannot render (no answer is sent, so no evidence is recorded): the
 * next item, or — after the last one — re-plan, as "Continue" does after a correct answer.
 */
export function skipItem(state: PlayerState): Exclude<ContinueStep, "retry"> {
  const count = state.teach?.items.length ?? 0;
  return state.itemIndex + 1 < count ? "nextItem" : "plan";
}

const freshItem = { hints: [] as string[], hintsExhausted: false, answer: null };

export function playerReducer(state: PlayerState, action: PlayerAction): PlayerState {
  switch (action.type) {
    case "started":
      return { ...state, sessionId: action.sessionId };
    case "planning":
      return { ...state, phase: "starting" };
    case "taught": {
      const next = {
        ...state,
        ...freshItem,
        objective: action.objective,
        teach: action.teach,
        step: 0,
        itemIndex: 0,
      };
      // A lesson with nothing to present goes straight to its questions.
      return { ...next, phase: presentationSteps(next).length > 0 ? "presenting" : "asking" };
    }
    case "nextStep":
      if (state.phase !== "presenting") return state;
      return isLastStep(state) ? state : { ...state, step: state.step + 1 };
    case "previousStep":
      if (state.phase !== "presenting") return state;
      return { ...state, step: Math.max(0, state.step - 1) };
    case "ready":
      if (state.phase !== "presenting") return state;
      return { ...state, phase: currentItem(state) ? "asking" : "starting" };
    case "hint":
      if (state.phase !== "asking") return state;
      return {
        ...state,
        hints: action.hint ? [...state.hints, action.hint] : state.hints,
        hintsExhausted: action.exhausted || !action.hint,
      };
    case "answered":
      return { ...state, answer: action.answer, mastery: action.answer.mastery, phase: "feedback" };
    case "retry":
      // Same item, hints kept: help already seen still counts towards this item's evidence.
      return { ...state, answer: null, phase: "asking" };
    case "nextItem":
      return { ...state, ...freshItem, itemIndex: state.itemIndex + 1, phase: "asking" };
    case "completed":
      return { ...state, summary: action.summary, phase: "complete" };
    case "escalated":
      return { ...state, phase: "escalated" };
    case "failed":
      return { ...state, phase: action.offline ? "offline" : "error" };
  }
}
