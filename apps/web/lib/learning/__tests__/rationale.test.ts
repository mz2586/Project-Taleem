import { describe, expect, it } from "vitest";

import { SUPPORTED_LOCALES } from "../../i18n/config";
import { translate } from "../../i18n/translate";
import {
  pct,
  REASON_CODES,
  reasonLine,
  reasonLines,
  recommendationView,
  recommendationViews,
  type ExplainedRecommendationWire,
  type ReasonWire,
} from "../rationale";

// The server's `ReasonCode` enum (services/core-api learning/domain/decision.py). The backend test
// test_explainable_recommendations.py pins the same set: renaming a code breaks both.
const SERVER_CODES = [
  "safety_gate",
  "review_due",
  "misconception_active",
  "high_uncertainty",
  "ready_for_new",
  "mastery_below_threshold",
  "prerequisite_gap",
  "diagnostic_placement",
  "placed_above",
  "retention_at_risk",
  "repeated_failure",
  "mastery_reached",
  "all_mastered",
];

const SAMPLE: Record<string, ReasonWire["params"]> = {
  review_due: { objective: "G4.N.1", days_overdue: 2.4, due_count: 3 },
  misconception_active: { objective: "G4.N.1", misconception: "MC-BIG-DENOM", evidence_count: 2 },
  high_uncertainty: { objective: "G4.N.2", uncertainty: 0.7 },
  ready_for_new: { objective: "G4.N.3", prerequisites: 1 },
  mastery_below_threshold: { objective: "G4.N.1", mastery: 0.42, threshold: 0.85 },
  prerequisite_gap: { objective: "G4.N.4", prereq: "G4.N.3" },
  diagnostic_placement: { objective: "G4.N.1", status: "not_yet", correct: 0, incorrect: 2, prior: 0.2, uncertainty: 0.49 },
  placed_above: { count: 2 },
  retention_at_risk: { objective: "G4.N.1", mastery: 0.55 },
  repeated_failure: { objective: "G4.N.1", consecutive_failures: 4 },
  mastery_reached: { objective: "G4.N.1", mastery: 0.9, threshold: 0.85 },
};

function render(locale: (typeof SUPPORTED_LOCALES)[number], reason: ReasonWire, audience: "student" | "adult"): string {
  const line = reasonLine(reason, audience);
  return translate(locale, line.key, line.params);
}

describe("reason codes", () => {
  it("are exactly the server's stable codes", () => {
    expect([...REASON_CODES].sort()).toEqual([...SERVER_CODES].sort());
  });

  it("have plain-language text for every code, audience and language, with nothing left unfilled", () => {
    for (const code of REASON_CODES) {
      for (const audience of ["student", "adult"] as const) {
        for (const locale of SUPPORTED_LOCALES) {
          const text = render(locale, { code, params: SAMPLE[code] ?? {} }, audience);
          expect(text, `${code}/${audience}/${locale}`).not.toMatch(/common\.rationale|\{\w+\}|undefined|NaN/);
          expect(text.trim()).not.toBe("");
        }
      }
    }
  });

  it("gives the adult the numbers behind the reason, as whole percentages", () => {
    expect(render("en", { code: "mastery_below_threshold", params: SAMPLE.mastery_below_threshold }, "adult")).toBe(
      "G4.N.1: mastery 42% is below the 85% goal.",
    );
    expect(render("en", { code: "review_due", params: SAMPLE.review_due }, "adult")).toBe(
      "G4.N.1: a review is due (2 days overdue; reviews due: 3).",
    );
    const placed = render("en", { code: "diagnostic_placement", params: SAMPLE.diagnostic_placement }, "adult");
    expect(placed).toContain("0 right, 2 wrong");
    expect(placed).toContain("uncertainty 49%");
  });

  it("explains an inferred placement by the objective that implied it", () => {
    const line = reasonLine(
      { code: "diagnostic_placement", params: { objective: "G4.N.1", status: "secure", inferred_from: "G4.N.2" } },
      "adult",
    );
    expect(line.key).toBe("common.rationale.adult.diagnostic_placement.inferred");
    expect(translate("en", line.key, line.params)).toContain("G4.N.2");
  });

  it("keeps the child's words warm and number-free", () => {
    expect(render("en", { code: "mastery_below_threshold", params: SAMPLE.mastery_below_threshold }, "student")).toBe(
      "You are still learning this idea.",
    );
    for (const status of ["secure", "not_yet", "uncertain", "something-new"]) {
      const text = render("en", { code: "diagnostic_placement", params: { status } }, "student");
      expect(text).toMatch(/starting questions/);
    }
    expect(render("ur", { code: "ready_for_new" }, "student")).toContain("نئے خیال");
  });

  it("never shows an unknown code or bad params raw", () => {
    expect(reasonLine({ code: "brand_new_reason", params: { x: 1 } }, "student").key).toBe("common.rationale.student.other");
    expect(reasonLine({ code: "brand_new_reason" }, "adult").key).toBe("common.rationale.adult.other");
    const text = render("en", { code: "mastery_below_threshold", params: { objective: "X", mastery: "oops" } }, "adult");
    expect(text).toBe("X: mastery 0% is below the 0% goal.");
  });

  it("drops repeated sentences and junk entries", () => {
    const lines = reasonLines(
      [{ code: "ready_for_new", params: { objective: "A" } }, { code: "ready_for_new", params: { objective: "A" } }, null as unknown as ReasonWire],
      "student",
    );
    expect(lines).toHaveLength(1);
    expect(reasonLines(undefined, "adult")).toEqual([]);
  });

  it("clamps percentages", () => {
    expect([pct(-1), pct(0.494), pct(2), pct(null), pct(Number.NaN)]).toEqual([0, 49, 100, 0, 0]);
  });
});

describe("recommendationView", () => {
  const rec: ExplainedRecommendationWire = {
    kind: "teach",
    objective_code: "G4.N.1",
    is_next_action: true,
    reasons: [
      { code: "ready_for_new", params: { objective: "G4.N.1", prerequisites: 0 } },
      { code: "diagnostic_placement", params: SAMPLE.diagnostic_placement },
    ],
    confidence: "low",
    mastery: 0.2,
    uncertainty: 0.49,
    state: "not_started",
    evidence: { practice: 0, practice_correct: 0, diagnostic: 2, diagnostic_correct: 0, last_at: 10 },
    estimate_source: "diagnostic",
  };

  it("shows why, how sure, and the answers behind it — diagnostic and practice apart", () => {
    const view = recommendationView(rec);
    expect(view.isNext).toBe(true);
    expect(translate("en", view.kind)).toBe("Learn a new objective");
    expect(view.reasons).toHaveLength(2);
    expect(translate("en", view.confidence)).toMatch(/low/);
    expect(translate("en", view.uncertainty!.key, view.uncertainty!.params)).toBe("Uncertainty: 49%");
    expect(translate("en", view.evidence.key, view.evidence.params)).toBe(
      "Answers behind this: practice 0 (0 right), starting questions 2 (0 right).",
    );
    expect(translate("en", view.source)).toBe("Based on the starting questions only");
    expect(translate("ur", view.evidence.key, view.evidence.params)).toContain("شروع کے سوال");
  });

  it("is honest with no evidence or an unknown kind", () => {
    const view = recommendationView({ ...rec, kind: "teleport", confidence: "?", uncertainty: null, evidence: undefined, estimate_source: undefined });
    expect(view.kind).toBe("common.rationale.kind.other");
    expect(view.confidence).toBe("common.rationale.confidence.low");
    expect(view.uncertainty).toBeNull();
    expect(view.evidence.key).toBe("common.rationale.evidence.none");
    expect(view.source).toBe("common.rationale.source.none");
  });

  it("bounds the list and tolerates a missing one", () => {
    expect(recommendationViews(Array.from({ length: 9 }, () => rec))).toHaveLength(6);
    expect(recommendationViews(undefined)).toEqual([]);
  });
});
