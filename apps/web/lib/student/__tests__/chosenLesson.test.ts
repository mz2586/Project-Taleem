// A lesson the child chose: the link targets (Learn's lesson rows, unit-check remediation), the
// session page reading `?lesson=`, and the gentle "You chose this lesson" + prerequisite hint —
// rendered to static markup in the node suite (react-dom/server; no jsdom).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PathBrowser } from "@/components/progression/PathBrowser";
import { ChosenLessonNotice } from "@/components/student/ChosenLessonNotice";

import { formatPercent } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import { resultView, type ViewContext } from "../../progression/view";
import { checkResult, pathView } from "../../progression/wire";
import { choiceNotice, lessonHref, readChosenLesson, SESSION_HREF, type LearnerChoiceWire } from "../chosenLesson";

type Locale = "ur" | "en";
const PREF = ["en", "ur"];
const ctxFor = (locale: Locale): ViewContext => ({ t: createTranslator(locale), locale, formatPercent: (r) => formatPercent(r, locale) });

const choice = (unmet: LearnerChoiceWire["prerequisite_hint"]): LearnerChoiceWire => ({
  objective_code: "M4.F.2",
  chosen_by: "learner",
  rationale: ["You chose this lesson; the AI teacher suggested teach M4.F.1"],
  reasons: [],
  recommended: { decision: "teach", objective_code: "M4.F.1" },
  prerequisite_hint: unmet,
});

describe("lessonHref / readChosenLesson", () => {
  it("links one lesson by objective code, and the plain session without one", () => {
    expect(lessonHref("M4.F.2")).toBe("/student/session?lesson=M4.F.2");
    expect(lessonHref("A B/C")).toBe("/student/session?lesson=A%20B%2FC");
    expect(lessonHref("")).toBe(SESSION_HREF);
    expect(lessonHref(null)).toBe(SESSION_HREF);
  });

  it("reads the chosen lesson back from the URL, ignoring anything that is not a code", () => {
    const read = (q: string) => readChosenLesson(new URLSearchParams(q));
    expect(read(new URL(`http://x${lessonHref("M4.F.2")}`).search)).toBe("M4.F.2");
    expect(read("lesson=%20M4.F.2%20")).toBe("M4.F.2");
    expect(read("")).toBeNull();
    expect(read("lesson=")).toBeNull();
    expect(read("lesson=<script>")).toBeNull();
    expect(read(`lesson=${"x".repeat(65)}`)).toBeNull();
    expect(readChosenLesson(null)).toBeNull();
  });
});

describe("choiceNotice", () => {
  const t = createTranslator("en");

  it("is null when the AI teacher chose (or an older server says nothing)", () => {
    expect(choiceNotice(null, t, PREF)).toBeNull();
    expect(choiceNotice(undefined, t, PREF)).toBeNull();
  });

  it("says 'You chose this lesson' with no hint when every prerequisite is met", () => {
    const v = choiceNotice(choice(null), t, PREF)!;
    expect(v.title).toBe("You chose this lesson");
    expect(v.body).toMatch(/AI teacher will suggest/);
    expect(v.hint).toBeNull();
  });

  it("lists unmet prerequisites gently, with titles (or a code fallback) and links to them", () => {
    const v = choiceNotice(
      choice({ unmet: [{ objective_code: "M4.F.1", title: { ur: "آدھا", en: "Halves" } }, { objective_code: "M4.F.0", title: null }] }),
      t,
      PREF,
    )!;
    expect(v.hint!.intro).toMatch(/You can still try it/);
    expect(v.hint!.intro).not.toMatch(/can't|cannot|not allowed|locked/i);
    expect(v.hint!.prerequisites).toEqual([
      { code: "M4.F.1", title: { text: "Halves", locale: "en" }, href: "/student/session?lesson=M4.F.1" },
      { code: "M4.F.0", title: { text: "Lesson M4.F.0", locale: "" }, href: "/student/session?lesson=M4.F.0" },
    ]);
  });
});

describe("ChosenLessonNotice markup", () => {
  it.each<Locale>(["en", "ur"])("%s: the choice and the hint, with prerequisite links", (locale) => {
    const t = createTranslator(locale);
    const notice = choiceNotice(choice({ unmet: [{ objective_code: "M4.F.1", title: { ur: "آدھا", en: "Halves" } }] }), t, [locale, ...PREF])!;
    const html = renderToStaticMarkup(createElement(ChosenLessonNotice, { notice }));
    expect(html).toContain("data-chosen-lesson");
    expect(html).toContain(t("student.session.chosen.title"));
    expect(html).toContain("data-prerequisite-hint");
    expect(html).toContain('href="/student/session?lesson=M4.F.1"');
    expect(html).toContain(locale === "ur" ? 'lang="ur" dir="rtl">آدھا' : "Halves");
  });

  it("shows no hint block when nothing is unmet", () => {
    const html = renderToStaticMarkup(createElement(ChosenLessonNotice, { notice: choiceNotice(choice(null), createTranslator("en"), PREF)! }));
    expect(html).toContain("You chose this lesson");
    expect(html).not.toContain("data-prerequisite-hint");
  });
});

describe("links into a chosen lesson", () => {
  it("every lesson row on Learn opens that lesson", () => {
    const path = pathView(
      {
        grade: 4,
        subjects: [
          {
            subject_key: "math",
            title: { en: "Mathematics" },
            units: [
              {
                unit_key: "u1",
                title: { en: "Fractions" },
                state: "in_progress",
                lessons: [
                  { lesson_id: "L1", objective_code: "M4.F.1", title: { en: "Halves" }, state: "practised" },
                  { lesson_id: "L2", objective_code: "M4.F.2", title: { en: "Quarters" }, state: "not_started" },
                ],
                check: { available: false },
              },
            ],
          },
        ],
        next_step: { kind: "lesson", unit_key: "u1", title: { en: "Quarters" } },
      },
      PREF,
    );
    const html = renderToStaticMarkup(createElement(PathBrowser, { path, ctx: ctxFor("en") }));
    expect(html).toContain('href="/student/session?lesson=M4.F.1"');
    expect(html).toContain('href="/student/session?lesson=M4.F.2"');
    expect(html.match(/data-lesson-link/g)?.length).toBe(2);
    // The AI teacher's own suggestion still opens the plain session (it picks).
    expect(html).toContain('href="/student/session"');
  });

  it("unit-check remediation links open the lesson to practise", () => {
    const result = checkResult(
      { score_percent: 40, passed: false, pass_mark: 70, per_objective: [], remediation: [{ objective_code: "M4.F.2", title: { en: "Quarters" }, lesson_id: "L2" }] },
      PREF,
    );
    expect(resultView(result, ctxFor("en")).remediation.map((r) => r.href)).toEqual(["/student/session?lesson=M4.F.2"]);
  });

  it("the session page reads ?lesson= and asks for that lesson as the learner's choice", () => {
    const page = readFileSync(fileURLToPath(new URL("../../../app/student/session/page.tsx", import.meta.url)), "utf8");
    expect(page).toContain("readChosenLesson(useSearchParams())");
    expect(page).toContain("learningApi.teach(s.session_id, chosenLesson, { learnerChosen: true })");
    expect(page).toContain("<ChosenLessonNotice notice={choice} />");
  });
});
