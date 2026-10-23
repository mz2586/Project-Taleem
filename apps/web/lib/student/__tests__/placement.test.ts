import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import {
  answerReducer,
  classifyAnswerError,
  initialAnswerState,
  PLACEMENT_FAILURE_COPY,
  PLACEMENT_HREF,
  PLACEMENT_SCREEN_COPY,
  placementEntry,
  placementScreen,
  type PlacementWire,
} from "../placement";
import { ApiError } from "../types";

const base: PlacementWire = {
  student_ref: "s1",
  status: "available",
  reason: null,
  placement_id: null,
  items_used: 0,
  max_items: 12,
  stop_reason: null,
  placement_uncertainty: 1,
  start_objective: null,
  next_item: {
    item_ref: "p1-one-of-four",
    objective_code: "MATH-G4-FR-01",
    prompt: { ur: "کونسی کسر؟", en: "Which fraction?" },
    options: ["1/4", "4/1", "1"],
  },
  objectives: [],
};

describe("placementEntry (Today)", () => {
  it("offers the starting questions only when a placement is possible", () => {
    expect(placementEntry(base)).toEqual({
      title: "student.today.placementTitle",
      body: "student.today.placementBody",
      action: "student.today.placementStart",
      href: PLACEMENT_HREF,
    });
    expect(placementEntry({ ...base, status: "in_progress", items_used: 2 })?.action).toBe("student.today.placementContinue");
  });

  it("shows nothing when nothing is published, the learner has history, or it is done", () => {
    expect(placementEntry({ ...base, status: "unavailable", reason: "no_published_items", next_item: null })).toBeNull();
    expect(placementEntry({ ...base, status: "not_eligible", reason: "has_history", next_item: null })).toBeNull();
    expect(placementEntry({ ...base, status: "completed", next_item: null })).toBeNull();
    expect(placementEntry({ ...base, next_item: null })).toBeNull();
    expect(placementEntry(null)).toBeNull();
  });
});

describe("placementScreen", () => {
  it("asks the question in the interface language, numbered against the cap", () => {
    const screen = placementScreen({ ...base, items_used: 2 }, "en");
    expect(screen).toEqual({
      kind: "question",
      question: {
        itemRef: "p1-one-of-four",
        prompt: "Which fraction?",
        promptLocale: "en",
        options: [
          { index: 0, label: "1/4" },
          { index: 1, label: "4/1" },
          { index: 2, label: "1" },
        ],
        number: 3,
        max: 12,
      },
    });
    const ur = placementScreen(base, "ur");
    expect(ur.kind === "question" && ur.question.prompt).toBe("کونسی کسر؟");
  });

  it("falls back to the authored language, marked as such", () => {
    const screen = placementScreen({ ...base, next_item: { ...base.next_item!, prompt: { ur: "", en: "Only English" } } }, "ur");
    expect(screen.kind === "question" && screen.question).toMatchObject({ prompt: "Only English", promptLocale: "en" });
  });

  it("has an honest screen for every other state, in both languages", () => {
    expect(placementScreen({ ...base, status: "completed", next_item: null }, "en").kind).toBe("done");
    expect(placementScreen({ ...base, status: "unavailable", next_item: null }, "en").kind).toBe("unavailable");
    expect(placementScreen({ ...base, status: "not_eligible", next_item: null }, "en").kind).toBe("not-eligible");
    for (const copy of Object.values(PLACEMENT_SCREEN_COPY)) {
      for (const key of [copy.title, copy.body]) {
        expect(translate("en", key)).not.toBe(key);
        expect(translate("ur", key)).not.toBe(key);
      }
    }
  });

  it("never tells the child right or wrong", () => {
    const text = ["thanks", "intro", "doneBody"].map((k) => translate("en", `student.placement.${k}` as "student.placement.thanks"));
    for (const line of text) expect(line).not.toMatch(/\b(correct|wrong|right)\b/i);
  });
});

describe("answering", () => {
  it("sends one answer at a time", () => {
    const saving = answerReducer(initialAnswerState, { type: "submit", option: 1 });
    expect(saving).toEqual({ status: "saving", option: 1 });
    expect(answerReducer(saving, { type: "submit", option: 0 })).toBe(saving);
    expect(answerReducer(saving, { type: "saved" })).toEqual(initialAnswerState);
    expect(answerReducer(saving, { type: "failed", error: "offline" })).toEqual({ status: "failed", error: "offline" });
    expect(answerReducer(initialAnswerState, { type: "failed", error: "error" })).toBe(initialAnswerState);
  });

  it("reloads when the server has moved on, and says offline honestly", () => {
    expect(classifyAnswerError(new ApiError(409, { code: "PLACEMENT_ITEM_MISMATCH" }))).toBe("reload");
    expect(classifyAnswerError(new ApiError(0, {}))).toBe("offline");
    expect(classifyAnswerError(new ApiError(500, {}))).toBe("error");
    expect(classifyAnswerError(new Error("x"))).toBe("error");
    for (const key of Object.values(PLACEMENT_FAILURE_COPY)) {
      expect(translate("ur", key)).not.toBe(key);
    }
  });
});
