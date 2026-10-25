// The progression view models (PROGRESSION_AND_EXAMINATION_CONTRACT): state mapping, "practice done"
// never read as "mastered", sitting resume, answer bodies per kind, the finish view, the record, the
// offline line, and that nothing claims to be a certificate.
import { describe, expect, it } from "vitest";

import { formatPercent } from "../../i18n/format";
import { progressionEn, progressionUr } from "../../i18n/messages/progression";
import { createTranslator } from "../../i18n/translate";
import { emptyPairDraft, fillAnswer, orderAnswer, orderTap, pairsAnswer, tapLeft, tapRight } from "../../student/itemAnswer";
import { ApiError } from "../../student/types";
import { checkAnswerBody, PROGRESSION_PATHS } from "../api";
import {
  forgetSitting,
  readStoredSitting,
  rememberSitting,
  resumePlan,
  sittingStorageKey,
  type KeyValueStore,
} from "../sitting";
import type { PathWire, RecordWire } from "../types";
import {
  checkEntry,
  checkFailure,
  checkOfflineMessage,
  guardianRecordLinks,
  LEARNER_RECORD_LINKS,
  lessonBadge,
  questionOf,
  recordView,
  resultView,
  unitBadge,
  type ViewContext,
} from "../view";
import { academicRecord, afterAnswer, checkResult, lessonState, pathView, sittingView, toSeconds, unitState } from "../wire";

type Locale = "ur" | "en";
const ctxFor = (locale: Locale): ViewContext => ({
  t: createTranslator(locale),
  locale,
  formatPercent: (r) => formatPercent(r, locale),
});
const PREF = ["en", "ur"];

const PATH: PathWire = {
  grade: 4,
  subjects: [
    {
      subject_key: "math",
      title: { ur: "ریاضی", en: "Mathematics" },
      units: [
        {
          unit_key: "u1",
          title: { en: "Fractions" },
          state: "ready_for_check",
          lessons: [
            { lesson_id: "L1", objective_code: "M4.F.1", title: { en: "Halves" }, state: "practised" },
            { lesson_id: "L2", objective_code: "M4.F.2", title: { en: "Quarters" }, state: "mastered" },
            { lesson_id: "L3", objective_code: "M4.F.3", title: null, state: "weird" },
          ],
          check: { available: true, best_score: 60, passed: false, last_sitting_id: "s0" },
        },
        { unit_key: "u2", title: { en: "Decimals" }, state: "not_started", lessons: [], check: { available: false } },
      ],
    },
  ],
  next_step: { kind: "lesson", lesson_id: "L1", title: { en: "Halves" } },
};

describe("state mapping", () => {
  it("maps lesson states, with unknown reading as not started (never mastered)", () => {
    expect(lessonState("practised")).toBe("practised");
    expect(lessonState("practiced")).toBe("practised");
    expect(lessonState("completed")).toBe("practised");
    expect(lessonState("mastered")).toBe("mastered");
    expect(lessonState("in_progress")).toBe("in_progress");
    expect(lessonState("surprise")).toBe("not_started");
    expect(lessonState(null)).toBe("not_started");
  });

  it("maps unit states, with unknown reading as not started (never completed)", () => {
    expect(unitState("ready_for_check")).toBe("ready_for_check");
    expect(unitState("completed")).toBe("completed");
    expect(unitState("passed")).toBe("completed");
    expect(unitState("???")).toBe("not_started");
  });

  it("parses the path", () => {
    const view = pathView(PATH, PREF);
    expect(view.grade).toBe(4);
    expect(view.gradeCompleted).toBe(false);
    const unit = view.subjects[0]!.units[0]!;
    expect(unit.title?.text).toBe("Fractions");
    expect(unit.lessons.map((l) => l.state)).toEqual(["practised", "mastered", "not_started"]);
    expect(unit.check).toMatchObject({ available: true, bestScore: 60, passed: false, passMark: 70 });
    expect(view.nextStep).toEqual({ kind: "lesson", title: { text: "Halves", locale: "en" }, unitKey: null });
    expect(pathView({ subjects: [{ units: [{ state: "completed" }] }] }, PREF).gradeCompleted).toBe(true);
    expect(pathView(null, PREF).subjects).toEqual([]);
  });
});

describe("completed is not mastered", () => {
  it.each<Locale>(["ur", "en"])("%s: practice done and mastered differ in words and shape", (locale) => {
    const t = createTranslator(locale);
    const practised = lessonBadge("practised", t);
    const mastered = lessonBadge("mastered", t);
    expect(practised.label).not.toBe(mastered.label);
    expect(practised.symbol).not.toBe(mastered.symbol);
    expect(practised.label).not.toContain(mastered.label);
    expect(new Set(["not_started", "in_progress", "practised", "mastered"].map((s) => lessonBadge(s as never, t).label)).size).toBe(4);
    expect(new Set(["not_started", "in_progress", "ready_for_check", "completed"].map((s) => unitBadge(s as never, t).label)).size).toBe(4);
  });

  it("uses the agreed English words", () => {
    const t = createTranslator("en");
    expect(lessonBadge("practised", t).label).toBe("Practice done");
    expect(lessonBadge("mastered", t).label).toBe("Mastered");
  });
});

describe("unit check entry", () => {
  const ctx = ctxFor("en");
  const view = pathView(PATH, PREF);
  const [u1, u2] = view.subjects[0]!.units;

  it("appears only when available, labelled as a Taleem check and not a certificate", () => {
    expect(checkEntry(u2!, ctx)).toBeNull();
    const entry = checkEntry(u1!, ctx)!;
    expect(entry.href).toBe("/student/subjects/u1/check");
    expect(entry.claim).toBe("Taleem unit check — not a certificate");
    expect(entry.label).toBe("Try the unit check again");
    expect(entry.best).toBe("Best result: 60% · not yet");
    expect(entry.note).toBe("You can try again after you practise the ideas you missed, or after 24 hours.");
  });

  it("says Continue for a sitting remembered on this phone", () => {
    expect(checkEntry(u1!, ctx, true)!.label).toBe("Continue the unit check");
    expect(checkEntry({ ...u1!, check: { ...u1!.check, bestScore: null } }, ctx)!.label).toBe("Start the unit check");
  });
});

describe("sitting resume", () => {
  const memory = (): KeyValueStore & { map: Map<string, string> } => {
    const map = new Map<string, string>();
    return { map, getItem: (k) => map.get(k) ?? null, setItem: (k, v) => void map.set(k, v), removeItem: (k) => void map.delete(k) };
  };

  it("remembers, reads back and forgets the sitting id (only id + expiry are stored)", () => {
    const store = memory();
    expect(rememberSitting(store, "S1", "u1", { sittingId: "sit-9", expiresAt: 2000 })).toBe(true);
    expect(JSON.parse(store.map.get(sittingStorageKey("S1", "u1"))!)).toEqual({ sittingId: "sit-9", expiresAt: 2000 });
    expect(readStoredSitting(store, "S1", "u1")).toEqual({ sittingId: "sit-9", expiresAt: 2000 });
    expect(readStoredSitting(store, "S1", "u2")).toBeNull();
    forgetSitting(store, "S1", "u1");
    expect(readStoredSitting(store, "S1", "u1")).toBeNull();
  });

  it("survives storage that throws, is missing, or holds garbage", () => {
    const throwing: KeyValueStore = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("quota");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(rememberSitting(throwing, "S1", "u1", { sittingId: "x", expiresAt: null })).toBe(false);
    expect(readStoredSitting(throwing, "S1", "u1")).toBeNull();
    expect(() => forgetSitting(throwing, "S1", "u1")).not.toThrow();
    expect(readStoredSitting(null, "S1", "u1")).toBeNull();
    const junk = memory();
    junk.setItem(sittingStorageKey("S1", "u1"), "{not json");
    expect(readStoredSitting(junk, "S1", "u1")).toBeNull();
  });

  it("plans resume / expired / start", () => {
    expect(resumePlan({ sittingId: "a", expiresAt: 200 }, null, 100)).toEqual({ kind: "resume", sittingId: "a" });
    expect(resumePlan({ sittingId: "a", expiresAt: null }, null, 100)).toEqual({ kind: "resume", sittingId: "a" });
    expect(resumePlan({ sittingId: "a", expiresAt: 100 }, null, 100)).toEqual({ kind: "expired" });
    expect(resumePlan(null, "srv", 100)).toEqual({ kind: "resume", sittingId: "srv" });
    expect(resumePlan(null, null, 100)).toEqual({ kind: "start" });
  });

  it("reads a sitting and advances it after an answer", () => {
    const s = sittingView(
      { sitting_id: "sit-1", expires_at: "2026-10-26T10:00:00Z", total: 10, answered: 2, item: { item_ref: "i3", kind: "fill", prompt: "2+2=?" } },
      "u1",
      PREF,
    );
    expect(s).toMatchObject({ sittingId: "sit-1", unitKey: "u1", total: 10, answered: 2, state: "open" });
    expect(s.expiresAt).toBe(toSeconds("2026-10-26T10:00:00Z"));
    expect(s.item).toMatchObject({ item_ref: "i3", kind: "fill", options: [] });
    expect(questionOf(s.answered, s.total, createTranslator("en"))).toBe("Question 3 of 10");
    const next = afterAnswer(s, { answered: 3, total: 10, next_item: { item_ref: "i4", options: ["a", "b"] } }, PREF);
    expect(next.answered).toBe(3);
    expect(next.item?.item_ref).toBe("i4");
    const done = afterAnswer({ ...s, answered: 9 }, { answered: 10, total: 10, next_item: null }, PREF);
    expect(done.item).toBeNull();
    expect(done.answered).toBe(10);
    expect(sittingView({ sitting_id: "x", state: "expired" }, "u1", PREF).state).toBe("incomplete");
  });

  it("reads times in seconds, milliseconds and ISO", () => {
    expect(toSeconds(1_800_000_000)).toBe(1_800_000_000);
    expect(toSeconds(1_800_000_000_000)).toBe(1_800_000_000);
    expect(toSeconds("nope")).toBeNull();
    expect(toSeconds(null)).toBeNull();
  });
});

describe("answer bodies per kind", () => {
  it("sends item_ref plus exactly one contract answer field", () => {
    expect(checkAnswerBody("c1", { option: 2 })).toEqual({ item_ref: "c1", option: 2 });
    expect(checkAnswerBody("f1", fillAnswer("  ہاں  ")!)).toEqual({ item_ref: "f1", text: "ہاں" });
    const seq = orderTap(orderTap(orderTap([], 2), 0), 1);
    expect(checkAnswerBody("o1", orderAnswer(seq, 3)!)).toEqual({ item_ref: "o1", order: [2, 0, 1] });
    let draft = tapRight(tapLeft(emptyPairDraft, 0, "match").draft, 3, "match").draft;
    draft = tapRight(tapLeft(draft, 1, "match").draft, 2, "match").draft;
    expect(checkAnswerBody("m1", pairsAnswer(draft, 2)!)).toEqual({ item_ref: "m1", pairs: [[0, 3], [1, 2]] });
    let sort = tapRight(tapLeft(emptyPairDraft, 0, "sort").draft, 2, "sort").draft;
    sort = tapRight(tapLeft(sort, 1, "sort").draft, 2, "sort").draft;
    expect(checkAnswerBody("s1", pairsAnswer(sort, 2)!)).toEqual({ item_ref: "s1", pairs: [[0, 2], [1, 2]] });
  });

  it("spells every route in one place", () => {
    expect(PROGRESSION_PATHS.path("S 1")).toBe("/v1/learning/students/S%201/path");
    expect(PROGRESSION_PATHS.startCheck("S1", "u1")).toBe("/v1/learning/students/S1/units/u1/checks");
    expect(PROGRESSION_PATHS.answer("S1", "u1", "sit")).toBe("/v1/learning/students/S1/units/u1/checks/sit:answer");
    expect(PROGRESSION_PATHS.finish("S1", "u1", "sit")).toBe("/v1/learning/students/S1/units/u1/checks/sit:finish");
    expect(PROGRESSION_PATHS.learnerRecord("S1")).toBe("/v1/learning/students/S1/record");
    expect(PROGRESSION_PATHS.guardianRecord("S1")).toBe("/v1/guardian/children/S1/record");
  });
});

describe("finish view", () => {
  const notYet = checkResult(
    {
      score_percent: 60,
      passed: false,
      pass_mark: 70,
      per_objective: [
        { objective_code: "M4.F.1", title: { en: "Halves" }, correct: 5, total: 5 },
        { objective_code: "M4.F.2", title: { en: "Quarters" }, correct: 1, total: 5 },
      ],
      remediation: [{ objective_code: "M4.F.2", title: { en: "Quarters" } }],
    },
    PREF,
  );

  it("shows score, not yet, breakdown and remediation links — encouraging, never 'fail'", () => {
    const v = resultView(notYet, ctxFor("en"));
    expect(v.outcome).toBe("not_yet");
    expect(v.title).toBe("Not yet — and that is OK");
    expect(v.score).toBe("Your score: 60%");
    expect(v.passMark).toBe("Pass mark: 70%");
    expect(v.breakdown.map((b) => b.line)).toEqual(["5 of 5 right", "1 of 5 right"]);
    expect(v.breakdown[0]!.allRight).toBe(true);
    expect(v.remediation).toEqual([
      { code: "M4.F.2", title: { text: "Quarters", locale: "en" }, href: "/student/session?lesson=M4.F.2", action: "Practise with my AI teacher" },
    ]);
    expect(v.retake).toBe("You can try again after you practise the ideas you missed, or after 24 hours.");
    expect(v.claim).toBe("Taleem unit check — not a certificate");
    expect(JSON.stringify(v).toLowerCase()).not.toMatch(/\bfail(ed)?\b/);
  });

  it("passes, with no retake line", () => {
    const v = resultView(checkResult({ score_percent: 90, passed: true, pass_mark: 70 }, PREF), ctxFor("ur"));
    expect(v.outcome).toBe("passed");
    expect(v.retake).toBeNull();
    expect(v.title).toBe(progressionUr.result.passedTitle);
  });

  it("reproduces the score from the breakdown when the server omits it", () => {
    const r = checkResult({ per_objective: [{ correct: 7, total: 10 }] }, PREF);
    expect(r.scorePercent).toBe(70);
    expect(r.passed).toBe(true);
  });
});

describe("record view", () => {
  const RECORD: RecordWire = {
    grade: 4,
    grade_completion: { grade: 4, completed_at: 1_800_000_000 },
    subjects: [
      {
        subject_key: "math",
        title: { en: "Mathematics" },
        units: [
          {
            unit_key: "u1",
            title: { en: "Fractions" },
            state: "completed",
            sittings: [
              { sitting_id: "a", finished_at: 1_790_000_000, state: "finished", score_percent: 60, passed: false },
              { sitting_id: "b", finished_at: 1_795_000_000, state: "finished", score_percent: 80, passed: true },
              { sitting_id: "c", started_at: 1_796_000_000, state: "incomplete" },
            ],
          },
        ],
      },
    ],
    sittings: [{ sitting_id: "z", unit_key: "u9", unit_title: { en: "Old unit" }, finished_at: 1_780_000_000, score_percent: 50, passed: false }],
    lessons_mastered: [{ lesson_id: "L2", title: { en: "Quarters" } }],
    report_cards: [{ card_id: "rc 1", period_start: 1_790_000_000, period_end: 1_792_000_000 }],
    derived_at: 1_800_000_100,
  };

  it("keeps every sitting, newest first, with the best result and 'not finished' never a fail", () => {
    const rec = academicRecord(RECORD, PREF);
    const unit = rec.subjects[0]!.units[0]!;
    expect(unit.sittings.map((s) => s.sittingId)).toEqual(["c", "b", "a"]);
    expect(unit.best).toEqual({ scorePercent: 80, passed: true });
    expect(rec.subjects[1]!.units[0]!.key).toBe("u9");
    const v = recordView(rec, ctxFor("en"), LEARNER_RECORD_LINKS);
    const lines = v.subjects[0]!.units[0]!.sittings;
    expect(lines.map((l) => l.state)).toEqual(["incomplete", "passed", "not_yet"]);
    expect(lines[0]!.text).toContain("Not finished (not a fail)");
    expect(v.subjects[0]!.units[0]!.best).toBe("Best result: 80% · passed");
    expect(v.grade).toBe("Grade 4");
    expect(v.gradeCompletion!.text).toBe("Grade 4 completed in Taleem — not an accredited certificate");
    expect(v.lessonsMastered.count).toBe("Lessons mastered: 1");
    expect(v.reportCards[0]!.href).toBe("/student/report-cards/rc%201");
    expect(v.hasSittings).toBe(true);
  });

  it("links a guardian to the child's report cards", () => {
    const v = recordView(academicRecord(RECORD, PREF), ctxFor("ur"), guardianRecordLinks("S 1"));
    expect(v.reportCards[0]!.href).toBe("/guardian/children/S%201/report-cards/rc%201");
    expect(v.reportCardsHref).toBe("/guardian/children/S%201/report-cards");
  });

  it("has no grade completion unless the server derived one, and accepts a mastered count", () => {
    const rec = academicRecord({ grade: 4, lessons_mastered: 3 }, PREF);
    expect(rec.gradeCompletion).toBeNull();
    expect(rec.lessonsMasteredCount).toBe(3);
    expect(recordView(rec, ctxFor("en"), LEARNER_RECORD_LINKS).lessonsMastered.none).toBe(false);
  });
});

describe("offline and failures", () => {
  it("says honestly that a check needs the internet", () => {
    const t = createTranslator("en");
    expect(checkOfflineMessage(true, t).body).toMatch(/only work with the internet.*saved answers are safe/);
    expect(checkOfflineMessage(false, t).body).toMatch(/only work with the internet/);
    expect(checkOfflineMessage(false, createTranslator("ur")).title).toBe(progressionUr.check.offlineTitle);
  });

  it("classifies check errors", () => {
    expect(checkFailure(new ApiError(0, { code: "OFFLINE" }))).toBe("offline");
    expect(checkFailure(new ApiError(410, { code: "GONE" }))).toBe("expired");
    expect(checkFailure(new ApiError(409, { code: "RETAKE_NOT_ALLOWED" }))).toBe("retake_not_yet");
    expect(checkFailure(new ApiError(409, { code: "UNIT_NOT_READY" }))).toBe("not_available");
    expect(checkFailure(new ApiError(404, { code: "NOT_FOUND" }))).toBe("gone");
    expect(checkFailure(new Error("x"))).toBe("error");
  });
});

describe("no certificate claim", () => {
  type Tree = { [k: string]: string | Tree };
  const leaves = (tree: Tree): string[] => Object.values(tree).flatMap((v) => (typeof v === "string" ? [v] : leaves(v)));

  it("every English mention of a certificate is a denial", () => {
    for (const text of leaves(progressionEn as unknown as Tree)) {
      for (const m of text.matchAll(/certificat\w*/gi)) {
        const before = text.slice(0, m.index).toLowerCase();
        expect({ text, ok: /not (a|an accredited) $|, not $/.test(before) }).toEqual({ text, ok: true });
      }
    }
  });

  it("every Urdu mention of a certificate is a denial", () => {
    for (const text of leaves(progressionUr as unknown as Tree)) {
      for (const m of text.matchAll(/سرٹیفکیٹ/g)) {
        const after = text.slice(m.index! + m[0].length);
        expect({ text, ok: /^ نہیں/.test(after) }).toEqual({ text, ok: true });
      }
    }
  });
});
