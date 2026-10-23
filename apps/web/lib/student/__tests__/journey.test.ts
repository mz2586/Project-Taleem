import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import {
  classifyLoadError,
  emptyKnowledge,
  ENDING_COPY,
  gradeLabel,
  masteryStateKey,
  needsTodayToExplain,
  orOnNotFound,
  planOutcome,
  teachFailureEnding,
  TODAY_EMPTY_COPY,
  todayModel,
  type SessionEnding,
} from "../journey";
import { ApiError, type DecisionView, type KnowledgeView, type ProgressView, type TodayView } from "../types";

// What core-api returns for a learner while NO lesson is published (see journey.ts header).
const TODAY_NOTHING_PUBLISHED: TodayView = {
  next_action: { objective_code: null, reason: "complete" },
  mastery_summary: { mastered: 0, in_progress: 0, total: 0 },
  revision_due_count: 0,
};
const COMPLETE: DecisionView = { decision: "complete", objective_code: null, rationale: ["no eligible objective remains"] };

function progress(over: Partial<ProgressView> = {}): ProgressView {
  return {
    student_ref: "s",
    objectives_mastered: 0,
    objectives_in_progress: 0,
    total_attempts: 0,
    accuracy: 0,
    misconceptions_detected: 0,
    misconceptions_cleared: 0,
    reviews_scheduled: 0,
    events_by_type: {},
    objective_mastery: {},
    ...over,
  };
}

const KNOWLEDGE: KnowledgeView = {
  student_ref: "s",
  objectives: {
    A: { mastery: 0.95, uncertainty: 0.1, state: "mastered" },
    B: { mastery: 0.4, uncertainty: 0.3, state: "in_progress" },
    C: { mastery: 0.5, uncertainty: 0.3, state: "needs_review" },
  },
};

describe("classifyLoadError", () => {
  it("calls only a network failure offline", () => {
    expect(classifyLoadError(new ApiError(0, { code: "OFFLINE" }))).toBe("offline");
  });
  it("treats a 401 that survived refresh as signed out, not offline", () => {
    expect(classifyLoadError(new ApiError(401, {}))).toBe("signed-out");
  });
  it("treats 403, 5xx and non-API errors as errors", () => {
    expect(classifyLoadError(new ApiError(403, {}))).toBe("error");
    expect(classifyLoadError(new ApiError(500, {}))).toBe("error");
    expect(classifyLoadError(new Error("boom"))).toBe("error");
  });
  it("names a withdrawn consent and a paused account instead of a retryable error", () => {
    // What the per-request learner gate returns once a guardian withdraws consent or pauses the
    // child; the browser journey found Today showing "couldn't load, try again" here.
    expect(classifyLoadError(new ApiError(403, { code: "CONSENT_REQUIRED" }))).toBe("consent");
    expect(classifyLoadError(new ApiError(403, { code: "LEARNER_INACTIVE" }))).toBe("paused");
    expect(classifyLoadError(new ApiError(403, { code: "FORBIDDEN" }))).toBe("error");
  });
});

describe("orOnNotFound", () => {
  it("substitutes the fallback for a 404 (a brand-new learner has no knowledge yet)", async () => {
    const fallback = emptyKnowledge("s");
    await expect(orOnNotFound(Promise.reject(new ApiError(404, {})), fallback)).resolves.toBe(fallback);
  });
  it("passes other failures and successes through", async () => {
    await expect(orOnNotFound(Promise.reject(new ApiError(0, {})), null)).rejects.toBeInstanceOf(ApiError);
    await expect(orOnNotFound(Promise.resolve(1), 0)).resolves.toBe(1);
  });
});

describe("todayModel", () => {
  it("says nothing is published when the backend has no lessons — and offers no Start", () => {
    const m = todayModel({ today: TODAY_NOTHING_PUBLISHED, knowledge: emptyKnowledge("s"), progress: progress() });
    expect(m.kind).toBe("nothing-published");
    expect(m.canStart).toBe(false);
    expect(m.total).toBe(0);
    expect(m.accuracy).toBeNull();
  });

  it("offers a first lesson when lessons exist but none is started", () => {
    const today: TodayView = { ...TODAY_NOTHING_PUBLISHED, next_action: { objective_code: "A", reason: "learn" } };
    const m = todayModel({ today, knowledge: emptyKnowledge("s"), progress: progress() });
    expect(m.kind).toBe("first-lesson");
    expect(m.canStart).toBe(true);
  });

  it("summarises an in-progress learner", () => {
    const today: TodayView = {
      next_action: { objective_code: "B", reason: "learn" },
      mastery_summary: { mastered: 1, in_progress: 1, total: 3 },
      revision_due_count: 1,
    };
    const m = todayModel({ today, knowledge: KNOWLEDGE, progress: progress({ total_attempts: 4, accuracy: 0.75 }) });
    expect(m).toMatchObject({ kind: "learning", canStart: true, mastered: 1, total: 3, dueCount: 1, accuracy: 0.75 });
    expect(m.masteryValue).toBeCloseTo(1 / 3);
  });

  it("calls a complete plan with recorded objectives all caught up, not empty", () => {
    const today: TodayView = {
      next_action: { objective_code: null, reason: "complete" },
      mastery_summary: { mastered: 3, in_progress: 0, total: 3 },
      revision_due_count: 0,
    };
    const m = todayModel({ today, knowledge: KNOWLEDGE, progress: null });
    expect(m.kind).toBe("all-caught-up");
    expect(m.canStart).toBe(false);
  });

  it("without the aggregate, still lets the learner try (the session then explains)", () => {
    expect(todayModel({ today: null, knowledge: null, progress: null })).toMatchObject({
      kind: "first-lesson",
      canStart: true,
    });
    expect(todayModel({ today: null, knowledge: KNOWLEDGE, progress: null }).kind).toBe("learning");
  });

  it("has copy for every empty kind in every locale", () => {
    for (const copy of Object.values(TODAY_EMPTY_COPY)) {
      expect(translate("en", copy.title)).not.toBe(copy.title);
      expect(translate("ur", copy.body)).not.toBe(copy.body);
    }
  });
});

describe("planOutcome", () => {
  it("teaches a teachable decision with an objective, as before", () => {
    for (const decision of ["teach", "continue", "review", "remediate", "diagnose"] as const) {
      expect(planOutcome({ decision, objective_code: "X", rationale: [] }, { taughtThisSession: false })).toEqual({
        kind: "teach",
        objective: "X",
      });
    }
  });

  it("escalates", () => {
    expect(planOutcome({ decision: "escalate", objective_code: null, rationale: [] }, { taughtThisSession: true })).toEqual({
      kind: "escalate",
    });
  });

  it("celebrates only when a lesson was actually taught", () => {
    expect(planOutcome(COMPLETE, { taughtThisSession: true })).toEqual({ kind: "end", ending: "finished" });
  });

  it("says there is nothing to learn when :next is complete before any lesson and nothing is published", () => {
    expect(planOutcome(COMPLETE, { taughtThisSession: false, today: TODAY_NOTHING_PUBLISHED })).toEqual({
      kind: "end",
      ending: "nothing-to-learn",
    });
  });

  it("distinguishes 'mastered everything' from 'nothing published'", () => {
    const today: TodayView = { ...TODAY_NOTHING_PUBLISHED, mastery_summary: { mastered: 4, in_progress: 0, total: 4 } };
    expect(planOutcome(COMPLETE, { taughtThisSession: false, today })).toEqual({ kind: "end", ending: "all-mastered" });
  });

  it("falls back to a neutral 'nothing new' when it cannot tell", () => {
    expect(planOutcome(COMPLETE, { taughtThisSession: false, today: null })).toEqual({ kind: "end", ending: "caught-up" });
    expect(needsTodayToExplain(COMPLETE, false)).toBe(true);
    expect(needsTodayToExplain(COMPLETE, true)).toBe(false);
  });

  it("treats rest before any lesson as a break", () => {
    const rest: DecisionView = { decision: "rest", objective_code: null, rationale: [] };
    expect(planOutcome(rest, { taughtThisSession: false })).toEqual({ kind: "end", ending: "rest" });
    expect(needsTodayToExplain(rest, false)).toBe(false);
  });

  it("does not teach a teachable decision without an objective", () => {
    const odd: DecisionView = { decision: "teach", objective_code: null, rationale: [] };
    expect(planOutcome(odd, { taughtThisSession: true })).toEqual({ kind: "end", ending: "finished" });
  });

  it("maps a missing lesson on :teach to 'unavailable', other failures to none", () => {
    expect(teachFailureEnding(new ApiError(404, { detail: "lesson not found" }))).toBe("unavailable");
    expect(teachFailureEnding(new ApiError(0, {}))).toBeNull();
  });

  it("has copy for every ending in every locale", () => {
    const endings: SessionEnding[] = ["finished", "rest", "nothing-to-learn", "all-mastered", "caught-up", "unavailable"];
    for (const ending of endings) {
      for (const locale of ["en", "ur"] as const) {
        expect(translate(locale, ENDING_COPY[ending].title)).not.toBe(ENDING_COPY[ending].title);
      }
    }
  });
});

describe("labels", () => {
  it("maps mastery states, defaulting unknown to not started", () => {
    expect(translate("en", masteryStateKey("mastered"))).toBe("Mastered");
    expect(translate("en", masteryStateKey("weird"))).toBe("Not started");
  });

  it("labels grades, with 0 as kindergarten", () => {
    expect(gradeLabel(0)).toEqual({ key: "student.profile.gradeKg" });
    const g = gradeLabel(4)!;
    expect(translate("en", g.key, g.params)).toBe("Grade 4");
    expect(gradeLabel(undefined)).toBeNull();
  });
});
