// "Ask your teacher" on the lesson screen. Pure; tested.
//
// Contract: packages/contracts/ai-teacher.openapi.yaml (`:ask`). What the backend does (verified
// against services/core-api learning/domain/lesson_qa.py and application/ai_teacher_service.py):
//
// - Tap intents (`example`, `common_mistake`, `recap`) need no typing and are always offered online.
// - A typed `question` is accepted only when the server says `free_text_enabled` (a flag, a
//   safeguarding disclosure screen and live `ai_teaching` consent). Until the first answer we do
//   not know, so the text box appears only after a response says it is enabled; a 403
//   FREE_TEXT_DISABLED hides it again.
// - `answered`: the `answer` passages are VERBATIM authored lesson text, shown like the lesson
//   itself (each with its own lang/dir). `not_in_lesson`: an honest "that is not in this lesson".
// - `holding`: the disclosure screen matched. No lesson text is shown, only the fixed holding
//   message and the way to get help. The question is never echoed back.

import type { MessageKey } from "../i18n/messages";
import { ApiError } from "./types";

export const ASK_TAP_INTENTS = ["example", "common_mistake", "recap"] as const;
export type AskTapIntent = (typeof ASK_TAP_INTENTS)[number];
export type AskIntent = AskTapIntent | "question";
export const QUESTION_MAX_CHARS = 300;

export interface AskPassageWire {
  text: string;
  source: string;
  locale: string;
}

export interface AskAnswerWire {
  ask_id: string;
  objective_code: string;
  intent: AskIntent;
  outcome: "answered" | "not_in_lesson" | "holding";
  answer: AskPassageWire[];
  matched_terms: string[];
  message_key: string;
  grounded: boolean;
  generative: boolean;
  follow_up: AskTapIntent[];
  free_text_enabled: boolean;
}

export type AskFailure = "offline" | "unavailable" | "freeTextOff" | "invalid" | "error";

export interface AskView {
  intent: AskIntent;
  outcome: AskAnswerWire["outcome"];
  passages: AskPassageWire[];
  message: MessageKey;
}

export type AskState =
  | { status: "closed"; freeText: boolean }
  | { status: "open"; freeText: boolean }
  | { status: "loading"; freeText: boolean; intent: AskIntent }
  | { status: "loaded"; freeText: boolean; view: AskView }
  | { status: "failed"; freeText: boolean; error: AskFailure };

export const initialAskState: AskState = { status: "closed", freeText: false };

export type AskAction =
  | { type: "open" }
  | { type: "close" }
  | { type: "request"; intent: AskIntent }
  | { type: "loaded"; wire: AskAnswerWire }
  | { type: "failed"; error: AskFailure };

export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "open":
      return { status: "open", freeText: state.freeText };
    case "close":
      return { status: "closed", freeText: state.freeText };
    case "request":
      return { status: "loading", freeText: state.freeText, intent: action.intent };
    case "loaded":
      return { status: "loaded", freeText: action.wire.free_text_enabled === true, view: askView(action.wire) };
    case "failed":
      // The server refused free text: stop offering the box.
      return { status: "failed", freeText: action.error === "freeTextOff" ? false : state.freeText, error: action.error };
  }
}

const MESSAGE: Record<AskAnswerWire["outcome"], MessageKey> = {
  answered: "student.askTeacher.fromLesson",
  not_in_lesson: "student.askTeacher.notInLesson",
  holding: "student.askTeacher.holding",
};

/** What the panel shows. Lesson text is shown only for `answered`; never for `holding`. */
export function askView(wire: AskAnswerWire): AskView {
  const outcome = wire.outcome in MESSAGE ? wire.outcome : "not_in_lesson";
  const passages =
    outcome === "answered" && wire.grounded === true && wire.generative === false
      ? wire.answer.filter((p) => typeof p.text === "string" && p.text.trim() !== "")
      : [];
  // An "answered" with nothing showable is reported honestly as not in the lesson.
  const shown = outcome === "answered" && passages.length === 0 ? "not_in_lesson" : outcome;
  return { intent: wire.intent, outcome: shown, passages, message: MESSAGE[shown] };
}

export function classifyAskError(error: unknown): AskFailure {
  if (error instanceof ApiError) {
    if (error.status === 0) return "offline";
    if (error.status === 404) return "unavailable";
    if (error.status === 403 && error.problem.code === "FREE_TEXT_DISABLED") return "freeTextOff";
    if (error.status === 422) return "invalid";
  }
  return "error";
}

export const ASK_FAILURE_COPY: Record<AskFailure, MessageKey> = {
  offline: "student.aiTeacher.failed.offline",
  unavailable: "student.askTeacher.notInLesson",
  freeTextOff: "student.askTeacher.typingOff",
  invalid: "student.askTeacher.invalid",
  error: "student.aiTeacher.failed.error",
};

export const ASK_INTENT_LABEL: Record<AskTapIntent, MessageKey> = {
  example: "student.askTeacher.intent.example",
  common_mistake: "student.askTeacher.intent.common_mistake",
  recap: "student.askTeacher.intent.recap",
};

/** A typed question ready to send, or null (blank or too long). */
export function questionToSend(raw: string): string | null {
  const q = raw.trim();
  return q === "" || q.length > QUESTION_MAX_CHARS ? null : q;
}
