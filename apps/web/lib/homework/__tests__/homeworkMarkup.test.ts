// Homework and marking markup, rendered to static HTML in the node suite (react-dom/server; no jsdom).
// Checked: a real label bound to a dir="auto" textarea with a visible counter, Send disabled with its
// reason (empty / offline), a marked answer read-only, the teacher's note shown, and the teacher
// card's labelled radio groups, required send-back feedback and a separate safeguarding action.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SubmissionCard } from "@/app/teacher/classes/[classId]/marking/SubmissionCard";
import { HomeworkItemCard } from "@/components/student/HomeworkItemCard";

import { formatNumber } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import type { DraftStore } from "../drafts";
import type { HomeworkItemView } from "../student";
import { rowView } from "../teacher";

type Locale = "ur" | "en";

const noDrafts: DraftStore = { read: () => null, write: () => true, clear: () => undefined };

function renderItem(over: Partial<HomeworkItemView> = {}, opts: { locale?: Locale; online?: boolean } = {}): string {
  const locale = opts.locale ?? "ur";
  const t = createTranslator(locale);
  const item: HomeworkItemView = {
    assignmentId: "a1",
    itemRef: "hw-1",
    prompt: { text: "اپنے گھر کے بارے میں لکھیں", locale: "ur" },
    hints: [],
    maxChars: 200,
    state: "not_started",
    sentText: null,
    feedback: null,
    outcome: null,
    source: "assignment",
    marking: null,
    reviewedBy: null,
    compare: null,
    canRetry: false,
    ...over,
  };
  const html = renderToStaticMarkup(
    createElement(HomeworkItemCard, {
      item,
      position: 1,
      t,
      formatNumber: (n: number) => formatNumber(n, locale),
      online: opts.online ?? true,
      draftKey: "k",
      drafts: noDrafts,
      send: async () => undefined,
      onSent: () => undefined,
    }),
  );
  return `<div dir="${locale === "ur" ? "rtl" : "ltr"}">${html}</div>`;
}

const sendButton = (html: string) => /<button[^>]*type="submit"[^>]*>.*?<\/button>/s.exec(html)?.[0] ?? "";

describe("HomeworkItemCard", () => {
  it("labels a dir=auto textarea and shows the counter against max_chars", () => {
    const html = renderItem();
    expect(html).toMatch(/<label for="([^"]+)"[^>]*>آپ کا جواب<\/label>.*<textarea id="\1"/s);
    expect(html).toContain('dir="auto"');
    expect(html).toContain("200 میں سے 0 حروف");
    expect(html).toContain('lang="ur" dir="rtl"');
    expect(html).toContain("ابھی شروع نہیں کیا");
  });

  it("starts with Send disabled and the reason beside it", () => {
    const html = renderItem({}, { locale: "en" });
    const button = sendButton(html);
    expect(button).toContain("disabled");
    expect(button).toContain("Send to my teacher");
    expect(button).toMatch(/aria-describedby="[^"]+-reason"/);
    expect(html).toContain("Write your answer first.");
    expect(html).toContain("0 of 200 letters");
  });

  it("offline, says it cannot be sent now and keeps the writing — never 'sent'", () => {
    const html = renderItem({ state: "returned", sentText: "old", feedback: "Add more" }, { locale: "en", online: false });
    expect(sendButton(html)).toContain("disabled");
    expect(html).toContain("No internet: this cannot be sent now. Your writing is kept on this phone.");
    expect(html).not.toContain("Sent to your teacher.");
    // Returned: the teacher's note, and a resend label.
    expect(html).toContain("Your teacher asked you to try again");
    expect(html).toContain("Add more");
    expect(sendButton(html)).toContain("Send again");
    expect(html).toContain(">old</textarea>");
  });

  it("a marked answer is read-only: no textarea, no Send, the feedback and what was sent", () => {
    const html = renderItem({ state: "marked", outcome: "met", feedback: "شاباش", sentText: "میرا گھر" });
    expect(html).not.toContain("<textarea");
    expect(sendButton(html)).toBe("");
    expect(html).toContain("جانچ ہو گئی: آپ نے کر دکھایا");
    expect(html).toContain("شاباش");
    expect(html).toContain("میرا گھر");
  });
});

describe("SubmissionCard", () => {
  const view = rowView(
    {
      submission_id: "s1",
      student_ref: "stu-1",
      learner_display_name: "Ali",
      assignment_id: "a1",
      objective_code: "M3.1",
      item_ref: "hw-1",
      prompt: { en: "Explain" },
      rubric: { max_score: 2, levels: [{ score: 2, descriptor: { en: "Complete" } }] },
      sample_answer: { en: "Because…" },
      text: "My answer",
      state: "submitted",
      submitted_at: 1_700_000_000,
    },
    ["ur", "en"],
  );

  const render = (locale: Locale = "en") =>
    renderToStaticMarkup(createElement(SubmissionCard, { row: view, t: createTranslator(locale), locale, onDecided: () => undefined }));

  it("shows the learner, prompt, the child's text, rubric and sample answer", () => {
    const html = render();
    expect(html).toContain("<bdi>Ali</bdi>");
    expect(html).toContain('lang="en" dir="ltr"');
    expect(html).toContain("My answer");
    expect(html).toContain("Score out of 2");
    expect(html).toContain("Complete");
    expect(html).toContain("Because…");
  });

  it("has labelled outcome and score radio groups, a bounded feedback box and required send-back feedback", () => {
    const html = render();
    expect(html).toMatch(/<legend[^>]*>Outcome<\/legend>/);
    expect(html).toContain('value="met"');
    expect(html).toContain('value="not_yet"');
    expect(html).toMatch(/<legend[^>]*>Rubric score \(0 to 2\)<\/legend>/);
    expect((html.match(/name="[^"]+-score"/g) ?? []).length).toBe(3);
    expect(html).toContain("0 of 1,000 characters");
    expect(html).toContain('required="" aria-required="true"');
    expect(html).toContain("What should the learner change? (required)");
  });

  it("offers the safeguarding concern as its own action, closed until asked (no confirm dialog yet)", () => {
    const html = render("ur");
    expect(html).toContain('data-concern="closed"');
    expect(html).toContain("حفاظت سے متعلق تشویش درج کریں");
    expect(html).not.toContain("ہاں، تشویش بھیجیں");
  });
});
