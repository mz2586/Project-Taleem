import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import {
  ASK_FAILURE_COPY,
  ASK_INTENT_LABEL,
  ASK_TAP_INTENTS,
  askReducer,
  askView,
  classifyAskError,
  initialAskState,
  QUESTION_MAX_CHARS,
  questionToSend,
  type AskAnswerWire,
} from "../askTeacher";
import { ApiError } from "../types";

const ANSWERED: AskAnswerWire = {
  ask_id: "ask_1",
  objective_code: "G4.FR.1",
  intent: "question",
  outcome: "answered",
  answer: [
    { text: "The bottom number shows the total.", source: "explanation#2", locale: "en" },
    { text: "  ", source: "explanation#3", locale: "en" },
  ],
  matched_terms: ["bottom"],
  message_key: "ai_teacher.ask.quoted_from_lesson",
  grounded: true,
  generative: false,
  follow_up: ["example", "common_mistake", "recap"],
  free_text_enabled: true,
};

describe("askView", () => {
  it("shows verbatim lesson passages, dropping blanks", () => {
    const v = askView(ANSWERED);
    expect(v.outcome).toBe("answered");
    expect(v.passages.map((p) => p.text)).toEqual(["The bottom number shows the total."]);
    expect(v.message).toBe("student.askTeacher.fromLesson");
  });

  it("never shows lesson text for a holding response", () => {
    const v = askView({ ...ANSWERED, outcome: "holding", message_key: "ai_teacher.ask.holding" });
    expect(v.outcome).toBe("holding");
    expect(v.passages).toEqual([]);
    expect(v.message).toBe("student.askTeacher.holding");
  });

  it("refuses to show anything not marked grounded and non-generative", () => {
    for (const bad of [{ grounded: false }, { generative: true }]) {
      const v = askView({ ...ANSWERED, ...bad });
      expect(v.passages).toEqual([]);
      expect(v.outcome).toBe("not_in_lesson");
    }
  });

  it("treats an unknown outcome as not in the lesson", () => {
    const v = askView({ ...ANSWERED, outcome: "chat" as AskAnswerWire["outcome"] });
    expect(v.outcome).toBe("not_in_lesson");
    expect(v.passages).toEqual([]);
  });
});

describe("askReducer", () => {
  it("offers typing only after the server says it is enabled, and stops on FREE_TEXT_DISABLED", () => {
    let s = askReducer(initialAskState, { type: "open" });
    expect(s).toEqual({ status: "open", freeText: false });
    s = askReducer(s, { type: "request", intent: "example" });
    expect(s.status).toBe("loading");
    s = askReducer(s, { type: "loaded", wire: ANSWERED });
    expect(s.freeText).toBe(true);
    s = askReducer(s, { type: "failed", error: "freeTextOff" });
    expect(s.freeText).toBe(false);
    s = askReducer(s, { type: "close" });
    expect(s).toEqual({ status: "closed", freeText: false });
  });

  it("keeps typing on through an ordinary failure", () => {
    const loaded = askReducer(initialAskState, { type: "loaded", wire: ANSWERED });
    expect(askReducer(loaded, { type: "failed", error: "offline" }).freeText).toBe(true);
  });
});

describe("errors and input", () => {
  it("classifies server refusals", () => {
    expect(classifyAskError(new ApiError(0, {}))).toBe("offline");
    expect(classifyAskError(new ApiError(404, { code: "NO_PUBLISHED_LESSON" }))).toBe("unavailable");
    expect(classifyAskError(new ApiError(403, { code: "FREE_TEXT_DISABLED" }))).toBe("freeTextOff");
    expect(classifyAskError(new ApiError(403, { code: "FORBIDDEN" }))).toBe("error");
    expect(classifyAskError(new ApiError(422, { code: "QUESTION_TOO_LONG" }))).toBe("invalid");
    expect(classifyAskError(new Error("x"))).toBe("error");
  });

  it("sends only a trimmed, non-empty, short question", () => {
    expect(questionToSend("  why?  ")).toBe("why?");
    expect(questionToSend("   ")).toBeNull();
    expect(questionToSend("x".repeat(QUESTION_MAX_CHARS + 1))).toBeNull();
  });

  it("has Urdu and English copy for every key it uses", () => {
    const keys = [
      ...Object.values(ASK_FAILURE_COPY),
      ...ASK_TAP_INTENTS.map((i) => ASK_INTENT_LABEL[i]),
      "student.askTeacher.fromLesson",
      "student.askTeacher.notInLesson",
      "student.askTeacher.holding",
    ] as const;
    for (const locale of ["en", "ur"] as const) {
      for (const key of keys) {
        const text = translate(locale, key);
        expect(text).not.toBe(key);
        expect(text.trim()).not.toBe("");
      }
    }
  });
});
