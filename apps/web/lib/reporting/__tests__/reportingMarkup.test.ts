// Report-card markup, rendered to static HTML in the node suite (react-dom/server; no jsdom).
// Checked: the mastery indicator always carries a text label (dots are aria-hidden); a card with no
// evidence says so and shows no figures; the version pin is present; the acknowledge button exists
// only until it is recorded, and never for a learner; the teacher's comment field has a real label
// and counter; and the print view leaves the shell header, navigation and buttons off the page.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CommentField } from "@/app/teacher/classes/[classId]/report-cards/CommentField";
import { GuardianShell } from "@/app/guardian/GuardianShell";
import { GenerateReport } from "@/components/reporting/GenerateReport";
import { ReportCardActions } from "@/components/reporting/ReportCardActions";
import { ReportCardList } from "@/components/reporting/ReportCardList";
import { MasteryIndicator, ReportCardView } from "@/components/reporting/ReportCardView";

import { createTranslator } from "../../i18n/translate";
import { periodOptions, type PeriodChoice } from "../generate";
import type { ReportCardWire } from "../types";
import { cardListView, cardView, type AckState } from "../view";
import { reportCard } from "../wire";

const noop = () => undefined;

function card(over: Partial<ReportCardWire> = {}): ReportCardWire {
  return {
    card_id: "rc-1",
    student_ref: "S1",
    learner_display_name: "عائشہ",
    class_name: "Class 4",
    period_start: 1_780_000_000,
    period_end: 1_787_000_000,
    issued_at: 1_787_000_000,
    issued_by_name: "Ms Sana",
    comment: "بہت اچھا کام",
    content_hash: "abcdef0123456789",
    curriculum_pack: "pk-2026.1",
    has_evidence: true,
    subjects: [
      {
        subject_key: "math",
        subject_name: { ur: "ریاضی", en: "Maths" },
        objectives: [
          { objective_code: "M4.1", title: { ur: "جمع", en: "Addition" }, mastery: "developing", attempts: 4, correct: 2, lesson_id: "L-12", lesson_version: 3 },
          { objective_code: "M4.2", title: { en: "Subtraction" }, mastery: "not_started", attempts: 0, correct: 0 },
        ],
      },
    ],
    ...over,
  };
}

function render(over: Partial<ReportCardWire> = {}, locale: "ur" | "en" = "en"): string {
  const t = createTranslator(locale);
  const view = cardView(reportCard(card(over), [locale]), { t, locale, timeZone: "UTC" });
  return renderToStaticMarkup(createElement(ReportCardView, { view, t }));
}

const strip = (html: string) => html.replace(/<[^>]+>/g, "");

describe("mastery indicator", () => {
  it.each([
    ["mastered", "en", "Learned well"],
    ["developing", "en", "Still learning"],
    ["not_started", "en", "Not started yet"],
    ["mastered", "ur", "اچھی طرح سیکھ لیا"],
    ["developing", "ur", "سیکھنا جاری ہے"],
  ] as const)("%s (%s) has a visible text label; the dots are decorative", (mastery, locale, label) => {
    const t = createTranslator(locale);
    const html = renderToStaticMarkup(createElement(MasteryIndicator, { mastery, label: t(`common.reportCard.mastery.${mastery}`) }));
    expect(html).toContain(label);
    expect(html).toMatch(/<span aria-hidden="true"[^>]*>[●○]{3}<\/span>/);
    // The label itself is not hidden.
    expect(html).toMatch(new RegExp(`<strong>.*${label}</strong>`));
  });
});

describe("report card view", () => {
  it("shows subjects, mastery words, counts, the version pin and the teacher's note", () => {
    const html = render();
    expect(html).toContain("<h2");
    expect(html).toContain("Report card: <bdi>عائشہ</bdi>");
    expect(html).toContain("Maths");
    expect(html).toContain("Still learning");
    expect(html).toContain("Questions answered: 4 · Right answers: 2");
    expect(html).toContain("No practice in these dates.");
    expect(html).toContain("Learned from lesson L-12 v3");
    expect(html).toContain("Teacher&#x27;s note");
    expect(html).toContain('<p dir="auto"');
    expect(html).toContain("بہت اچھا کام");
    expect(html).toContain("Curriculum: pk-2026.1");
    // Authored Urdu inside an English page keeps its own direction.
    expect(render({}, "ur")).toContain('lang="ur" dir="rtl"');
  });

  it("with no evidence, says no learning was recorded in this period and shows no figures", () => {
    const html = render({
      has_evidence: false,
      notice: "no_evidence_in_period",
      totals: null,
      subjects: [{ subject_key: "math", objectives: [{ objective_code: "M4.1", mastery: "not_started", attempts: 0, correct: 0 }] }],
    });
    expect(html).toContain("No learning recorded in this period");
    expect(html).toContain("data-no-evidence");
    expect(html).not.toContain("data-totals");
    expect(html).not.toContain("In short");
    expect(html).toContain("This is not a mark of zero.");
    expect(html).not.toContain("Questions answered");
    expect(html).not.toContain("Right answers");
    expect(html).not.toContain("Not started yet");
    expect(strip(html)).not.toMatch(/:\s*0\b/);
    expect(render({ has_evidence: false }, "ur")).toContain("اس مدت میں کوئی سیکھنا درج نہیں ہوا");
  });

  it("a replaced card says so in words and links to the newer card", () => {
    const t = createTranslator("en");
    const view = cardView(reportCard(card({ superseded_by: "rc-2" }), ["en"]), { t, locale: "en" });
    const html = renderToStaticMarkup(createElement(ReportCardView, { view, t, newerHref: "/x/rc-2" }));
    expect(html).toContain("This card was replaced");
    expect(html).toContain('href="/x/rc-2"');
  });

  it("the compact teacher preview keeps the summary and drops the objective rows", () => {
    const t = createTranslator("en");
    const view = cardView(reportCard(card({ card_id: null, issued_at: null }), ["en"]), { t, locale: "en" });
    const html = renderToStaticMarkup(createElement(ReportCardView, { view, t, compact: true, headingLevel: 3 }));
    expect(html).toContain("<h3");
    expect(html).toContain("<h4");
    expect(html).toContain("Preview — not issued yet");
    expect(html).toContain("Learned well: 0 · Still learning: 1 · Not started yet: 1");
    expect(html).not.toContain("Questions answered");
  });
});

describe("issuer, totals and integrity", () => {
  const system = { issued_by: "system", issued_by_name: "Taleem", class_id: null, class_name: null, comment: null } as const;

  it("a system card says 'Issued by Taleem', has no class line and no teacher's note", () => {
    const html = render({ ...system, totals: { objectives: 2, objectives_mastered: 0, attempts: 4, correct: 2 } });
    expect(html).toMatch(/<p data-issuer="system"[^>]*>Issued by Taleem on /);
    expect(html).not.toContain("Class:");
    expect(html).not.toContain("Teacher&#x27;s note");
    expect(html).not.toContain("Written by");
    expect(render(system, "ur")).toMatch(/<p data-issuer="system"[^>]*>تعلیم نے .* کو جاری کیا<\/p>/);
  });

  it("a teacher's card names the teacher; the note section appears only when there is a note", () => {
    const withNote = render({ issued_by: "T-7" });
    expect(withNote).toMatch(/<p data-issuer="teacher"[^>]*>Issued by Ms Sana on /);
    expect(withNote).toContain("Teacher&#x27;s note");
    const without = render({ issued_by: "T-7", comment: null });
    expect(without).toMatch(/Issued by Ms Sana on /);
    expect(without).not.toContain("Teacher&#x27;s note");
  });

  it("shows the totals as a short plain list", () => {
    const html = render({ totals: { objectives: 2, objectives_mastered: 1, attempts: 4, correct: 2, homework_met: 0, homework_not_yet: 0 } });
    expect(html).toContain("In short");
    expect(html).toContain("<li>Topics learned well: 1 of 2</li>");
    expect(html).toContain("<li>Questions answered: 4 · Right answers: 2</li>");
    expect(html).not.toContain("<li>Homework done well");
  });

  it("a card that failed its hash re-check carries a visible warning; a verified one does not", () => {
    const bad = render({ hash_verified: false });
    expect(bad).toMatch(/<div role="alert" data-integrity="failed"/);
    expect(strip(bad)).toContain("This card did not pass its safety check");
    expect(strip(bad)).toContain("Do not rely on it, and please tell Taleem.");
    expect(render({ hash_verified: false }, "ur")).toContain("یہ کارڈ حفاظتی جانچ میں پورا نہیں اترا");
    expect(render({ hash_verified: true })).not.toContain("data-integrity");
    const t = createTranslator("en");
    const html = renderToStaticMarkup(
      createElement(ReportCardList, {
        items: cardListView([reportCard(card({ hash_verified: false }), ["en"])], { t, locale: "en" }),
        hrefFor: (id: string) => `/cards/${id}`,
        label: "Report cards",
        newestLabel: "Newest",
        supersededLabel: "Replaced",
        unverifiedLabel: t("common.reportCard.listUnverified"),
      }),
    );
    expect(html).toContain('data-integrity="failed"');
    expect(html).toContain("Did not pass its safety check");
  });
});

describe("get a report (guardian)", () => {
  const NOW = Date.UTC(2026, 9, 24, 15) / 1000;
  const panel = (choice: PeriodChoice, locale: "en" | "ur" = "en", extra: Record<string, unknown> = {}) => {
    const t = createTranslator(locale);
    return renderToStaticMarkup(
      createElement(GenerateReport, {
        t,
        options: periodOptions(NOW, { t, locale, timeZone: "UTC" }),
        choice,
        onChoice: noop,
        custom: { start: "2026-09-01", end: "2026-09-30" },
        onCustom: noop,
        maxDate: "2026-10-24",
        busy: false,
        message: null,
        onSubmit: noop,
        ...extra,
      }),
    );
  };

  it("offers labelled period choices with their dates and a Generate button; custom fields stay hidden", () => {
    const html = panel("last_month");
    expect(html).toContain("<h2");
    expect(html).toContain("Get a report");
    expect(html).toMatch(/<label[^>]*><input type="radio" name="report-period" checked="" value="last_month"/);
    expect(html).toContain("From Sep 1, 2026 to Sep 30, 2026");
    expect(html).toContain("This term so far");
    expect(html).toContain("Other dates (advanced)");
    expect(html).not.toContain("data-custom-dates");
    expect(html).toMatch(/<button type="submit"[^>]*aria-label="Get the report"/);
    expect(panel("last_month", "ur")).toContain("رپورٹ حاصل کریں");
  });

  it("shows the two labelled date fields only for the advanced choice", () => {
    const html = panel("custom");
    expect(html).toContain("data-custom-dates");
    expect(html).toMatch(/<label for="generate-start"[^>]*>From<\/label>/);
    expect(html).toMatch(/<input[^>]*type="date"[^>]*max="2026-10-24"/);
  });

  it("shows an answer that is not a card in plain words, politely announced", () => {
    const html = panel("last_month", "en", { message: { title: "Please wait", body: "Please wait a few minutes and try again." } });
    expect(html).toMatch(/<div aria-live="polite"><div data-generate-message=""/);
    expect(html).toContain("Please wait a few minutes and try again.");
    const busy = panel("last_month", "en", { busy: true });
    expect(busy).toMatch(/<button type="submit"[^>]*disabled=""/);
    expect(busy).toContain("Making the report…");
  });
});

describe("acknowledge and print", () => {
  const t = createTranslator("en");
  const actions = (ack: AckState | null, seenDate: string | null = null) =>
    renderToStaticMarkup(createElement(ReportCardActions, { t, ack, seenDate, onAcknowledge: noop, onPrint: noop }));

  it("offers 'I have seen this' until it is recorded, then only says when", () => {
    expect(actions({ status: "unseen" })).toContain("I have seen this");
    const seen = actions({ status: "seen", at: 1, justNow: true }, "24 Oct 2026");
    expect(seen).not.toContain("I have seen this");
    expect(seen).toContain("You marked this as seen on 24 Oct 2026.");
    expect(seen).toContain("It is recorded that you have looked at this card.");
    const busy = actions({ status: "sending" });
    expect(busy).toMatch(/<button[^>]*disabled=""[^>]*aria-label="I have seen this"/);
  });

  it("a learner (no acknowledge) gets only the print button", () => {
    const html = actions(null);
    expect(html).not.toContain("I have seen this");
    expect(html).toContain("Print or save as PDF");
  });

  it("buttons are left off the printed page, the 'seen on' line is kept", () => {
    const html = actions({ status: "seen", at: 1, justNow: false }, "24 Oct 2026");
    const hidden = [...html.matchAll(/<div data-print="hide"[^>]*>(.*?)<\/div>/gs)].map((m) => m[1]).join("");
    expect(hidden).toContain("Print or save as PDF");
    expect(hidden).not.toContain("You marked this as seen");
  });

  it("the print stylesheet hides marked chrome, prints on A4 and lets the shell grow", () => {
    const css = readFileSync(fileURLToPath(new URL("../../../design-system/print.css", import.meta.url)), "utf8");
    expect(css).toMatch(/@media print/);
    expect(css).toMatch(/size:\s*A4/);
    expect(css).toMatch(/\[data-print="hide"\][\s\S]*?display:\s*none !important/);
    expect(css).toMatch(/\[data-print-shell\][\s\S]*?overflow:\s*visible !important/);
    const layout = readFileSync(fileURLToPath(new URL("../../../app/layout.tsx", import.meta.url)), "utf8");
    expect(layout).toContain('import "../design-system/print.css"');
  });

  it("the guardian shell's header and navigation are marked to hide when printing", () => {
    // children passed positionally (react/no-children-prop); the prop type is loosened for that.
    const Shell = GuardianShell as unknown as (props: { title: string; children?: ReactNode }) => ReactNode;
    const html = renderToStaticMarkup(createElement(Shell, { title: "Report card" }, createElement("p", null, "body")));
    expect(html).toMatch(/<header data-print="hide"[^>]*>[\s\S]*<nav[\s\S]*<\/nav><\/header>/);
    expect(html).toContain("data-print-shell");
    expect(html).toMatch(/<main[^>]*>.*body.*<\/main>/s);
  });
});

describe("list and comment field", () => {
  it("lists newest first with replaced cards marked in words", () => {
    const t = createTranslator("en");
    const cards = [card({ card_id: "a", issued_at: 1 }), card({ card_id: "b", issued_at: 2, supersedes: "a" })].map((w) => reportCard(w, ["en"]));
    const html = renderToStaticMarkup(
      createElement(ReportCardList, {
        items: cardListView(cards, { t, locale: "en" }),
        hrefFor: (id: string) => `/cards/${id}`,
        label: "Report cards, newest first",
        newestLabel: "Newest",
        supersededLabel: "Replaced by a newer card",
        seenLabels: ["Seen", "Not looked at yet"],
      }),
    );
    expect(html.indexOf('href="/cards/b"')).toBeLessThan(html.indexOf('href="/cards/a"'));
    expect(html).toContain("Replaced by a newer card");
    expect(html).toContain("Newest");
    expect(html).toContain("Not looked at yet");
  });

  it("the teacher's note has a real label, a counter and a limit message", () => {
    const t = createTranslator("ur");
    const ok = renderToStaticMarkup(createElement(CommentField, { id: "c1", value: "شاباش", onChange: noop, t }));
    expect(ok).toMatch(/<label for="c1">سرپرست کے لیے پیغام \(اختیاری\)<\/label>/);
    expect(ok).toContain('<textarea id="c1" dir="auto"');
    expect(ok).toContain("1,000 میں سے 5 حروف");
    const long = renderToStaticMarkup(createElement(CommentField, { id: "c2", value: "x".repeat(1001), onChange: noop, t: createTranslator("en") }));
    expect(long).toContain('aria-invalid="true"');
    expect(long).toContain("1,001 of 1,000 letters");
    expect(long).toContain("The note is too long. Use at most 1,000 letters.");
  });
});
