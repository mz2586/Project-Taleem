// HOMEWORK_AND_MARKING_CONTRACT.md §6 — the AI-led path, no teacher required. Pure view models plus
// react-dom/server markup (no jsdom): self-paced vs assignment grouping, copy per source, auto-marked
// vs self-check results, the compare block only after a send, and no teacher wording on self-paced items.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { HomeworkItemCard } from "@/components/student/HomeworkItemCard";

import { formatNumber } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import type { DraftStore } from "../drafts";
import {
  afterSent,
  compareView,
  homeworkGroups,
  homeworkView,
  initialText,
  isOpen,
  itemCopy,
  replaceItem,
  sendHomework,
  sendOutcomeKey,
  stateBadge,
  submitGate,
  type HomeworkItemView,
} from "../student";
import type { LearnerHomeworkWire } from "../types";

type Locale = "ur" | "en";
const PREF = ["ur", "en"] as const;

const wire: LearnerHomeworkWire = {
  assignments: [
    {
      assignment_id: "class-1",
      objective_code: "M3.1",
      class_name: "4B",
      due_at: 2000,
      source: "assignment",
      items: [{ item_ref: "c1", prompt: { en: "Explain" }, max_chars: 2000, marking: "teacher" }],
    },
    {
      assignment_id: "lesson-fractions",
      objective_code: "M3.2",
      lesson_title: { ur: "کسر", en: "Fractions" },
      due_at: null,
      items: [
        { item_ref: "s1", prompt: { en: "Half of 8?" }, max_chars: 200, source: "self_paced", marking: "auto" },
        {
          item_ref: "s2",
          prompt: { en: "Write a story" },
          max_chars: 2000,
          source: "self_paced",
          marking: "self_check",
          // Arrives on the item before any send: still never shown until submitted.
          compare: { sample_answer: { ur: "مثال", en: "An example" }, guidance: "Use three sentences." },
        },
      ],
    },
    // Untagged and no due date: the learner's own lesson practice.
    { assignment_id: "lesson-plain", objective_code: "M3.3", items: [{ item_ref: "p1", prompt: "x", max_chars: 200 }] },
  ],
};

const noDrafts: DraftStore = { read: () => null, write: () => true, clear: () => undefined };

const item = (over: Partial<HomeworkItemView> = {}): HomeworkItemView => ({
  assignmentId: "lesson-1",
  itemRef: "hw-1",
  prompt: { text: "Write about your home", locale: "en" },
  hints: [],
  maxChars: 200,
  state: "not_started",
  sentText: null,
  feedback: null,
  outcome: null,
  source: "self_paced",
  marking: "self_check",
  reviewedBy: null,
  compare: null,
  canRetry: false,
  ...over,
});

function render(over: Partial<HomeworkItemView>, locale: Locale = "en"): string {
  return renderToStaticMarkup(
    createElement(HomeworkItemCard, {
      item: item(over),
      position: 1,
      t: createTranslator(locale),
      formatNumber: (n: number) => formatNumber(n, locale),
      online: true,
      draftKey: "k",
      drafts: noDrafts,
      send: async () => undefined,
      onSent: () => undefined,
    }),
  );
}

const sendButton = (html: string) => /<button[^>]*type="submit"[^>]*>.*?<\/button>/s.exec(html)?.[0] ?? "";
const TEACHER = { en: /teacher/i, ur: /استاد/ } as const;

describe("parsing and grouping", () => {
  const view = homeworkView(wire, PREF, ["en", ...PREF]);

  it("reads source per item (item tag, else entry tag, else due date) and keeps self-paced undated", () => {
    expect(view.map((a) => [a.source, a.assignmentId, a.dueAt])).toEqual([
      ["assignment", "class-1", 2000],
      ["self_paced", "lesson-fractions", null],
      ["self_paced", "lesson-plain", null],
    ]);
    const [s1, s2] = view[1]!.items;
    expect(s1).toMatchObject({ source: "self_paced", marking: "auto" });
    expect(s2!.compare).toEqual({ sample: { text: "مثال", locale: "ur" }, guidance: { text: "Use three sentences.", locale: "" } });
    expect(view[2]!.items[0]).toMatchObject({ source: "self_paced", marking: null });
  });

  it("groups 'From your lessons' first, then 'From your class'; empty groups are left out", () => {
    const groups = homeworkGroups(view);
    expect(groups.map((g) => [g.source, g.headingKey, g.entries.length])).toEqual([
      ["self_paced", "student.homework.groups.lessons", 2],
      ["assignment", "student.homework.groups.classes", 1],
    ]);
    expect(homeworkGroups(view.filter((a) => a.source === "self_paced")).map((g) => g.source)).toEqual(["self_paced"]);
    expect(homeworkGroups([])).toEqual([]);
  });

  it("an entry mixing sources splits by source, and replaceItem touches only its own copy", () => {
    const mixed = homeworkView(
      {
        assignments: [
          {
            assignment_id: "a",
            objective_code: "x",
            due_at: 50,
            items: [
              { item_ref: "i", prompt: "p", max_chars: 200, source: "assignment" },
              { item_ref: "i", prompt: "p", max_chars: 200, source: "self_paced" },
            ],
          },
        ],
      },
      PREF,
    );
    expect(mixed.map((a) => [a.source, a.dueAt])).toEqual([
      ["assignment", 50],
      ["self_paced", null],
    ]);
    const next = { ...mixed[1]!.items[0]!, state: "submitted" as const };
    const after = replaceItem(mixed, next);
    expect(after[0]!.items[0]!.state).toBe("not_started");
    expect(after[1]!.items[0]!.state).toBe("submitted");
  });

  it("the empty state and intro speak of lessons, never a teacher", () => {
    for (const locale of ["en", "ur"] as const) {
      const t = createTranslator(locale);
      for (const key of ["student.homework.emptyTitle", "student.homework.emptyBody", "student.homework.intro", "student.homework.groups.lessons", "student.homework.groups.lessonsIntro"] as const) {
        expect(t(key)).not.toMatch(TEACHER[locale]);
      }
    }
    expect(createTranslator("en")("student.homework.emptyBody")).toContain("Finish a lesson and its practice will appear here");
    expect(createTranslator("en")("student.homework.intro")).toContain("Practice from your lessons");
  });
});

describe("copy per source", () => {
  it("self-paced: Check (auto) or Save (self-check); assignment: Send to my teacher", () => {
    expect(itemCopy(item({ marking: "auto" }))).toMatchObject({ send: "student.homework.checkAnswer", resendNote: "student.homework.resendNoteSelf" });
    expect(itemCopy(item({ marking: "self_check" }))).toMatchObject({ send: "student.homework.saveAnswer", sendAgain: "student.homework.saveAgain" });
    expect(itemCopy(item({ source: "assignment", marking: "teacher" }))).toMatchObject({
      send: "student.homework.send",
      resendNote: "student.homework.resendNote",
      final: "student.homework.reason.final",
    });
  });

  it("a submitted self-paced item is 'saved', an assignment 'sent to your teacher'", () => {
    expect(stateBadge(item({ state: "submitted" })).labelKey).toBe("student.homework.state.saved");
    expect(stateBadge(item({ state: "submitted", source: "assignment" })).labelKey).toBe("student.homework.state.sent");
  });

  it("the 'final' reason names Taleem for an auto mark and the teacher for a teacher's", () => {
    const auto = item({ state: "marked", outcome: "met", reviewedBy: "auto", marking: "auto" });
    expect(submitGate({ text: "x", maxChars: 10, state: "marked", sending: false, online: true, finalReason: itemCopy(auto).final }).reason).toBe(
      "student.homework.reason.finalChecked",
    );
    expect(itemCopy(item({ source: "assignment", state: "marked", reviewedBy: "teacher" })).final).toBe("student.homework.reason.final");
    expect(sendOutcomeKey({ kind: "final" }, auto)).toBe("student.homework.result.finalChecked");
  });
});

describe("result after submit", () => {
  const key = "k";

  it("auto-marked: the server's mark, Taleem's feedback and 'Checked by Taleem' — met and not yet", async () => {
    for (const outcome of ["met", "not_yet"] as const) {
      const out = await sendHomework({
        online: true,
        text: "4",
        maxChars: 200,
        state: "not_started",
        draftKey: key,
        drafts: noDrafts,
        send: vi.fn().mockResolvedValue({ submission_id: "s", state: "marked", outcome, reviewed_by: "auto", feedback: "Half of 8 is 4.", text: "4" }),
      });
      if (out.kind !== "sent") throw new Error("unreachable");
      const next = afterSent(item({ marking: "auto" }), out);
      expect(next).toMatchObject({ state: "marked", outcome, reviewedBy: "auto", feedback: "Half of 8 is 4." });
      expect(sendOutcomeKey(out, next)).toBe("student.homework.result.checked");
      const badge = stateBadge(next);
      expect(badge.labelKey).toBe(outcome === "met" ? "student.homework.state.checkedMet" : "student.homework.state.checkedNotYet");
      expect(badge.noteKey).toBe("student.homework.taleemNote");
      expect(compareView(next)).toBeNull();
    }
  });

  it("'marked' with no real outcome is not shown as a mark", () => {
    const next = afterSent(item({ marking: "auto" }), { kind: "sent", submission: { submission_id: "s", state: "marked" }, text: "4" });
    expect(next.state).toBe("submitted");
    expect(next.reviewedBy).toBeNull();
  });

  it("self-check: saved, not marked, and the comparison arrives with the answer", () => {
    const before = item();
    const next = afterSent(
      before,
      {
        kind: "sent",
        submission: { submission_id: "s", state: "submitted", marking: "self_check", compare: { sample_answer: { ur: "مثال", en: "Example" } } },
        text: "My story",
      },
      ["en", "ur"],
    );
    expect(next).toMatchObject({ state: "submitted", outcome: null, reviewedBy: null, sentText: "My story" });
    expect(compareView(next)).toEqual({ sample: { text: "Example", locale: "en" }, guidance: null });
    expect(sendOutcomeKey({ kind: "sent", submission: null, text: "x" }, next)).toBe("student.homework.result.savedCompare");
    expect(sendOutcomeKey({ kind: "sent", submission: null, text: "x" }, { ...next, compare: null })).toBe("student.homework.result.saved");
    // An assignment keeps its honest "sent to your teacher".
    expect(sendOutcomeKey({ kind: "sent", submission: null, text: "x" }, { ...next, source: "assignment" })).toBe("student.homework.result.sent");
  });

  it("no 'marked' wording anywhere a self-check item can show", () => {
    for (const locale of ["en", "ur"] as const) {
      const t = createTranslator(locale);
      const marked = locale === "en" ? /(?<!not )\bmarked\b/i : /جانچ ہو گئی/;
      for (const key of ["student.homework.state.saved", "student.homework.result.saved", "student.homework.result.savedCompare", "student.homework.compare.title"] as const) {
        expect(t(key)).not.toMatch(marked);
      }
    }
  });
});

describe("markup", () => {
  const compare = { sample: { text: "An example story", locale: "en" }, guidance: { text: "Three sentences", locale: "en" } };

  it("the compare block appears only after a self-check answer was sent", () => {
    expect(render({ compare })).not.toContain("data-compare");
    expect(render({ compare, state: "submitted", sentText: "Mine" })).toContain("data-compare");
    expect(render({ compare, state: "submitted", marking: "auto" })).not.toContain("data-compare");
    const html = render({ compare, state: "submitted", sentText: "Mine" });
    expect(html).toContain("Saved. Compare your answer:");
    expect(html).toContain("This answer was not marked.");
    expect(html).toContain("An example story");
    expect(html).toContain("Three sentences");
    expect(html).toContain("Saved (not marked)");
  });

  it("an auto-marked answer: 'Checked by Taleem', the feedback, read-only", () => {
    const met = render({ marking: "auto", state: "marked", outcome: "met", reviewedBy: "auto", feedback: "Half of 8 is 4.", sentText: "4" });
    expect(met).toContain("Checked by Taleem: ✓ Well done");
    expect(met).toContain("Taleem says:");
    expect(met).toContain("Half of 8 is 4.");
    expect(met).not.toContain("<textarea");
    const notYet = render({ marking: "auto", state: "marked", outcome: "not_yet", reviewedBy: "auto", feedback: "Try halving." }, "ur");
    expect(notYet).toContain("تعلیم نے جانچا: ابھی نہیں — دوبارہ کوشش کریں");
    expect(notYet).toContain("Try halving.");
  });

  it("no teacher wording on a self-paced item, in any state, in either language", () => {
    const states: Array<Partial<HomeworkItemView>> = [
      {},
      { marking: "auto" },
      { state: "submitted", sentText: "Mine", compare },
      { marking: "auto", state: "marked", outcome: "met", reviewedBy: "auto", sentText: "4", feedback: "Yes" },
      { marking: "auto", state: "marked", outcome: "not_yet", reviewedBy: "auto", sentText: "5" },
    ];
    for (const locale of ["en", "ur"] as const) {
      for (const over of states) expect(render(over, locale)).not.toMatch(TEACHER[locale]);
    }
    expect(sendButton(render({}))).toContain("Save my answer");
    expect(sendButton(render({ marking: "auto" }))).toContain("Check my answer");
  });

  it("an assignment keeps its teacher wording", () => {
    const html = render({ source: "assignment", marking: "teacher" });
    expect(sendButton(html)).toContain("Send to my teacher");
  });
});

describe("retry after Taleem's 'not yet' (can_retry)", () => {
  const notYet = { marking: "auto" as const, state: "marked" as const, outcome: "not_yet" as const, reviewedBy: "auto" as const, sentText: "5", feedback: "Try halving." };
  const entry = (sub: Record<string, unknown>, itemExtra: Record<string, unknown> = {}): LearnerHomeworkWire => ({
    assignments: [
      {
        assignment_id: "l",
        objective_code: "x",
        items: [{ item_ref: "i", prompt: "p", max_chars: 200, source: "self_paced", marking: "auto", ...itemExtra, submission: { submission_id: "s", ...sub } as never }],
      },
    ],
  });

  it("reads can_retry from the submission or the item; absent is false; a met stays final", () => {
    const read = (w: LearnerHomeworkWire) => homeworkView(w, PREF)[0]!.items[0]!.canRetry;
    expect(read(entry({ state: "marked", outcome: "not_yet", reviewed_by: "auto", can_retry: true }))).toBe(true);
    expect(read(entry({ state: "marked", outcome: "not_yet", reviewed_by: "auto" }, { can_retry: true }))).toBe(true);
    expect(read(entry({ state: "marked", outcome: "not_yet", reviewed_by: "auto" }))).toBe(false);
    expect(read(entry({ state: "marked", outcome: "not_yet", reviewed_by: "auto", can_retry: "yes" }))).toBe(false);
    expect(read(entry({ state: "marked", outcome: "met", reviewed_by: "auto", can_retry: true }))).toBe(false);
  });

  it("isOpen, the gate and sending follow can_retry", async () => {
    expect(isOpen("marked")).toBe(false);
    expect(isOpen("marked", true)).toBe(true);
    const gate = { text: "4", maxChars: 10, state: "marked" as const, sending: false, online: true };
    expect(submitGate(gate).canSend).toBe(false);
    expect(submitGate({ ...gate, canRetry: true })).toMatchObject({ canSend: true, reason: null });
    const send = vi.fn().mockResolvedValue({ submission_id: "s", state: "marked", outcome: "met", reviewed_by: "auto", text: "4" });
    expect(await sendHomework({ ...gate, draftKey: "k", drafts: noDrafts, send })).toEqual({ kind: "final" });
    expect(send).not.toHaveBeenCalled();
    const out = await sendHomework({ ...gate, canRetry: true, draftKey: "k", drafts: noDrafts, send });
    expect(out.kind).toBe("sent");
    if (out.kind !== "sent") throw new Error("unreachable");
    const next = afterSent(item({ ...notYet, canRetry: true }), out);
    expect(next).toMatchObject({ state: "marked", outcome: "met", canRetry: false });
    expect(initialText(item({ ...notYet, canRetry: true }), null)).toBe("5");
  });

  it("markup: 'Not yet — try again' leads to an editable answer and 'Check my answer'; without can_retry it is read-only", () => {
    const open = render({ ...notYet, canRetry: true });
    expect(open).toContain("Checked by Taleem: Not yet — try again");
    expect(open).toContain("Try halving.");
    expect(open).toContain("<textarea");
    expect(sendButton(open)).toContain("Check my answer");
    expect(sendButton(open)).not.toContain("disabled");
    const closed = render(notYet);
    expect(closed).not.toContain("<textarea");
    expect(sendButton(closed)).toBe("");
    const met = render({ ...notYet, outcome: "met", canRetry: false });
    expect(met).not.toContain("<textarea");
  });
});
