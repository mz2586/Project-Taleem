// The child's "Tell a grown-up" flow as a pure state machine.
//
//   choose ──tap a picture──▶ confirm ──Send──▶ sending ──▶ sent
//     ▲                         │  └─(optional) add words      ├──▶ offline (nothing stored; say so)
//     └────────choose again─────┘                              ├──▶ busy (rate limited)
//                                                              └──▶ error ──try again──▶ confirm
//
// Tapping is enough: words are optional, behind their own button. Sending needs a connection. The
// offline sync queue is deliberately NOT used: it lives in this device's storage, and a family
// device is often shared — a queued report could be read by the very person it is about. So an
// offline child is told plainly that nothing was sent and nothing was kept, and to find a grown-up.

import { cleanText, type Category, MAX_TEXT } from "./categories";
import type { ConcernContext } from "./context";

export type ChildStep = "choose" | "confirm" | "sending" | "sent" | "offline" | "busy" | "error";

export interface ChildState {
  step: ChildStep;
  category: Category | null;
  wordsOpen: boolean;
  text: string;
  textTooLong: boolean;
}

export type ChildAction =
  | { type: "choose"; category: Category }
  | { type: "back" }
  | { type: "openWords" }
  | { type: "setText"; text: string }
  | { type: "send" }
  | { type: "sent" }
  | { type: "failed"; outcome: "offline" | "busy" | "error" }
  | { type: "retry" };

export const initialChildState: ChildState = {
  step: "choose",
  category: null,
  wordsOpen: false,
  text: "",
  textTooLong: false,
};

export function childReducer(state: ChildState, action: ChildAction): ChildState {
  switch (action.type) {
    case "choose":
      return { ...state, step: "confirm", category: action.category };
    case "back":
      return { ...initialChildState };
    case "openWords":
      return state.step === "confirm" ? { ...state, wordsOpen: true } : state;
    case "setText":
      return { ...state, text: action.text, textTooLong: !cleanText(action.text).ok };
    case "send": {
      if (state.step !== "confirm" || state.category === null) return state;
      if (!cleanText(state.text).ok) return { ...state, textTooLong: true };
      return { ...state, step: "sending" };
    }
    case "sent":
      // Forget what was written as soon as it is delivered: nothing is shown back on this device.
      return state.step === "sending" ? { ...initialChildState, step: "sent" } : state;
    case "failed":
      return state.step === "sending" ? { ...state, step: action.outcome } : state;
    case "retry":
      return { ...state, step: state.category ? "confirm" : "choose" };
  }
}

export interface RaisePayload {
  category: Category;
  text?: string;
  context: { screen?: string; lessonId?: string };
}

/** The request body, or null if the state cannot be sent. Never includes a learner ref. */
export function childPayload(state: ChildState, context: ConcernContext): RaisePayload | null {
  if (state.category === null) return null;
  const cleaned = cleanText(state.text);
  if (!cleaned.ok) return null;
  const payload: RaisePayload = { category: state.category, context: {} };
  if (cleaned.text) payload.text = cleaned.text;
  if (context.screen) payload.context.screen = context.screen;
  if (context.lessonId) payload.context.lessonId = context.lessonId;
  return payload;
}

/** How a failed send is explained: no connection, too many, or anything else. */
export function failureOutcome(error: unknown): "offline" | "busy" | "error" {
  const status = (error as { status?: unknown } | null)?.status;
  if (status === 0) return "offline";
  if (status === 429) return "busy";
  return "error";
}

export { MAX_TEXT };
