// Homework and marking view models (HOMEWORK_AND_MARKING_CONTRACT.md): the learner's state badges,
// the Send gate and counter, offline keeping the draft without sending, and the teacher's mark,
// return and safeguarding-concern bodies. Pure — no browser, no network.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CATALOGS } from "../../i18n/messages";
import { ApiError } from "../../student/types";
import { clearHomeworkDrafts, draftKey, localDrafts, type DraftStore } from "../drafts";
import { HOMEWORK_PATHS } from "../api";
import {
  afterSent,
  charCount,
  homeworkView,
  initialText,
  isOpen,
  sendHomework,
  sendOutcomeKey,
  stateBadge,
  submitBody,
  submitGate,
  type HomeworkItemView,
} from "../student";
import {
  concernBody,
  concernErrorKey,
  decisionErrorKey,
  FEEDBACK_MAX,
  markBody,
  queueView,
  returnBody,
  rubricView,
} from "../teacher";
import type { LearnerHomeworkWire, SubmissionRowWire } from "../types";

const PREF = ["ur", "en"] as const;

function memoryDrafts(): DraftStore & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    read: (k) => data.get(k) ?? null,
    write: (k, v) => {
      if (v === "") data.delete(k);
      else data.set(k, v);
      return true;
    },
    clear: (k) => void data.delete(k),
  };
}

const item = (over: Partial<HomeworkItemView> = {}): HomeworkItemView => ({
  assignmentId: "a1",
  itemRef: "hw-1",
  prompt: { text: "سوال", locale: "ur" },
  hints: [],
  maxChars: 200,
  state: "not_started",
  sentText: null,
  feedback: null,
  outcome: null,
  ...over,
});

// ---- learner -------------------------------------------------------------------------------------------

describe("homeworkView", () => {
  const wire: LearnerHomeworkWire = {
    assignments: [
      {
        assignment_id: "late",
        objective_code: "M3.2",
        lesson_title: { ur: "کسر", en: "Fractions" },
        due_at: 2000,
        items: [
          { item_ref: "i1", kind: "written", prompt: { ur: "لکھیں", en: "Write" }, max_chars: 2000, hints: ["", "سوچیں"] },
          {
            item_ref: "i2",
            prompt: "Plain prompt",
            max_chars: 200,
            submission: { submission_id: "s2", state: "marked", outcome: "met", feedback: "شاباش", text: "میرا جواب" },
          },
        ],
      },
      { assignment_id: "soon", objective_code: "M3.1", due_at: 1000, items: [{ item_ref: "i3", prompt: { en: "x" }, max_chars: 200, state: "returned" }] },
      { assignment_id: "nothing", objective_code: "M3.0", due_at: 500, items: [] },
    ],
  };

  it("sorts soonest due first, drops assignments with no written items, and reads either state field", () => {
    const view = homeworkView(wire, PREF, ["en", ...PREF]);
    expect(view.map((a) => a.assignmentId)).toEqual(["soon", "late"]);
    expect(view[1]!.title).toEqual({ text: "Fractions", locale: "en" });
    expect(view[0]!.items[0]!.state).toBe("returned");
    const [first, second] = view[1]!.items;
    expect(first!.prompt).toEqual({ text: "لکھیں", locale: "ur" });
    expect(first!.hints).toEqual(["سوچیں"]);
    expect(first!.maxChars).toBe(2000);
    expect(second).toMatchObject({ state: "marked", outcome: "met", feedback: "شاباش", sentText: "میرا جواب" });
    expect(second!.prompt).toEqual({ text: "Plain prompt", locale: "" });
  });

  it("never reads an unknown state as marked", () => {
    const v = homeworkView(
      { assignments: [{ assignment_id: "a", objective_code: "x", due_at: 1, items: [{ item_ref: "i", prompt: "p", max_chars: 0, state: "weird" as never }] }] },
      PREF,
    );
    expect(v[0]!.items[0]!.state).toBe("not_started");
    expect(v[0]!.items[0]!.maxChars).toBe(200);
  });
});

describe("stateBadge — one per status, words + symbol", () => {
  it("not started, sent, returned with note, marked met / not yet with feedback", () => {
    expect(stateBadge(item())).toMatchObject({ labelKey: "student.homework.state.notStarted", symbol: "○", note: null });
    expect(stateBadge(item({ state: "submitted", feedback: "old" }))).toMatchObject({ labelKey: "student.homework.state.sent", note: null });
    expect(stateBadge(item({ state: "returned", feedback: "دوبارہ لکھیں" }))).toMatchObject({
      labelKey: "student.homework.state.returned",
      symbol: "↩",
      note: "دوبارہ لکھیں",
    });
    expect(stateBadge(item({ state: "marked", outcome: "met", feedback: "Well done" }))).toMatchObject({
      labelKey: "student.homework.state.markedMet",
      symbol: "●",
      note: "Well done",
    });
    expect(stateBadge(item({ state: "marked", outcome: "not_yet", feedback: null }))).toMatchObject({
      labelKey: "student.homework.state.markedNotYet",
      symbol: "◑",
      note: null,
    });
  });

  it("every badge and reason has words in both catalogs", () => {
    for (const locale of ["ur", "en"] as const) {
      const s = CATALOGS[locale].student.homework;
      for (const v of Object.values(s.state)) expect(v.trim()).not.toBe("");
      for (const v of Object.values(s.reason)) expect(v.trim()).not.toBe("");
      for (const v of Object.values(s.result)) expect(v.trim()).not.toBe("");
    }
  });

  it("resubmission is open while sent or returned; marked is final", () => {
    expect(isOpen("not_started")).toBe(true);
    expect(isOpen("submitted")).toBe(true);
    expect(isOpen("returned")).toBe(true);
    expect(isOpen("marked")).toBe(false);
  });
});

describe("submitGate — Send and the counter", () => {
  const base = { maxChars: 10, state: "not_started" as const, sending: false, online: true };

  it("is disabled while empty (whitespace counts as empty), with the reason", () => {
    expect(submitGate({ ...base, text: "" })).toEqual({ canSend: false, count: 0, over: false, reason: "student.homework.reason.empty" });
    expect(submitGate({ ...base, text: "   \n " }).canSend).toBe(false);
  });

  it("counts code points of the trimmed text, as the server does", () => {
    expect(charCount("  ab  ")).toBe(2);
    expect(charCount("😀😀")).toBe(2);
    expect(charCount("سلام")).toBe(4);
  });

  it("enables at exactly max_chars and disables one over", () => {
    expect(submitGate({ ...base, text: "a".repeat(10) })).toEqual({ canSend: true, count: 10, over: false, reason: null });
    expect(submitGate({ ...base, text: "a".repeat(11) })).toEqual({
      canSend: false,
      count: 11,
      over: true,
      reason: "student.homework.reason.tooLong",
    });
  });

  it("is disabled while sending, offline, or once marked", () => {
    expect(submitGate({ ...base, text: "ok", sending: true })).toMatchObject({ canSend: false, reason: null });
    expect(submitGate({ ...base, text: "ok", online: false })).toMatchObject({ canSend: false, reason: "student.homework.reason.offline" });
    expect(submitGate({ ...base, text: "ok", state: "marked" })).toMatchObject({ canSend: false, reason: "student.homework.reason.final" });
    expect(submitGate({ ...base, text: "ok", state: "returned" }).canSend).toBe(true);
  });

  it("builds a trimmed body, or none when empty or too long", () => {
    expect(submitBody("  جواب  ", 200)).toEqual({ text: "جواب" });
    expect(submitBody("   ", 200)).toBeNull();
    expect(submitBody("abc", 2)).toBeNull();
  });
});

describe("sendHomework — never claims a send that did not happen", () => {
  const key = draftKey("stu-1", "a1", "hw-1");

  it("offline: keeps the draft and does not call the server", async () => {
    const drafts = memoryDrafts();
    const send = vi.fn();
    const out = await sendHomework({ online: false, text: "میرا جواب", maxChars: 200, state: "not_started", draftKey: key, drafts, send });
    expect(out).toEqual({ kind: "offline", kept: true });
    expect(send).not.toHaveBeenCalled();
    expect(drafts.read(key)).toBe("میرا جواب");
    expect(sendOutcomeKey(out)).toBe("student.homework.result.offlineKept");
  });

  it("a network failure mid-send is the same: not sent, draft kept", async () => {
    const drafts = memoryDrafts();
    const send = vi.fn().mockRejectedValue(new ApiError(0, { code: "OFFLINE" }));
    const out = await sendHomework({ online: true, text: "hello", maxChars: 200, state: "submitted", draftKey: key, drafts, send });
    expect(out.kind).toBe("offline");
    expect(drafts.read(key)).toBe("hello");
  });

  it("says plainly when the phone could not keep the text either", async () => {
    const drafts = { ...memoryDrafts(), write: () => false };
    const out = await sendHomework({ online: false, text: "x", maxChars: 200, state: "not_started", draftKey: key, drafts, send: vi.fn() });
    expect(out).toEqual({ kind: "offline", kept: false });
    expect(sendOutcomeKey(out)).toBe("student.homework.result.offlineNotKept");
  });

  it("success: sends the trimmed text, clears the draft, and the item reads as sent", async () => {
    const drafts = memoryDrafts();
    const send = vi.fn().mockResolvedValue({ submission_id: "s1", state: "submitted", text: "hi" });
    const out = await sendHomework({ online: true, text: "  hi ", maxChars: 200, state: "returned", draftKey: key, drafts, send });
    expect(send).toHaveBeenCalledWith({ text: "hi" });
    expect(out.kind).toBe("sent");
    expect(drafts.read(key)).toBeNull();
    if (out.kind !== "sent") throw new Error("unreachable");
    expect(afterSent(item({ state: "returned", feedback: "redo" }), out)).toMatchObject({ state: "submitted", sentText: "hi", feedback: null });
  });

  it("a marked item is never sent; a 409 from the server reads as final", async () => {
    const send = vi.fn();
    expect(await sendHomework({ online: true, text: "x", maxChars: 200, state: "marked", draftKey: key, drafts: memoryDrafts(), send })).toEqual({
      kind: "final",
    });
    expect(send).not.toHaveBeenCalled();
    const conflict = vi.fn().mockRejectedValue(new ApiError(409, {}));
    const drafts = memoryDrafts();
    expect((await sendHomework({ online: true, text: "x", maxChars: 200, state: "submitted", draftKey: key, drafts, send: conflict })).kind).toBe("final");
  });

  it("maps 404, 403 and 422 honestly, keeping the draft", async () => {
    for (const [status, kind] of [
      [404, "not-found"],
      [403, "consent"],
      [422, "invalid"],
      [500, "error"],
    ] as const) {
      const drafts = memoryDrafts();
      const out = await sendHomework({
        online: true,
        text: "x",
        maxChars: 200,
        state: "not_started",
        draftKey: key,
        drafts,
        send: vi.fn().mockRejectedValue(new ApiError(status, {})),
      });
      expect(out.kind).toBe(kind);
      expect(drafts.read(key)).toBe("x");
    }
  });

  it("403 SHARING_REQUIRED says sharing is off and keeps the writing on the phone", async () => {
    const drafts = memoryDrafts();
    const out = await sendHomework({
      online: true,
      text: "my story",
      maxChars: 200,
      state: "not_started",
      draftKey: key,
      drafts,
      send: vi.fn().mockRejectedValue(new ApiError(403, { code: "SHARING_REQUIRED" })),
    });
    expect(out).toEqual({ kind: "sharing", kept: true });
    expect(sendOutcomeKey(out)).toBe("student.homework.result.sharingOff");
    expect(drafts.read(key)).toBe("my story");
  });

  it("starts from a kept draft, else from what was last sent; marked starts empty", () => {
    expect(initialText(item({ state: "submitted", sentText: "sent" }), "draft")).toBe("draft");
    expect(initialText(item({ state: "submitted", sentText: "sent" }), null)).toBe("sent");
    expect(initialText(item({ state: "marked", sentText: "sent" }), "draft")).toBe("");
  });
});

describe("localDrafts — browser storage, wrapped", () => {
  beforeEach(() => window.localStorage.clear());

  it("writes, reads, clears, and removes on empty text", () => {
    const key = draftKey("stu-1", "a1", "i1");
    expect(localDrafts.write(key, "abc")).toBe(true);
    expect(localDrafts.read(key)).toBe("abc");
    localDrafts.write(key, "");
    expect(localDrafts.read(key)).toBeNull();
  });

  it("clears one learner's drafts without touching another's", () => {
    localDrafts.write(draftKey("stu-1", "a", "i"), "one");
    localDrafts.write(draftKey("stu-2", "a", "i"), "two");
    window.localStorage.setItem("unrelated", "keep");
    clearHomeworkDrafts("stu-1");
    expect(localDrafts.read(draftKey("stu-1", "a", "i"))).toBeNull();
    expect(localDrafts.read(draftKey("stu-2", "a", "i"))).toBe("two");
    expect(window.localStorage.getItem("unrelated")).toBe("keep");
  });

  it("a throwing storage is 'nothing kept', never a crash", () => {
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceeded");
    });
    expect(localDrafts.write(draftKey("s", "a", "i"), "x")).toBe(false);
    spy.mockRestore();
  });
});

describe("HOMEWORK_PATHS — the contract's routes", () => {
  it("spells every endpoint once, with encoded segments", () => {
    expect(HOMEWORK_PATHS.learnerHomework("stu 1")).toBe("/v1/school/learners/stu%201/homework");
    expect(HOMEWORK_PATHS.submit("s", "a/1", "i")).toBe("/v1/school/learners/s/homework/a%2F1/items/i:submit");
    expect(HOMEWORK_PATHS.queue("c1", "submitted")).toBe("/v1/school/classes/c1/submissions?status=submitted");
    expect(HOMEWORK_PATHS.mark("sub-1")).toBe("/v1/school/submissions/sub-1:mark");
    expect(HOMEWORK_PATHS.return("sub-1")).toBe("/v1/school/submissions/sub-1:return");
    expect(HOMEWORK_PATHS.concern("sub-1")).toBe("/v1/school/submissions/sub-1:concern");
  });
});

// ---- teacher -------------------------------------------------------------------------------------------

const row = (over: Partial<SubmissionRowWire> = {}): SubmissionRowWire => ({
  submission_id: "s1",
  student_ref: "stu-1",
  learner_display_name: "Ali",
  assignment_id: "a1",
  objective_code: "M3.1",
  item_ref: "hw-1",
  prompt: { ur: "لکھیں" },
  text: "میرا جواب",
  state: "submitted",
  submitted_at: 100,
  ...over,
});

describe("queueView", () => {
  it("is oldest first, stable by id, and accepts either name field", () => {
    const v = queueView(
      [row({ submission_id: "b", submitted_at: 300 }), row({ submission_id: "z", submitted_at: 100, learner_display_name: undefined, display_name: "Sana" }), row({ submission_id: "a", submitted_at: 100 })],
      PREF,
    );
    expect(v.map((r) => r.submissionId)).toEqual(["a", "z", "b"]);
    expect(v[1]!.learnerName).toBe("Sana");
  });

  it("expands a rubric into one choice per score, keeping authored descriptors", () => {
    const r = rubricView(
      { max_score: 2, criteria: ["Explains", { criterion: { en: "Uses units" } }], levels: [{ score: 2, descriptor: { en: "Full" } }] },
      PREF,
    );
    expect(r!.maxScore).toBe(2);
    expect(r!.levels.map((l) => l.score)).toEqual([0, 1, 2]);
    expect(r!.levels[2]!.descriptor).toEqual({ text: "Full", locale: "en" });
    expect(r!.criteria.map((c) => c.text)).toEqual(["Explains", "Uses units"]);
    expect(rubricView(null, PREF)).toBeNull();
    expect(rubricView({ max_score: -1 }, PREF)).toBeNull();
  });
});

describe("markBody", () => {
  const rubric = { maxScore: 4 };

  it("requires an outcome", () => {
    expect(markBody({ outcome: null, score: "", feedback: "" }, null)).toEqual({
      ok: false,
      problems: { outcome: "teacher.marking.problems.outcome" },
    });
  });

  it("without a rubric, score is null whatever the form holds", () => {
    expect(markBody({ outcome: "met", score: "3", feedback: "  Good  " }, null)).toEqual({
      ok: true,
      body: { outcome: "met", score: null, feedback: "Good" },
    });
  });

  it("with a rubric, score is required and must be an integer in 0..max_score", () => {
    expect(markBody({ outcome: "met", score: "", feedback: "" }, rubric)).toMatchObject({
      ok: false,
      problems: { score: "teacher.marking.problems.scoreRequired" },
    });
    for (const bad of ["5", "-1", "1.5", "x"]) {
      expect(markBody({ outcome: "met", score: bad, feedback: "" }, rubric)).toMatchObject({
        ok: false,
        problems: { score: "teacher.marking.problems.scoreRange" },
      });
    }
    expect(markBody({ outcome: "not_yet", score: "0", feedback: "" }, rubric)).toEqual({
      ok: true,
      body: { outcome: "not_yet", score: 0, feedback: "" },
    });
    expect(markBody({ outcome: "met", score: "4", feedback: "" }, rubric)).toMatchObject({ ok: true, body: { score: 4 } });
  });

  it("caps feedback at 1000 characters", () => {
    expect(markBody({ outcome: "met", score: "", feedback: "a".repeat(FEEDBACK_MAX) }, null).ok).toBe(true);
    expect(markBody({ outcome: "met", score: "", feedback: "a".repeat(FEEDBACK_MAX + 1) }, null)).toMatchObject({
      ok: false,
      problems: { feedback: "teacher.marking.problems.feedbackTooLong" },
    });
  });

  it("reports every problem at once", () => {
    const out = markBody({ outcome: null, score: "", feedback: "a".repeat(1001) }, rubric);
    expect(out.ok).toBe(false);
    if (!out.ok) expect(Object.keys(out.problems).sort()).toEqual(["feedback", "outcome", "score"]);
  });
});

describe("returnBody — feedback is required", () => {
  it("refuses empty or whitespace feedback, trims, and caps at 1000", () => {
    expect(returnBody("")).toEqual({ ok: false, problems: { feedback: "teacher.marking.problems.returnFeedbackRequired" } });
    expect(returnBody("   ")).toMatchObject({ ok: false });
    expect(returnBody("  Add the units ")).toEqual({ ok: true, body: { feedback: "Add the units" } });
    expect(returnBody("a".repeat(1001))).toMatchObject({ ok: false, problems: { feedback: "teacher.marking.problems.feedbackTooLong" } });
  });
});

describe("concernBody — the safeguarding concern payload", () => {
  it("needs a known category", () => {
    expect(concernBody({ category: null, note: "" })).toEqual({ ok: false, problem: "teacher.marking.concern.categoryRequired" });
    expect(concernBody({ category: "nope" as never, note: "" }).ok).toBe(false);
  });

  it("carries only the category and the teacher's own note — never the child's text or a learner ref", () => {
    expect(concernBody({ category: "very_sad", note: "" })).toEqual({ ok: true, body: { category: "very_sad" } });
    const out = concernBody({ category: "felt_unsafe", note: "  Please check in  " });
    expect(out).toEqual({ ok: true, body: { category: "felt_unsafe", text: "Please check in" } });
    if (out.ok) expect(Object.keys(out.body).sort()).toEqual(["category", "text"]);
  });

  it("caps the note at the safeguarding free-text limit", () => {
    expect(concernBody({ category: "other", note: "a".repeat(501) })).toEqual({ ok: false, problem: "teacher.marking.concern.noteTooLong" });
  });
});

describe("teacher failure copy", () => {
  it("409 on mark/return says it was already decided; access stays non-leaking", () => {
    expect(decisionErrorKey(new ApiError(409, {}))).toBe("teacher.marking.errors.alreadyDecided");
    expect(decisionErrorKey(new ApiError(422, {}))).toBe("teacher.errors.checkDetails");
    expect(decisionErrorKey(new ApiError(404, {}))).toBe("teacher.errors.notAvailable");
    expect(decisionErrorKey(new ApiError(0, {}))).toBe("teacher.errors.offline");
    expect(concernErrorKey(new ApiError(403, {}))).toBe("teacher.errors.notAvailable");
    expect(concernErrorKey(new Error("x"))).toBe("teacher.errors.generic");
  });
});
