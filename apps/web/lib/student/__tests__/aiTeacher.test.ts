import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import {
  classifyExplainError,
  EXPLAIN_FAILURE_COPY,
  EXPLAIN_STYLES,
  explainAvailability,
  explainReducer,
  explanationView,
  groundingLabel,
  initialExplainState,
  nextStyle,
  noticeFor,
  styleLabel,
  styleToRequest,
  whyNextModel,
  type AdaptivePlanWire,
  type ExplanationWire,
} from "../aiTeacher";
import { ApiError } from "../types";

// What core-api returns today (generative flag off): authored utterances, no `generation` key.
const TEMPLATED: ExplanationWire = {
  objective_code: "G4.N.1",
  style: "worked_example_led",
  utterances: [
    { kind: "present", text: "Place value tells us what each digit is worth.", locale: "en" },
    { kind: "present", text: "  ", locale: "en" },
    { kind: "present", text: "مثال: 345 میں 4 دہائیاں ہیں۔", locale: "ur" },
  ],
  confidence: "medium",
  grounded: true,
  guardrail: { grounded: true, generative: false, escalate: false },
  rationale: ["style=worked_example_led"],
};

const WITH_GENERATION: ExplanationWire = {
  ...TEMPLATED,
  generation: {
    status: "accepted",
    fallback: null,
    explanation: {
      text: "Think of digits as boxes: hundreds, tens, ones.",
      locale: "en",
      generated: true,
      verified: false,
      verified_source: "utterances",
      notice_key: "ai_teacher.generated_explanation_unverified",
      source: "generated",
      lesson_id: "l1",
      objective_code: "G4.N.1",
      grounded_on: ["lesson.explanation.en", "lesson.worked_example_steps[2]", "lesson.explanation.ur"],
    },
  },
};

describe("explanationView", () => {
  it("works fully without `generation` (the flag is off everywhere today)", () => {
    const view = explanationView(TEMPLATED);
    expect(view.generated).toBeNull();
    expect(view.style).toBe("worked_example_led");
    expect(view.utterances).toEqual([
      { kind: "present", text: "Place value tells us what each digit is worth.", locale: "en" },
      { kind: "present", text: "مثال: 345 میں 4 دہائیاں ہیں۔", locale: "ur" },
    ]);
  });

  it("keeps generated text out of the verified utterances and always attaches its notice", () => {
    const view = explanationView(WITH_GENERATION);
    expect(view.utterances).toHaveLength(2);
    expect(view.generated).toMatchObject({
      text: "Think of digits as boxes: hundreds, tens, ones.",
      locale: "en",
      notice: "student.aiTeacher.notice.generatedUnverified",
    });
    expect(view.generated!.groundedOn).toEqual([
      { key: "student.aiTeacher.grounding.explanation" },
      { key: "student.aiTeacher.grounding.workedStep", params: { step: 3 } },
    ]);
  });

  it("shows nothing extra for a refused or unavailable rephrase", () => {
    for (const status of ["refused", "unavailable"] as const) {
      const wire = { ...TEMPLATED, generation: { status, fallback: "authored" as const, explanation: null } };
      expect(explanationView(wire).generated).toBeNull();
    }
  });

  it("never shows a non-accepted explanation even if text is present", () => {
    const wire = { ...WITH_GENERATION, generation: { ...WITH_GENERATION.generation!, status: "refused" as const } };
    expect(explanationView(wire).generated).toBeNull();
  });

  it("gives an unknown notice key a generic notice rather than none", () => {
    expect(noticeFor("ai_teacher.some_future_notice")).toBe("student.aiTeacher.notice.generatedOther");
    expect(noticeFor(undefined)).toBe("student.aiTeacher.notice.generatedOther");
    const wire = {
      ...WITH_GENERATION,
      generation: { ...WITH_GENERATION.generation!, explanation: { ...WITH_GENERATION.generation!.explanation!, notice_key: "x" } },
    };
    expect(explanationView(wire).generated!.notice).toBe("student.aiTeacher.notice.generatedOther");
  });

  it("has catalog text for every notice in both languages, saying it is not checked", () => {
    for (const key of ["student.aiTeacher.notice.generatedUnverified", "student.aiTeacher.notice.generatedOther"] as const) {
      expect(translate("en", key)).toMatch(/computer/i);
      expect(translate("en", key)).toMatch(/not been checked/);
      expect(translate("ur", key)).toContain("کمپیوٹر");
    }
  });

  it("passes through an escalation", () => {
    expect(explanationView({ ...TEMPLATED, guardrail: { escalate: true } }).escalate).toBe(true);
    expect(explanationView(TEMPLATED).escalate).toBe(false);
  });
});

describe("groundingLabel", () => {
  it("names the lesson fields in plain words", () => {
    expect(groundingLabel("lesson.title.ur")).toEqual({ key: "student.aiTeacher.grounding.title" });
    expect(groundingLabel("lesson.worked_example_steps[0]")).toEqual({
      key: "student.aiTeacher.grounding.workedStep",
      params: { step: 1 },
    });
    expect(groundingLabel("lesson.something_else")).toEqual({ key: "student.aiTeacher.grounding.other" });
  });
});

describe("explainAvailability", () => {
  it("offers every contract style when the server has no objection", () => {
    expect(explainAvailability({ offline: { lesson_explanation: "available" } }, true)).toEqual({
      available: true,
      styles: EXPLAIN_STYLES,
    });
    expect(explainAvailability(null, true).available).toBe(true);
  });

  it("hides the feature when the server reports it unavailable", () => {
    expect(explainAvailability({ offline: { lesson_explanation: "disabled_offline" } }, true)).toEqual({
      available: false,
      reason: "disabled",
    });
  });

  it("needs a network, because :explain is a server call", () => {
    expect(explainAvailability({ offline: { lesson_explanation: "available" } }, false)).toEqual({
      available: false,
      reason: "offline",
    });
  });
});

describe("style cycling", () => {
  it("lets the server choose first, then always picks a different style", () => {
    expect(nextStyle(null)).toBeNull();
    expect(nextStyle("direct")).toBe("worked_example_led");
    expect(nextStyle("question_led")).toBe("direct");
  });

  it("labels every style in both languages", () => {
    for (const style of EXPLAIN_STYLES) {
      expect(translate("en", styleLabel(style))).not.toContain("student.");
      expect(translate("ur", styleLabel(style))).not.toContain("student.");
    }
  });
});

describe("explainReducer", () => {
  it("request -> loading -> shown, remembering the style for the next request", () => {
    let s = explainReducer(initialExplainState, { type: "request", context: "feedback" });
    expect(s).toEqual({ status: "loading", context: "feedback", lastStyle: null });
    expect(styleToRequest(s)).toBeNull();
    s = explainReducer(s, { type: "loaded", view: explanationView(TEMPLATED) });
    expect(s.status).toBe("shown");
    expect(styleToRequest(s)).toBe("concrete_to_abstract");
  });

  it("keeps the last style across close, and forgets it on a new objective", () => {
    const shown = explainReducer(explainReducer(initialExplainState, { type: "request", context: "presenting" }), {
      type: "loaded",
      view: explanationView(TEMPLATED),
    });
    const closed = explainReducer(shown, { type: "close" });
    expect(closed).toEqual({ status: "closed", lastStyle: "worked_example_led" });
    expect(explainReducer(closed, { type: "reset" })).toEqual(initialExplainState);
  });

  it("records a failure and ignores stray results", () => {
    const loading = explainReducer(initialExplainState, { type: "request", context: "feedback" });
    expect(explainReducer(loading, { type: "failed", error: "offline" })).toMatchObject({ status: "failed", error: "offline" });
    expect(explainReducer(initialExplainState, { type: "loaded", view: explanationView(TEMPLATED) })).toBe(initialExplainState);
    expect(explainReducer(loading, { type: "request", context: "presenting" })).toBe(loading);
  });

  it("classifies failures, each with localized copy", () => {
    expect(classifyExplainError(new ApiError(0, {}))).toBe("offline");
    expect(classifyExplainError(new ApiError(404, {}))).toBe("unavailable");
    expect(classifyExplainError(new ApiError(500, {}))).toBe("error");
    for (const key of Object.values(EXPLAIN_FAILURE_COPY)) {
      expect(translate("en", key)).not.toBe(key);
      expect(translate("ur", key)).not.toBe(key);
    }
  });
});

describe("whyNextModel", () => {
  const plan = (over: Partial<AdaptivePlanWire> = {}): AdaptivePlanWire => ({
    next_action: { kind: "review", objective_code: "G4.N.1", rationale: [{ rule_id: "R3", note: "engine text" }] },
    weak_topics: [
      { objective_code: "G4.N.1", state: "at_risk", mastery: 0.4, active_misconceptions: [], reason: "retention at risk" },
      { objective_code: "G4.N.2", state: "in_progress", mastery: 0.5, active_misconceptions: [], reason: "still learning" },
    ],
    revision_due: ["G4.N.1"],
    practice: [],
    confidence: "medium",
    rationale: ["next: review"],
    ...over,
  });

  it("says what was chosen and why, in plain words, never the engine's English notes", () => {
    const model = whyNextModel(plan());
    expect(translate("en", model.choice)).toBe("Review an idea you learned before");
    expect(model.objective).toBe("G4.N.1");
    expect(model.reasons.map((r) => translate("en", r.key, r.params))).toEqual([
      "You might forget this idea soon.",
      "Ideas ready to review: 1",
      "Ideas that need more practice: 2",
    ]);
    expect(translate("en", model.certainty)).toBe("Your teacher is fairly sure.");
    expect(JSON.stringify(model)).not.toContain("engine text");
  });

  it("has a gentle reason when there is nothing weak or due", () => {
    const model = whyNextModel(plan({ next_action: { kind: "teach", objective_code: "G4.N.3" }, weak_topics: [], revision_due: [], confidence: "low" }));
    expect(model.reasons.map((r) => r.key)).toEqual(["student.whyNext.because.nextInOrder"]);
    expect(translate("en", model.certainty)).toBe("Your teacher is still getting to know you.");
  });

  it("handles completion and unknown kinds", () => {
    expect(whyNextModel(plan({ next_action: { kind: "complete", objective_code: null }, weak_topics: [], revision_due: [] })).reasons[0]!.key).toBe(
      "student.whyNext.because.allDone",
    );
    expect(whyNextModel(plan({ next_action: { kind: "teleport", objective_code: null } })).choice).toBe("student.whyNext.kind.other");
  });

  it("is localized in Urdu", () => {
    const model = whyNextModel(plan());
    expect(translate("ur", "student.whyNext.chose", { choice: translate("ur", model.choice) })).toContain("دہرانا");
  });
});
