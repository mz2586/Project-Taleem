// Path, unit-check and record markup, rendered to static HTML in the node suite (react-dom/server; no
// jsdom). Checked: lesson titles and states as words + shape, the unit-check entry only when
// available, "Question n of N" and every item kind rendering through the shared interaction
// components, the finish screen, the record, and no certificate claim anywhere.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CheckQuestion } from "@/components/progression/CheckQuestion";
import { CheckResultPanel } from "@/components/progression/CheckResultPanel";
import { PathBrowser } from "@/components/progression/PathBrowser";
import { RecordSections } from "@/components/progression/RecordSections";

import { formatNumber, formatPercent } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import { guardianRecordLinks, LEARNER_RECORD_LINKS, questionOf, recordView, resultView, type ViewContext } from "../view";
import { academicRecord, checkItem, checkResult, pathView, type CheckItemView } from "../wire";

type Locale = "ur" | "en";
const ctxFor = (locale: Locale): ViewContext => ({ t: createTranslator(locale), locale, formatPercent: (r) => formatPercent(r, locale) });
const PREF = ["en", "ur"];
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

/** Every "certificate" in visible text is a denial. */
function noCertificateClaim(html: string) {
  const plain = text(html);
  for (const m of plain.matchAll(/certificat\w*/gi)) {
    expect(plain.slice(Math.max(0, m.index! - 20), m.index).toLowerCase()).toMatch(/not (a|an accredited) $|, not $/);
  }
  for (const m of plain.matchAll(/سرٹیفکیٹ/g)) expect(plain.slice(m.index! + m[0].length)).toMatch(/^ نہیں/);
}

const path = pathView(
  {
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
              { lesson_id: "L2", objective_code: "M4.F.2", title: { ur: "چوتھائی" }, state: "mastered" },
            ],
            check: { available: true },
          },
          { unit_key: "u2", title: { en: "Decimals" }, state: "not_started", lessons: [], check: { available: false } },
        ],
      },
    ],
    next_step: { kind: "unit_check", unit_key: "u1", title: { en: "Fractions check" } },
  },
  PREF,
);

describe("PathBrowser", () => {
  it.each<Locale>(["en", "ur"])("%s: subjects → units → lessons with states in words", (locale) => {
    const ctx = ctxFor(locale);
    const html = renderToStaticMarkup(createElement(PathBrowser, { path, ctx }));
    expect(html).toContain("Halves");
    expect(html).toContain('lang="ur" dir="rtl">چوتھائی');
    expect(html).toContain('data-lesson-state="practised"');
    expect(html).toContain('data-lesson-state="mastered"');
    expect(html).toContain(ctx.t("progression.lessonState.practised"));
    expect(html).toContain(ctx.t("progression.lessonState.mastered"));
    // Exactly one unit-check entry: the available one.
    expect(html.match(/data-check-entry/g)?.length).toBe(1);
    expect(html).toContain('href="/student/subjects/u1/check"');
    expect(html).toContain(ctx.t("progression.check.claim"));
    expect(html).toContain(ctx.t("progression.path.nextTitle"));
    // The working unit is open; the untouched one is closed.
    expect(html).toMatch(/<details open=""[^>]*data-unit="u1"/);
    expect(html).not.toMatch(/<details open=""[^>]*data-unit="u2"/);
    noCertificateClaim(html);
  });
});

describe("CheckQuestion", () => {
  const items: CheckItemView[] = [
    checkItem({ item_ref: "c", kind: "choose", prompt: { en: "Pick half" }, options: ["1/2", "1/3"] }, PREF)!,
    checkItem({ item_ref: "f", kind: "fill", prompt: "Write half" }, PREF)!,
    checkItem({ item_ref: "o", kind: "order", options: ["a", "b", "c"] }, PREF)!,
    checkItem({ item_ref: "m", kind: "match", options: ["x", "y", "1", "2"], left_count: 2 }, PREF)!,
    checkItem({ item_ref: "s", kind: "sort", options: ["x", "y", "A", "B"], left_count: 2 }, PREF)!,
  ];

  it.each(items.map((i) => [i.kind, i] as const))("renders a %s item with progress and a disabled save until answered", (_kind, item) => {
    const t = createTranslator("en");
    const html = renderToStaticMarkup(
      createElement(CheckQuestion, {
        item,
        t,
        formatNumber: (n: number) => formatNumber(n, "en"),
        progress: questionOf(2, 10, t),
        disabled: false,
        onAnswer: () => undefined,
      }),
    );
    expect(html).toContain("Question 3 of 10");
    expect(html).toContain(`data-kind="${item.kind}"`);
    expect(html).not.toContain(t("student.session.items.unavailable"));
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>.*?Save my answer/s);
  });

  it("disables everything while offline", () => {
    const t = createTranslator("ur");
    const html = renderToStaticMarkup(
      createElement(CheckQuestion, { item: items[0]!, t, formatNumber: (n: number) => String(n), progress: questionOf(0, 10, t), disabled: true, onAnswer: () => undefined }),
    );
    expect(html.match(/<button[^>]*aria-pressed="false"[^>]*disabled=""/g)?.length).toBe(2);
  });
});

describe("CheckResultPanel", () => {
  it.each<Locale>(["en", "ur"])("%s: score, not yet, breakdown, remediation and the claim", (locale) => {
    const ctx = ctxFor(locale);
    const view = resultView(
      checkResult(
        {
          score_percent: 40,
          passed: false,
          pass_mark: 70,
          per_objective: [{ objective_code: "A", title: { en: "Halves" }, correct: 2, total: 5 }],
          remediation: [{ objective_code: "A", title: { en: "Halves" } }],
        },
        PREF,
      ),
      ctx,
    );
    const html = renderToStaticMarkup(createElement(CheckResultPanel, { view, t: ctx.t }));
    expect(html).toContain('data-outcome="not_yet"');
    expect(html).toContain(view.score);
    expect(html).toContain(ctx.t("progression.result.notYetTitle"));
    expect(html).toContain(ctx.t("progression.result.objectiveLine", { correct: 2, total: 5 }));
    expect(html).toContain('href="/student/session?lesson=A"');
    expect(html).toContain(ctx.t("progression.check.claim"));
    if (locale === "en") expect(text(html).toLowerCase()).not.toMatch(/\bfail(ed)?\b/);
    noCertificateClaim(html);
  });
});

describe("RecordSections", () => {
  const record = academicRecord(
    {
      grade: 4,
      grade_state: "completed",
      grade_completed_at: 1_800_000_000,
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
                { sitting_id: "a", finished_at: 1_790_000_000, score_percent: 80, passed: true },
                { sitting_id: "b", started_at: 1_791_000_000, state: "incomplete" },
              ],
            },
          ],
        },
      ],
      lessons_mastered: [],
      report_cards: [{ card_id: "rc1", issued_at: 1_795_000_000 }],
      derived_at: 1_800_000_000,
    },
    PREF,
  );

  it.each<Locale>(["en", "ur"])("%s: grade, completion labelled not accredited, sittings, lessons, report cards", (locale) => {
    const ctx = ctxFor(locale);
    const html = renderToStaticMarkup(createElement(RecordSections, { view: recordView(record, ctx, LEARNER_RECORD_LINKS), t: ctx.t }));
    expect(html).toContain(ctx.t("progression.record.grade", { grade: 4 }));
    expect(html).toContain("data-grade-complete");
    expect(html).toContain(ctx.t("progression.record.gradeCompleted", { grade: 4 }));
    expect(html).toContain('data-sitting-state="passed"');
    expect(html).toContain('data-sitting-state="incomplete"');
    expect(html).toContain(ctx.t("progression.record.incomplete"));
    expect(html).toContain(ctx.t("progression.record.noLessonsMastered"));
    expect(html).toContain('href="/student/report-cards/rc1"');
    noCertificateClaim(html);
  });

  it("links a guardian's view to the child's report cards", () => {
    const ctx = ctxFor("en");
    const html = renderToStaticMarkup(createElement(RecordSections, { view: recordView(record, ctx, guardianRecordLinks("S1")), t: ctx.t }));
    expect(html).toContain('href="/guardian/children/S1/report-cards/rc1"');
    expect(html).toContain("Grade 4 completed in Taleem — not an accredited certificate");
  });
});
