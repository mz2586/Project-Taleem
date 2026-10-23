// The teacher's learner panel — "Why this next?" for one learner of the class. Pure; unit-tested.
//
// Contract: GET /v1/school/classes/{classId}/learners/{studentRef} (school.openapi.yaml,
// `ClassLearnerDetail`). The server shows a learner only while their guardian shares progress, checked
// live on every request; a learner who stopped sharing is a 404 exactly like one who never existed.
// The panel says so plainly ("not available — the guardian may have stopped sharing") and never
// keeps showing reasons it loaded earlier.

import type { MessageKey } from "../i18n/messages";
import {
  recommendationViews,
  type ExplainedRecommendationWire,
  type PlacementSummaryWire,
  type ReasonLine,
  type ReasonWire,
  type RecommendationView,
} from "../learning/rationale";
import { teacherFailure } from "./errors";

export interface ClassLearnerDetail {
  student_ref: string;
  display_name: string;
  class_id: string;
  joined_at: number;
  confidence: string;
  next_action: { kind: string; objective_code: string | null; reasons: ReasonWire[] } | null;
  recommendations: ExplainedRecommendationWire[];
  placement: PlacementSummaryWire | null;
}

export interface LearnerDetailView {
  recommendations: RecommendationView[];
  /** The starting-questions summary, or "none answered". */
  placement: ReasonLine;
}

export function learnerDetailView(detail: ClassLearnerDetail): LearnerDetailView {
  const p = detail.placement;
  return {
    recommendations: recommendationViews(detail.recommendations),
    placement:
      p && p.placed
        ? {
            key: "teacher.learner.placement",
            params: { secure: p.objectives_secure, notYet: p.objectives_not_yet, uncertain: p.objectives_uncertain },
          }
        : { key: "teacher.learner.noPlacement" },
  };
}

export type LearnerPanelState =
  | { status: "closed" }
  | { status: "loading" }
  | { status: "shown"; view: LearnerDetailView }
  | { status: "hidden" }
  | { status: "failed"; error: MessageKey };

export type LearnerPanelAction =
  | { type: "open" }
  | { type: "loaded"; detail: ClassLearnerDetail }
  | { type: "failed"; error: unknown }
  | { type: "close" };

export function learnerPanelReducer(state: LearnerPanelState, action: LearnerPanelAction): LearnerPanelState {
  switch (action.type) {
    case "open":
      // Always reload on open: visibility is live, so an earlier answer is never reused.
      return { status: "loading" };
    case "loaded":
      return state.status === "loading" ? { status: "shown", view: learnerDetailView(action.detail) } : state;
    case "failed": {
      if (state.status !== "loading") return state;
      const failure = teacherFailure(action.error);
      if (failure === "not-available") return { status: "hidden" };
      return { status: "failed", error: failure === "offline" ? "teacher.errors.offline" : "teacher.learner.error" };
    }
    case "close":
      return { status: "closed" };
  }
}
