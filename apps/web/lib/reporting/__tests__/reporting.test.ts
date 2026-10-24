// Report cards — the pure half (REPORT_CARD_CONTRACT.md): the wire edge, the period rules, the
// preview / issue bodies (comments, supersedes), the exact skip reasons, the view model's honesty
// rules (issuer, no evidence, integrity, totals), the list order, "acknowledge once", the guardian
// feed badge, and locale numerals. "Get a report" (generate) is in generate.test.ts.
import { describe, expect, it } from "vitest";

import { createTranslator } from "../../i18n/translate";
import { ApiError } from "../../student/types";
import { localDateInput } from "../../teacher/assignments";
import { REPORTING_PATHS } from "../api";
import {
  COMMENT_MAX,
  commentProblem,
  defaultPeriod,
  issueBody,
  issueErrorKey,
  periodFromInputs,
  previewBody,
  skippedReasonKey,
  skippedRows,
} from "../teacher";
import type { ReportCardWire } from "../types";
import {
  ackReducer,
  acknowledgedAt,
  canAcknowledge,
  cardListView,
  cardView,
  feedBadge,
  initialAck,
  masteryDots,
  readFailure,
  showAcknowledge,
  type AckState,
} from "../view";
import { cardList, feed, reportCard, resultCards, skipped } from "../wire";

const at = (y: number, m: number, d: number, h = 12) => Math.floor(new Date(y, m - 1, d, h).getTime() / 1000);
const NOW = at(2026, 10, 24, 15);
const en = { t: createTranslator("en"), locale: "en" as const, timeZone: "UTC" };
const ur = { t: createTranslator("ur"), locale: "ur" as const, timeZone: "UTC" };

function wire(over: Partial<ReportCardWire> = {}): ReportCardWire {
  return {
    format: "taleem.report-card/1",
    derivation: "taleem.reporting.derive/1",
    card_id: "rc-1",
    student_ref: "S1",
    learner_display_name: "Ayesha",
    class_id: "C1",
    class_name: "Class 4",
    organization_id: null,
    organization_name: null,
    period_start: at(2026, 7, 24, 0),
    period_end: at(2026, 10, 24, 15),
    period_rule: "start_inclusive_end_exclusive",
    issued_at: at(2026, 10, 24, 15),
    issued_by: "T-7",
    issued_by_name: "Ms Sana",
    status: "issued",
    notice: null,
    totals: { objectives: 2, objectives_mastered: 1, attempts: 5, correct: 3, homework_met: 1, homework_not_yet: 0 },
    hash_verified: true,
    comment: null,
    supersedes: null,
    superseded_by: null,
    acknowledged_at: null,
    content_hash: "abcdef0123456789abcdef",
    curriculum_pack: "pk-primary-2026.1",
    has_evidence: true,
    subjects: [
      {
        subject_key: "math",
        subject_name: { ur: "ریاضی", en: "Maths" },
        objectives: [
          {
            objective_code: "M4.1",
            title: { ur: "جمع", en: "Addition" },
            mastery: "mastered",
            attempts: 5,
            correct: 3,
            homework_met: 1,
            homework_not_yet: 0,
            lesson_id: "L-12",
            lesson_version: 3,
          },
          { objective_code: "M4.2", title: { en: "Subtraction" }, mastery: "not_started", attempts: 0, correct: 0, homework_met: 0, homework_not_yet: 0 },
        ],
      },
    ],
    ...over,
  };
}

describe("the wire edge", () => {
  it("accepts the list under report_cards, cards, or as a bare array", () => {
    expect(cardList({ report_cards: [wire()] })).toHaveLength(1);
    expect(cardList({ cards: [wire()] })).toHaveLength(1);
    expect(cardList([wire(), wire()])).toHaveLength(2);
    expect(cardList(null)).toEqual([]);
    expect(resultCards({ previews: [wire()], skipped: [] })).toHaveLength(1);
    expect(resultCards({ issued: [wire()] })).toHaveLength(1);
  });

  it("reads an unknown mastery as not started, never as mastered, and never more right than tried", () => {
    const card = reportCard(
      wire({ subjects: [{ subject_key: "x", objectives: [{ objective_code: "a", mastery: "wizard", attempts: 2, correct: 9 }, { objective_code: "b", mastery: "in_progress" }] }] }),
      ["en"],
    );
    expect(card.subjects[0]!.objectives[0]!.mastery).toBe("not_started");
    expect(card.subjects[0]!.objectives[0]!.correct).toBe(2);
    expect(card.subjects[0]!.objectives[1]!.mastery).toBe("developing");
  });

  it("falls back to the evidence itself only when has_evidence is absent", () => {
    expect(reportCard(wire({ has_evidence: false }), ["en"]).hasEvidence).toBe(false);
    const bare = wire({ subjects: [{ subject_key: "x", objectives: [{ objective_code: "a", attempts: 0 }] }] });
    delete bare.has_evidence;
    expect(reportCard(bare, ["en"]).hasEvidence).toBe(false);
  });

  it("reads skipped learners with the server's exact reason codes; anything else is 'other', never guessed", () => {
    expect(
      skipped({
        class_id: "C1",
        period_start: 1,
        period_end: 2,
        report_cards: [],
        skipped: [
          { student_ref: "S1", learner_display_name: "Bilal", reason: "consent_withdrawn" },
          { student_ref: "S2", learner_display_name: null, reason: "inactive" },
          { student_ref: "S3", learner_display_name: "Zara", reason: "not_in_class" },
          { student_ref: "S4", learner_display_name: "Omar", reason: "already_issued", card_id: "rc-9" },
          { student_ref: "S5", display_name: "Old", reason: "consent_missing", card_id: "rc-x" },
        ],
      }),
    ).toEqual([
      { studentRef: "S1", learnerName: "Bilal", reason: "consent_withdrawn", cardId: null },
      { studentRef: "S2", learnerName: "", reason: "inactive", cardId: null },
      { studentRef: "S3", learnerName: "Zara", reason: "not_in_class", cardId: null },
      { studentRef: "S4", learnerName: "Omar", reason: "already_issued", cardId: "rc-9" },
      { studentRef: "S5", learnerName: "Old", reason: "other", cardId: null },
    ]);
  });

  it("reads issuer, status, totals and the hash check exactly as sent", () => {
    const sys = reportCard(wire({ issued_by: "system", issued_by_name: "Taleem", class_id: null, class_name: null, comment: "x" }), ["en"]);
    expect(sys).toMatchObject({ isSystem: true, issuedByName: "Taleem", classId: "", className: "", comment: null, status: "issued" });
    expect(sys.totals).toEqual({ objectives: 2, objectivesMastered: 1, attempts: 5, correct: 3, homeworkMet: 1, homeworkNotYet: 0 });
    expect(reportCard(wire(), ["en"])).toMatchObject({ isSystem: false, issuedBy: "T-7", hashVerified: true });
    expect(reportCard(wire({ hash_verified: false }), ["en"]).hashVerified).toBe(false);
    const bare = wire();
    delete bare.hash_verified;
    delete bare.status;
    expect(reportCard(bare, ["en"])).toMatchObject({ hashVerified: null, status: "issued" });
    expect(reportCard(wire({ card_id: null, status: "preview" }), ["en"]).status).toBe("preview");
    expect(reportCard(wire({ status: "superseded", superseded_by: "rc-2" }), ["en"]).status).toBe("superseded");
  });

  it("the no-evidence notice always wins, and then there are no totals", () => {
    const card = reportCard(wire({ notice: "no_evidence_in_period", has_evidence: true }), ["en"]);
    expect(card.hasEvidence).toBe(false);
    expect(card.totals).toBeNull();
  });

  it("spells every path once, under /v1/reporting", () => {
    expect(REPORTING_PATHS.preview("C 1")).toBe("/v1/reporting/classes/C%201/report-cards:preview");
    expect(REPORTING_PATHS.issue("C1")).toBe("/v1/reporting/classes/C1/report-cards");
    expect(REPORTING_PATHS.childCards("S1")).toBe("/v1/reporting/children/S1/report-cards");
    expect(REPORTING_PATHS.generate("S 1")).toBe("/v1/reporting/children/S%201/report-cards:generate");
    expect(REPORTING_PATHS.notifications("S1")).toBe("/v1/reporting/children/S1/notifications");
    expect(REPORTING_PATHS.card("rc/1")).toBe("/v1/reporting/report-cards/rc%2F1");
    expect(REPORTING_PATHS.acknowledge("rc-1")).toBe("/v1/reporting/report-cards/rc-1:acknowledge");
    expect(REPORTING_PATHS.learnerCards("S1")).toBe("/v1/reporting/learners/S1/report-cards");
  });
});

describe("period validation", () => {
  it("defaults to the last three months ending today", () => {
    expect(defaultPeriod(NOW)).toEqual({ start: "2026-07-24", end: "2026-10-24" });
    // 31 May minus three months is the last day of February, not 3 March.
    expect(defaultPeriod(at(2026, 5, 31))).toEqual({ start: "2026-02-28", end: "2026-05-31" });
    expect(periodFromInputs(defaultPeriod(NOW), NOW).ok).toBe(true);
  });

  it("asks for both days and refuses dates that do not exist", () => {
    expect(periodFromInputs({ start: "", end: "" }, NOW)).toEqual({
      ok: false,
      problems: { start: "teacher.reportCards.startEmpty", end: "teacher.reportCards.endEmpty" },
    });
    expect(periodFromInputs({ start: "2026-02-30", end: "2026-03-01" }, NOW)).toEqual({
      ok: false,
      problems: { start: "teacher.reportCards.dateInvalid" },
    });
  });

  it("refuses a last day in the future, and a start that is not before the end", () => {
    expect(periodFromInputs({ start: "2026-09-01", end: "2026-10-25" }, NOW)).toEqual({
      ok: false,
      problems: { end: "teacher.reportCards.endFuture" },
    });
    expect(periodFromInputs({ start: "2026-10-10", end: "2026-10-01" }, NOW)).toEqual({
      ok: false,
      problems: { start: "teacher.reportCards.order" },
    });
  });

  it("runs from the start of the first day to the start of the day after the last (exclusive) — or now, when that is today", () => {
    const past = periodFromInputs({ start: "2026-09-01", end: "2026-09-30" }, NOW);
    expect(past).toEqual({ ok: true, periodStart: at(2026, 9, 1, 0), periodEnd: at(2026, 10, 1, 0) });
    // A single day is a valid period.
    expect(periodFromInputs({ start: "2026-09-01", end: "2026-09-01" }, NOW)).toEqual({
      ok: true,
      periodStart: at(2026, 9, 1, 0),
      periodEnd: at(2026, 9, 2, 0),
    });
    const today = periodFromInputs({ start: "2026-09-01", end: "2026-10-24" }, NOW);
    expect(today.ok && today.periodEnd).toBe(NOW);
    expect(today.ok && today.periodEnd <= NOW).toBe(true);
  });
});

describe("preview and issue bodies", () => {
  const period = { periodStart: 100, periodEnd: 200 };

  it("previews the whole class unless learners are named, carrying any correction", () => {
    expect(previewBody(period)).toEqual({ period_start: 100, period_end: 200 });
    expect(previewBody(period, ["S1"])).toEqual({ period_start: 100, period_end: 200, student_refs: ["S1"] });
    expect(previewBody(period, undefined, { S4: " rc-9 ", S5: "" })).toEqual({ period_start: 100, period_end: 200, supersedes: { S4: "rc-9" } });
  });

  it("issues exactly the previewed learners, with trimmed comments and only the chosen supersedes", () => {
    const built = issueBody({
      ...period,
      studentRefs: ["S1", "S2"],
      comments: { S1: "  Well done.  ", S2: "   ", S3: "not previewed" },
      supersedes: { S2: "rc-old", S1: "", S3: "rc-x" },
    });
    expect(built).toEqual({
      ok: true,
      body: { period_start: 100, period_end: 200, student_refs: ["S1", "S2"], comments: { S1: "Well done." }, supersedes: { S2: "rc-old" } },
    });
  });

  it("leaves comments and supersedes out when there are none", () => {
    const built = issueBody({ ...period, studentRefs: ["S1"], comments: {}, supersedes: {} });
    expect(built).toEqual({ ok: true, body: { period_start: 100, period_end: 200, student_refs: ["S1"] } });
  });

  it("refuses a comment over 1000 characters (counted as characters, not UTF-16 units)", () => {
    expect(commentProblem("ب".repeat(COMMENT_MAX))).toBeNull();
    expect(commentProblem("😀".repeat(COMMENT_MAX))).toBeNull();
    expect(issueBody({ ...period, studentRefs: ["S1"], comments: { S1: "x".repeat(1001) }, supersedes: {} })).toEqual({
      ok: false,
      problem: "teacher.reportCards.commentTooLong",
      studentRef: "S1",
    });
  });

  it("has nothing to issue without a preview", () => {
    expect(issueBody({ ...period, studentRefs: [], comments: {}, supersedes: {} })).toEqual({
      ok: false,
      problem: "teacher.reportCards.nothingToIssue",
    });
  });

  it("names why a learner was left out, and what a refused issue means", () => {
    expect(skippedReasonKey("consent_withdrawn")).toBe("teacher.reportCards.skipped.consentWithdrawn");
    expect(skippedReasonKey("inactive")).toBe("teacher.reportCards.skipped.inactive");
    expect(skippedReasonKey("not_in_class")).toBe("teacher.reportCards.skipped.notInClass");
    expect(skippedReasonKey("already_issued")).toBe("teacher.reportCards.skipped.alreadyIssued");
    expect(skippedReasonKey("other")).toBe("teacher.reportCards.skipped.other");
    const t = createTranslator("en");
    expect(t(skippedReasonKey("consent_withdrawn"))).toBe("Their guardian has switched off permission.");
    expect(t(skippedReasonKey("already_issued"))).toBe("Already has a card for these dates.");
    expect(createTranslator("ur")(skippedReasonKey("inactive"))).toBe("ان کا اکاؤنٹ فعال نہیں۔");
    expect(issueErrorKey(new ApiError(422, { code: "VALIDATION" }))).toBe("teacher.reportCards.periodRejected");
    expect(issueErrorKey(new ApiError(409, { code: "ALREADY_SUPERSEDED" }))).toBe("teacher.reportCards.supersedeConflict");
    expect(issueErrorKey(new ApiError(404, { code: "NOT_FOUND" }))).toBe("teacher.errors.notAvailable");
    expect(issueErrorKey(new ApiError(0, { code: "OFFLINE" }))).toBe("teacher.errors.offline");
  });

  it("offers 'correct it' only for already_issued with the card id the server gave", () => {
    const rows = skippedRows(
      skipped({
        skipped: [
          { student_ref: "S4", learner_display_name: "Omar", reason: "already_issued", card_id: "rc-9" },
          { student_ref: "S6", learner_display_name: "Hina", reason: "already_issued" },
          { student_ref: "S1", learner_display_name: "Bilal", reason: "consent_withdrawn", card_id: "rc-1" },
        ],
      }),
    );
    expect(rows.map((r) => [r.studentRef, r.canCorrect, r.cardId])).toEqual([
      ["S4", true, "rc-9"],
      ["S6", false, null],
      ["S1", false, null],
    ]);
    // The correction then rides in the issue body for exactly that learner and card.
    expect(issueBody({ ...period, studentRefs: ["S4"], comments: {}, supersedes: { S4: rows[0]!.cardId! } })).toEqual({
      ok: true,
      body: { period_start: 100, period_end: 200, student_refs: ["S4"], supersedes: { S4: "rc-9" } },
    });
  });
});

describe("the card view", () => {
  it("gives each objective a word for its mastery, its practice, its homework and its version pin", () => {
    const view = cardView(reportCard(wire(), ["en", "ur"]), en);
    const [first, second] = view.subjects[0]!.objectives;
    expect(view.subjects[0]!.name).toBe("Maths");
    expect(view.subjects[0]!.summary).toBe("Learned well: 1 · Still learning: 0 · Not started yet: 1");
    expect(first!.masteryLabel).toBe("Learned well");
    expect(first!.practice).toBe("Questions answered: 5 · Right answers: 3");
    expect(first!.homework).toBe("Homework done well: 1 · Homework to try again: 0");
    expect(first!.pin).toBe("Learned from lesson L-12 v3");
    expect(view.curriculum).toBe("Curriculum: pk-primary-2026.1");
    expect(view.reference).toBe("Card rc-1 · check code abcdef012345");
    // Nothing practised: says so, never "0 of 0 right".
    expect(second!.practice).toBeNull();
    expect(second!.homework).toBeNull();
    expect(second!.noPractice).toBe("No practice in these dates.");
    expect(second!.pin).toBeNull();
  });

  it("shows no figures at all for a card with no evidence", () => {
    const view = cardView(reportCard(wire({ has_evidence: false }), ["en"]), en);
    expect(view.hasEvidence).toBe(false);
    expect(view.subjects).toEqual([]);
    expect(view.totals).toEqual([]);
    const none = cardView(
      reportCard(wire({ has_evidence: false, notice: "no_evidence_in_period", totals: null, subjects: [] }), ["en"]),
      en,
    );
    expect(none).toMatchObject({ hasEvidence: false, subjects: [], totals: [] });
  });

  it("says 'Issued by Taleem' on a system card and the teacher's name otherwise", () => {
    const sys = cardView(reportCard(wire({ issued_by: "system", issued_by_name: "Taleem", class_id: null, class_name: null }), ["en"]), en);
    expect(sys.issued).toBe("Issued by Taleem on Oct 24, 2026");
    expect(sys).toMatchObject({ isSystem: true, className: null, comment: null, commentBy: null });
    expect(cardView(reportCard(wire({ issued_by: "system", issued_by_name: "Taleem" }), ["ur"]), ur).issued).toBe(
      "تعلیم نے 24 اکتوبر، 2026 کو جاری کیا",
    );
    const teacher = cardView(reportCard(wire({ comment: "Well done" }), ["en"]), en);
    expect(teacher.issued).toBe("Issued by Ms Sana on Oct 24, 2026");
    expect(teacher.commentBy).toBe("Written by Ms Sana");
    expect(cardView(reportCard(wire({ issued_by_name: "" }), ["en"]), en).issued).toBe("Issued by the teacher on Oct 24, 2026");
    // A preview names nobody: nothing has been issued.
    expect(cardView(reportCard(wire({ card_id: null, status: "preview" }), ["en"]), en).issued).toBeNull();
  });

  it("sums the card up in short plain lines, leaving out what did not happen", () => {
    expect(cardView(reportCard(wire(), ["en"]), en).totals).toEqual([
      "Topics learned well: 1 of 2",
      "Questions answered: 5 · Right answers: 3",
      "Homework done well: 1 · Homework to try again: 0",
    ]);
    const noHomework = wire({ totals: { objectives: 3, objectives_mastered: 0, attempts: 4, correct: 1, homework_met: 0, homework_not_yet: 0 } });
    expect(cardView(reportCard(noHomework, ["en"]), en).totals).toEqual(["Topics learned well: 0 of 3", "Questions answered: 4 · Right answers: 1"]);
    expect(cardView(reportCard(wire({ totals: null }), ["en"]), en).totals).toEqual([]);
  });

  it("warns when the server could not re-verify the card's hash — and only then", () => {
    expect(cardView(reportCard(wire({ hash_verified: false }), ["en"]), en).integrityWarning).toBe(true);
    expect(cardView(reportCard(wire({ hash_verified: true }), ["en"]), en).integrityWarning).toBe(false);
    const bare = wire();
    delete bare.hash_verified;
    expect(cardView(reportCard(bare, ["en"]), en).integrityWarning).toBe(false);
    const items = cardListView([reportCard(wire({ hash_verified: false }), ["en"])], en);
    expect(items[0]!.unverified).toBe(true);
  });

  it("shows an exclusive end as the last day it covers", () => {
    const sept = { period_start: Date.UTC(2026, 8, 1) / 1000, period_end: Date.UTC(2026, 9, 1) / 1000 };
    expect(cardView(reportCard(wire(sept), ["en"]), en).period).toBe("From Sep 1, 2026 to Sep 30, 2026");
  });

  it("uses Urdu words, and the locale's digits when native digits are asked for", () => {
    const western = cardView(reportCard(wire(), ["ur"]), ur);
    expect(western.subjects[0]!.objectives[0]!.practice).toBe("حل کیے گئے سوال: 5 · درست جواب: 3");
    const native = cardView(reportCard(wire(), ["ur"]), { ...ur, t: createTranslator("ur", "native") });
    expect(native.subjects[0]!.objectives[0]!.practice).toBe("حل کیے گئے سوال: ۵ · درست جواب: ۳");
    expect(native.subjects[0]!.name).toBe("ریاضی");
    const english = cardView(reportCard(wire(), ["en"]), { ...en, t: createTranslator("en", "native") });
    expect(english.subjects[0]!.objectives[0]!.practice).toBe("Questions answered: 5 · Right answers: 3");
  });

  it("draws mastery as three dots filled by how far along", () => {
    expect(masteryDots("mastered")).toBe("●●●");
    expect(masteryDots("developing")).toBe("●●○");
    expect(masteryDots("not_started")).toBe("○○○");
  });

  it("marks a preview, a correction and a replaced card", () => {
    expect(cardView(reportCard(wire({ card_id: null, issued_at: null }), ["en"]), en)).toMatchObject({ isPreview: true, issued: null });
    expect(cardView(reportCard(wire({ supersedes: "rc-0" }), ["en"]), en).corrects).toBe(true);
    const replaced = cardView(reportCard(wire({ superseded_by: "rc-2" }), ["en"]), en);
    expect(replaced).toMatchObject({ superseded: true, supersededBy: "rc-2" });
    expect(showAcknowledge(replaced)).toBe(false);
    expect(cardView(reportCard(wire({ status: "superseded" }), ["en"]), en).superseded).toBe(true);
    expect(cardView(reportCard(wire({ status: "preview", card_id: null }), ["en"]), en).isPreview).toBe(true);
  });
});

describe("the list of cards", () => {
  it("is newest first, and marks a card another one supersedes", () => {
    const cards = [
      wire({ card_id: "old", issued_at: 100 }),
      wire({ card_id: "new", issued_at: 300, supersedes: "mid" }),
      wire({ card_id: "mid", issued_at: 200 }),
    ].map((w) => reportCard(w, ["en"]));
    const items = cardListView(cards, en);
    expect(items.map((i) => i.cardId)).toEqual(["new", "mid", "old"]);
    expect(items.map((i) => i.superseded)).toEqual([false, true, false]);
  });
});

describe("acknowledge once", () => {
  it("starts seen when the server already recorded it, so there is nothing to send", () => {
    const seen = initialAck({ acknowledgedAt: 500 });
    expect(seen).toEqual({ status: "seen", at: 500, justNow: false });
    expect(canAcknowledge(seen)).toBe(false);
    expect(ackReducer(seen, { type: "send" })).toBe(seen);
  });

  it("sends once: a second tap while sending, or after it is recorded, does nothing", () => {
    let state: AckState = initialAck({ acknowledgedAt: null });
    expect(canAcknowledge(state)).toBe(true);
    state = ackReducer(state, { type: "send" });
    expect(state.status).toBe("sending");
    expect(canAcknowledge(state)).toBe(false);
    expect(ackReducer(state, { type: "send" })).toBe(state);
    state = ackReducer(state, { type: "done", at: acknowledgedAt({ acknowledged_at: 900 }, 1) });
    expect(state).toEqual({ status: "seen", at: 900, justNow: true });
    expect(ackReducer(state, { type: "send" })).toBe(state);
    expect(ackReducer(state, { type: "failed", error: new Error("late"), now: 1 })).toBe(state);
  });

  it("may retry after a failure; a 409 (already recorded) counts as seen", () => {
    const failed = ackReducer({ status: "sending" }, { type: "failed", error: new ApiError(0, { code: "OFFLINE" }), now: 5 });
    expect(failed).toEqual({ status: "failed", error: "common.reportCard.ackOffline" });
    expect(canAcknowledge(failed)).toBe(true);
    expect(ackReducer({ status: "sending" }, { type: "failed", error: new ApiError(409, { code: "ALREADY_ACKNOWLEDGED" }), now: 7 })).toEqual({
      status: "seen",
      at: 7,
      justNow: true,
    });
    expect(acknowledgedAt(undefined, 42)).toBe(42);
  });

  it("reads 403 and 404 the same way, so nothing is revealed", () => {
    expect(readFailure(new ApiError(403, { code: "FORBIDDEN" }))).toBe("not-available");
    expect(readFailure(new ApiError(404, { code: "NOT_FOUND" }))).toBe("not-available");
    expect(readFailure(new ApiError(0, { code: "OFFLINE" }))).toBe("offline");
    expect(readFailure(new ApiError(403, { code: "CONSENT_REQUIRED" }))).toBe("consent");
  });
});

describe("the guardian's in-app feed", () => {
  const note = (cardId: string, read: boolean) => ({
    id: `report-card-${cardId}`,
    kind: "report_card_issued",
    card_id: cardId,
    student_ref: "S1",
    class_id: null,
    period_start: 1,
    period_end: 2,
    supersedes: null,
    issued_at: 3,
    read,
  });

  it("reads {notifications, unread}, and counts unread itself when the number is missing", () => {
    expect(feed({ notifications: [note("a", false), note("b", true)], unread: 1 })).toMatchObject({ unread: 1 });
    expect(feed({ notifications: [note("a", false), note("b", false)] }).unread).toBe(2);
    expect(feed([note("a", false)]).unread).toBe(1);
    expect(feed(null)).toEqual({ items: [], unread: 0 });
    // An entry without a card, or of another kind, is not a report card notice.
    expect(feed({ notifications: [{ ...note("a", false), card_id: "" }, { ...note("b", false), kind: "other" }] }).items).toEqual([]);
  });

  it("badges the child page only when something is unread", () => {
    const t = createTranslator("en");
    expect(feedBadge(feed({ notifications: [note("a", true)], unread: 0 }), t)).toBeNull();
    expect(feedBadge(null, t)).toBeNull();
    expect(feedBadge(feed({ notifications: [note("a", false)], unread: 1 }), t)).toBe("New report card");
    expect(feedBadge(feed({ notifications: [note("a", false), note("b", false), note("c", false)], unread: 3 }), t)).toBe(
      "New report cards: 3",
    );
    expect(feedBadge(feed({ notifications: [note("a", false), note("b", false)] }), createTranslator("ur"))).toBe("نئے رپورٹ کارڈ: 2");
  });
});
