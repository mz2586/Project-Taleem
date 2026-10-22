import { describe, expect, it } from "vitest";

import {
  canRequestHint,
  continueAfterFeedback,
  currentItem,
  hintsUsed,
  initialPlayerState,
  isLastStep,
  nextHintLevel,
  playerReducer,
  presentationSteps,
  type PlayerAction,
  type PlayerState,
} from "../lessonPlayer";
import type { AnswerView, TeachView } from "../types";

const TEACH: TeachView = {
  utterances: [
    { kind: "present", text: "کسور" },
    { kind: "present", text: "ایک کسر پورے کا حصہ ہے۔" },
    { kind: "present", text: "" }, // blank authored step — never shown as an empty card
    { kind: "present", text: "Step one" },
    { kind: "ask", text: "not a presentation step" },
  ],
  items: [
    { item_ref: "p1", prompt: { ur: "سوال ۱" }, options: ["a", "b"], hint_count: 2 },
    { item_ref: "p2", prompt: { ur: "سوال ۲" }, options: ["a", "b"], hint_count: 0 },
  ],
};

function answer(outcome: AnswerView["outcome"], mastery = 0.4): AnswerView {
  return {
    outcome,
    mastery,
    state: "in_progress",
    post_decision: "continue",
    confirmed_misconceptions: [],
    cleared_misconceptions: [],
    feedback: [],
  };
}

function run(...actions: PlayerAction[]): PlayerState {
  return actions.reduce(playerReducer, initialPlayerState);
}

const taught: PlayerAction = { type: "taught", objective: "OBJ", teach: TEACH };

describe("presentation pacing", () => {
  it("presents only non-empty `present` utterances, one at a time", () => {
    const s = run({ type: "started", sessionId: "s1" }, taught);
    expect(s.phase).toBe("presenting");
    expect(presentationSteps(s).map((u) => u.text)).toEqual([
      "کسور",
      "ایک کسر پورے کا حصہ ہے۔",
      "Step one",
    ]);
    expect(s.step).toBe(0);
    expect(isLastStep(s)).toBe(false);
  });

  it("steps forward and back without leaving the lesson bounds", () => {
    let s = run(taught, { type: "previousStep" });
    expect(s.step).toBe(0);
    s = run(taught, { type: "nextStep" }, { type: "nextStep" }, { type: "nextStep" });
    expect(s.step).toBe(2);
    expect(isLastStep(s)).toBe(true);
    s = playerReducer(s, { type: "previousStep" });
    expect(s.step).toBe(1);
  });

  it("moves to the first question only when the child says they are ready", () => {
    const s = run(taught, { type: "ready" });
    expect(s.phase).toBe("asking");
    expect(currentItem(s)?.item_ref).toBe("p1");
  });

  it("skips presentation when the lesson has nothing to present", () => {
    const s = run({ type: "taught", objective: "OBJ", teach: { ...TEACH, utterances: [] } });
    expect(s.phase).toBe("asking");
  });

  it("ignores step navigation outside the presentation phase", () => {
    const s = run(taught, { type: "ready" });
    expect(playerReducer(s, { type: "nextStep" })).toBe(s);
    expect(playerReducer(s, { type: "ready" })).toBe(s);
  });
});

describe("authored hint ladder", () => {
  it("offers a hint only while authored rungs remain", () => {
    let s = run(taught, { type: "ready" });
    expect(canRequestHint(s)).toBe(true);
    expect(nextHintLevel(s)).toBe(0);
    s = playerReducer(s, { type: "hint", hint: "first", exhausted: false });
    expect(nextHintLevel(s)).toBe(1);
    expect(canRequestHint(s)).toBe(true);
    s = playerReducer(s, { type: "hint", hint: "second", exhausted: false });
    expect(s.hints).toEqual(["first", "second"]);
    expect(canRequestHint(s)).toBe(false); // hint_count reached
  });

  it("never offers a hint for an item that has none", () => {
    const s = run(
      taught,
      { type: "ready" },
      { type: "answered", answer: answer("correct") },
      { type: "nextItem" },
    );
    expect(currentItem(s)?.item_ref).toBe("p2");
    expect(canRequestHint(s)).toBe(false);
  });

  it("stops asking once the server reports the ladder exhausted", () => {
    const legacy: TeachView = { ...TEACH, items: [{ item_ref: "p1", prompt: {}, options: ["a"] }] };
    let s = run({ type: "taught", objective: "OBJ", teach: legacy }, { type: "ready" });
    expect(canRequestHint(s)).toBe(true); // no hint_count: ask and let the server decide
    s = playerReducer(s, { type: "hint", hint: null, exhausted: true });
    expect(s.hints).toEqual([]);
    expect(canRequestHint(s)).toBe(false);
  });

  it("does not offer hints while feedback is showing", () => {
    const s = run(taught, { type: "ready" }, { type: "answered", answer: answer("incorrect") });
    expect(canRequestHint(s)).toBe(false);
    expect(playerReducer(s, { type: "hint", hint: "late", exhausted: false })).toBe(s);
  });
});

describe("evidence and progression", () => {
  it("reports every hint seen on the item as hints_used, across retries", () => {
    let s = run(taught, { type: "ready" }, { type: "hint", hint: "first", exhausted: false });
    expect(hintsUsed(s)).toBe(1);
    s = run(
      taught,
      { type: "ready" },
      { type: "hint", hint: "first", exhausted: false },
      { type: "answered", answer: answer("incorrect") },
      { type: "retry" },
    );
    // A retry keeps the help already given — it still counts towards this item's evidence.
    expect(s.phase).toBe("asking");
    expect(hintsUsed(s)).toBe(1);
    expect(s.answer).toBeNull();
  });

  it("retries the same item on a miss and never advances", () => {
    const s = run(taught, { type: "ready" }, { type: "answered", answer: answer("incorrect", 0.2) });
    expect(continueAfterFeedback(s)).toBe("retry");
    expect(s.mastery).toBe(0.2);
    expect(currentItem(playerReducer(s, { type: "retry" }))?.item_ref).toBe("p1");
  });

  it("treats a partial answer as a retry, not a pass", () => {
    const s = run(taught, { type: "ready" }, { type: "answered", answer: answer("partial") });
    expect(continueAfterFeedback(s)).toBe("retry");
  });

  it("advances to the next item with a fresh hint ladder after a correct answer", () => {
    let s = run(
      taught,
      { type: "ready" },
      { type: "hint", hint: "first", exhausted: false },
      { type: "answered", answer: answer("correct") },
    );
    expect(continueAfterFeedback(s)).toBe("nextItem");
    s = playerReducer(s, { type: "nextItem" });
    expect(s.itemIndex).toBe(1);
    expect(s.hints).toEqual([]);
    expect(s.hintsExhausted).toBe(false);
    expect(hintsUsed(s)).toBe(0);
  });

  it("re-plans with the server after the last item is answered correctly", () => {
    const s = run(
      taught,
      { type: "ready" },
      { type: "answered", answer: answer("correct") },
      { type: "nextItem" },
      { type: "answered", answer: answer("correct", 0.9) },
    );
    expect(continueAfterFeedback(s)).toBe("plan");
    expect(s.mastery).toBe(0.9);
  });

  it("starts the next lesson from its first step with no carried-over hints", () => {
    const s = run(
      taught,
      { type: "nextStep" },
      { type: "ready" },
      { type: "hint", hint: "first", exhausted: false },
      { type: "planning" },
      taught,
    );
    expect(s.phase).toBe("presenting");
    expect(s.step).toBe(0);
    expect(s.itemIndex).toBe(0);
    expect(s.hints).toEqual([]);
  });
});

describe("terminal states", () => {
  it("maps network and auth failures to the offline screen, others to the error screen", () => {
    expect(run({ type: "failed", offline: true }).phase).toBe("offline");
    expect(run({ type: "failed", offline: false }).phase).toBe("error");
  });

  it("can escalate to a human from any phase", () => {
    expect(run(taught, { type: "escalated" }).phase).toBe("escalated");
  });

  it("records the session summary on completion", () => {
    const s = run({ type: "completed", summary: { state: "ended", interactions: 6 } });
    expect(s.phase).toBe("complete");
    expect(s.summary?.interactions).toBe(6);
  });
});
