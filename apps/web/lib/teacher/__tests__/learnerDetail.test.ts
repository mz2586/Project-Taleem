import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import { ApiError } from "../../student/types";
import { learnerDetailView, learnerPanelReducer, type ClassLearnerDetail } from "../learnerDetail";

const detail: ClassLearnerDetail = {
  student_ref: "stu_1",
  display_name: "Zara",
  class_id: "cls_1",
  joined_at: 100,
  confidence: "low",
  next_action: { kind: "teach", objective_code: "MATH-G4-FR-01", reasons: [{ code: "ready_for_new", params: { objective: "MATH-G4-FR-01" } }] },
  recommendations: [
    {
      kind: "teach",
      objective_code: "MATH-G4-FR-01",
      is_next_action: true,
      reasons: [
        { code: "ready_for_new", params: { objective: "MATH-G4-FR-01", prerequisites: 0 } },
        { code: "diagnostic_placement", params: { objective: "MATH-G4-FR-01", status: "uncertain", correct: 0, incorrect: 1, prior: 0.35, uncertainty: 0.7 } },
      ],
      confidence: "low",
      mastery: 0.35,
      uncertainty: 0.7,
      evidence: { practice: 0, practice_correct: 0, diagnostic: 1, diagnostic_correct: 0 },
      estimate_source: "diagnostic",
    },
  ],
  placement: { placed: true, placement_id: "placement-1", objectives_secure: 0, objectives_not_yet: 0, objectives_uncertain: 1 },
};

describe("learnerDetailView", () => {
  it("shows the reasons with their numbers and the starting-questions summary", () => {
    const view = learnerDetailView(detail);
    const lines = view.recommendations[0]!.reasons.map((r) => translate("en", r.key, r.params));
    expect(lines[1]).toBe(
      "MATH-G4-FR-01: the starting questions were not conclusive (0 right, 1 wrong; estimate 35%, uncertainty 70%).",
    );
    expect(translate("en", view.placement.key, view.placement.params)).toBe("Starting questions: known 0, not yet 0, unclear 1");
    expect(translate("ur", view.placement.key, view.placement.params)).toContain("شروع کے سوال");
  });

  it("says plainly when no starting questions were answered", () => {
    expect(learnerDetailView({ ...detail, placement: null }).placement.key).toBe("teacher.learner.noPlacement");
  });
});

describe("learnerPanelReducer", () => {
  it("loads on every open — visibility is live, an earlier answer is never reused", () => {
    const shown = learnerPanelReducer({ status: "loading" }, { type: "loaded", detail });
    expect(shown.status).toBe("shown");
    expect(learnerPanelReducer(shown, { type: "open" })).toEqual({ status: "loading" });
    expect(learnerPanelReducer(shown, { type: "close" })).toEqual({ status: "closed" });
  });

  it("treats a 404 (sharing stopped) as hidden, not as an error, and never keeps old reasons", () => {
    const hidden = learnerPanelReducer({ status: "loading" }, { type: "failed", error: new ApiError(404, { code: "NOT_FOUND" }) });
    expect(hidden).toEqual({ status: "hidden" });
    expect(translate("en", "teacher.learner.hidden")).toMatch(/stopped sharing/);
  });

  it("separates offline from other failures, and ignores stray results", () => {
    expect(learnerPanelReducer({ status: "loading" }, { type: "failed", error: new ApiError(0, {}) })).toEqual({
      status: "failed",
      error: "teacher.errors.offline",
    });
    expect(learnerPanelReducer({ status: "loading" }, { type: "failed", error: new ApiError(500, {}) })).toEqual({
      status: "failed",
      error: "teacher.learner.error",
    });
    expect(learnerPanelReducer({ status: "closed" }, { type: "loaded", detail })).toEqual({ status: "closed" });
  });
});
