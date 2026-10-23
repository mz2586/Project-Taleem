import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import { whyNextModel, type AdaptivePlanWire } from "../aiTeacher";

// The plan as core-api returns it now: structured `reasons` beside the English engine notes.
const plan: AdaptivePlanWire = {
  next_action: {
    kind: "teach",
    objective_code: "MATH-G4-FR-01",
    rationale: [{ rule_id: "select_eligible", note: "MATH-G4-FR-01 state=not_started" }],
    reasons: [
      { code: "ready_for_new", params: { objective: "MATH-G4-FR-01", prerequisites: 0 } },
      { code: "diagnostic_placement", params: { objective: "MATH-G4-FR-01", status: "not_yet", correct: 0, incorrect: 2 } },
    ],
  },
  weak_topics: [
    // An English `reason` the client must NOT match on any more.
    { objective_code: "MATH-G4-FR-01", state: "in_progress", mastery: 0.2, active_misconceptions: [], reason: "retention at risk" },
  ],
  revision_due: [],
  practice: [],
  confidence: "low",
  rationale: ["next: teach"],
};

describe("whyNextModel with structured reasons", () => {
  it("renders the server's reason codes in the child's words, never the English notes", () => {
    const model = whyNextModel(plan);
    expect(model.reasons.map((r) => translate("en", r.key, r.params))).toEqual([
      "You are ready for a new idea.",
      "Your starting questions showed this is a good place to begin.",
      "Ideas that need more practice: 1",
    ]);
    const json = JSON.stringify(model);
    expect(json).not.toContain("state=not_started");
    expect(json).not.toContain("retention");
  });

  it("is localized in Urdu", () => {
    const model = whyNextModel(plan);
    expect(translate("ur", model.reasons[0]!.key)).toBe("آپ ایک نئے خیال کے لیے تیار ہیں۔");
  });

  it("without structured reasons, reads the weak topic's state — not its English reason", () => {
    const old = whyNextModel({ ...plan, next_action: { kind: "continue", objective_code: "MATH-G4-FR-01" } });
    // state in_progress -> still learning, even though the English text said "retention at risk".
    expect(old.reasons[0]!.key).toBe("student.whyNext.because.stillLearning");
    const misconception = whyNextModel({
      ...plan,
      next_action: { kind: "remediate", objective_code: "MATH-G4-FR-01" },
      weak_topics: [{ ...plan.weak_topics[0]!, active_misconceptions: ["MC-1"], reason: "?" }],
    });
    expect(misconception.reasons[0]!.key).toBe("student.whyNext.because.misconception");
  });
});
