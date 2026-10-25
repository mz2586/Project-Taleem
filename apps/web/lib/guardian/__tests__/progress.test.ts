import { describe, expect, it } from "vitest";

import type { ChildOverview } from "../types";
import { childDetailModel, formatChildSummary, weeklySummaryModel } from "../progress";
import { summary } from "./fixtures";

const EN = { locale: "en" as const, timeZone: "UTC" };
const UR = { locale: "ur" as const, timeZone: "UTC" };
const UR_NATIVE = { ...UR, digits: "native" as const };

function overview(over: Partial<ChildOverview> = {}): ChildOverview {
  return {
    student_ref: "stu_1",
    progress_overview: {
      objectives_mastered: 3,
      objectives_in_progress: 1,
      total_attempts: 1250,
      accuracy: 0.8,
      misconceptions_detected: 2,
      misconceptions_cleared: 1,
    },
    knowledge_growth: { "G4.N.1": 0.95 },
    attendance: { active_days: 5, day_indices: [] },
    learning_streaks: { current: 2, longest: 4, last_active_day: 1 },
    weekly_summary: { sessions: 3, attempts: 20, correct: 15, accuracy: 0.75 },
    learning_timeline: [{ session_id: "s1", objectives: ["G4.N.1"], attempts: 5, correct: 4, at: 1_761_134_400 }],
    assessment_history: { assessments: [{ id: "l1:formative", objective_code: "G4.N.1", type: "formative", item_count: 4 }] },
    ai_teacher_activity: { next_action: { kind: "review", objective_code: "G4.N.1" } },
    recommendations: [{ objective_code: "G4.N.2", reason: "learn" }],
    intervention_notifications: [
      { id: "revision-due", type: "revision_due", message: "You have 1 idea(s) to review today." },
      { id: "x", type: "brand_new", message: "Server sentence" },
    ],
    offline_sync_status: { last_synced_at: 1_761_134_400, is_stale: false, seconds_since_sync: 10, pending_is_device_reported: true },
    achievement_history: [
      { id: "mastery-G4.N.1", name: "Mastered G4.N.1", description: "You mastered a new idea.", earned_at: 1 },
      { id: "cleared-G4.N.1-2", name: "Cleared a misconception", description: "x", earned_at: 2 },
    ],
    ...over,
  };
}

describe("formatChildSummary", () => {
  it("formats with the locale's numbers, label: value", () => {
    const s = formatChildSummary(EN, summary("a", { objectives_mastered: 1234, objectives_in_progress: 2, total_attempts: 40, accuracy: 0.756 }));
    expect(s.mastered).toBe("Ideas mastered: 1,234");
    expect(s.accuracy).toBe("Correct answers: 76%");
    expect(s.masteryRatio).toBeCloseTo(1234 / 1236);
  });

  it("uses Urdu digits when asked, Western by default", () => {
    const western = formatChildSummary(UR, summary("a", { objectives_mastered: 12, total_attempts: 3, accuracy: 0.5 }));
    expect(western.mastered).toContain("12");
    const native = formatChildSummary(UR_NATIVE, summary("a", { objectives_mastered: 12, total_attempts: 3, accuracy: 0.5 }));
    expect(native.mastered).toContain("۱۲");
    expect(native.accuracy).toContain("۵۰");
  });

  it("has no accuracy before the first answer (0% would be a lie)", () => {
    const s = formatChildSummary(EN, summary("a"));
    expect(s.accuracy).toBeNull();
    expect(s.masteryRatio).toBe(0);
  });

  it("mentions attention and achievements only when there are some", () => {
    expect(formatChildSummary(EN, summary("a")).attention).toBeNull();
    const s = formatChildSummary(EN, summary("a", {}, { open_interventions: 2, achievements_count: 1 }));
    expect(s.attention).toBe("Needs attention: 2");
    expect(s.achievements).toBe("Achievements: 1");
  });

  it("describes sync freshness and streaks in words", () => {
    const stale = formatChildSummary(EN, summary("a"));
    expect(stale.syncStale).toBe(true);
    expect(stale.streak).toBe("No learning streak yet");
    const fresh = formatChildSummary(
      EN,
      summary("a", {}, { streak: { current: 3, longest: 3, last_active_day: 1 }, sync_status: { last_synced_at: 1, is_stale: false, seconds_since_sync: 1, pending_is_device_reported: true } }),
    );
    expect(fresh.sync).toBe("Up to date");
    expect(fresh.streak).toBe("Days in a row: 3");
  });
});

describe("weeklySummaryModel", () => {
  it("says a quiet week kindly", () => {
    expect(weeklySummaryModel(EN, { sessions: 0, attempts: 0, correct: 0, accuracy: 0 }).kind).toBe("quiet");
  });

  it("lists sessions, answers and correct answers with a percentage", () => {
    const model = weeklySummaryModel(EN, { sessions: 3, attempts: 20, correct: 15, accuracy: 0.75 });
    expect(model).toEqual({
      kind: "active",
      lines: ["Learning sessions: 3", "Questions answered: 20", "Correct: 15 (75%)"],
      encouragement: "Praise the effort, not only the right answers.",
    });
  });

  it("does not claim a correct count before any answer", () => {
    const model = weeklySummaryModel(EN, { sessions: 1, attempts: 0, correct: 0, accuracy: 0 });
    expect(model.kind === "active" && model.lines).toHaveLength(2);
  });

  it("is in Urdu for an Urdu interface", () => {
    const model = weeklySummaryModel(UR, { sessions: 3, attempts: 20, correct: 15, accuracy: 0.75 });
    expect(model.kind === "active" && model.lines[0]).toBe("پڑھائی کی نشستیں: 3");
  });
});

describe("childDetailModel", () => {
  it("formats the overview with locale numbers", () => {
    const model = childDetailModel(EN, overview());
    expect(model.hasProgress).toBe(true);
    expect(model.overview).toContain("Questions answered: 1,250");
    expect(model.overview).toContain("Correct answers: 80%");
    expect(model.overview).toContain("Mistakes fixed: 1");
  });

  it("reports no progress for a child with no answers, and no next step", () => {
    const model = childDetailModel(EN, overview({ progress_overview: { ...overview().progress_overview, total_attempts: 0 } }));
    expect(model.hasProgress).toBe(false);
    expect(model.nextStep).toBeNull();
    expect(model.overview.some((l) => l.includes("%"))).toBe(false);
  });

  it("rebuilds server English sentences from their kind, keeping unknown ones as marked content", () => {
    const model = childDetailModel(UR, overview());
    expect(model.attention[0]).toEqual({ text: "کچھ خیالات دہرانے کا وقت ہے۔" });
    expect(model.attention[1]).toEqual({ text: "دیکھنے کی چیز", extra: { text: "Server sentence", content: true } });
    expect(model.achievements[0]).toEqual({ text: "ایک خیال سیکھ لیا", extra: { text: "G4.N.1", content: true } });
    expect(model.recommendations[0]!.text).toBe("اگلا سیکھیں");
  });

  it("names the AI teacher's next step in words", () => {
    expect(childDetailModel(EN, overview()).nextStep).toEqual({
      text: "Review an idea learned before",
      extra: { text: "G4.N.1", content: true },
    });
  });

  it("dates timeline entries and the last sync in the interface locale", () => {
    const model = childDetailModel(EN, overview());
    expect(model.timeline[0]!.text).toBe("Oct 22, 2025 — answers: 5, correct: 4");
    expect(model.sync.lastSync).toBe("Last update: Oct 22, 2025");
    expect(model.knowledge[0]).toMatchObject({ objective: { text: "G4.N.1" }, value: "95%" });
    expect(model.assessments[0]!.text).toBe("Practice check — questions: 4");
  });

  it("tolerates a sparse response", () => {
    const sparse = overview({
      knowledge_growth: {},
      learning_timeline: [],
      recommendations: [],
      intervention_notifications: [],
      achievement_history: [],
      assessment_history: {},
      ai_teacher_activity: {},
      offline_sync_status: { last_synced_at: null, is_stale: true, seconds_since_sync: null, pending_is_device_reported: true },
    });
    const model = childDetailModel(EN, sparse);
    expect(model.timeline).toEqual([]);
    expect(model.assessments).toEqual([]);
    expect(model.nextStep).toBeNull();
    expect(model.sync).toMatchObject({ stale: true, lastSync: null });
  });
});

describe("childDetailModel — lesson titles", () => {
  const titles = { "G4.N.1": { ur: "کسریں", en: "Fractions" }, "G4.N.2": { ur: "", en: "Decimals" } };

  it("names every objective by its lesson title, in the guardian's language first", () => {
    const model = childDetailModel(EN, overview({ objective_titles: titles }));
    expect(model.knowledge[0]?.objective).toEqual({ text: "Fractions", content: true, locale: "en" });
    expect(model.nextStep?.extra).toEqual({ text: "Fractions", content: true, locale: "en" });
    expect(model.recommendations[0]?.extra).toEqual({ text: "Decimals", content: true, locale: "en" });
    expect(model.assessments[0]?.extra?.text).toBe("Fractions");
    expect(model.achievements[0]?.extra?.text).toBe("Fractions");
    const ur = childDetailModel(UR, overview({ objective_titles: titles }));
    expect(ur.knowledge[0]?.objective).toEqual({ text: "کسریں", content: true, locale: "ur" });
    expect(JSON.stringify(ur)).not.toContain("G4.N.1");
  });

  it("falls back to the code only for a server that sends no titles", () => {
    expect(childDetailModel(EN, overview()).knowledge[0]?.objective).toEqual({ text: "G4.N.1", content: true });
  });
});
