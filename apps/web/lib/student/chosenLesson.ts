// A lesson the child chose (a lesson row on Learn, a "practise this" link after a unit check),
// instead of the AI teacher's pick. Pure; tested.
//
// Contract: packages/contracts/learning.openapi.yaml (`TeachIn.learner_chosen`, `LearnerChoice`).
// The session page opens `/student/session?lesson=<objective_code>` with `:teach` +
// `learner_chosen`; the server allows any published lesson the child may see, records "You chose
// this lesson" in the session's rationale, and returns unmet prerequisites as a hint — never a
// block. The words here stay gentle: a hint is "these may help first", never "you can't".

import { pickLocalized, type LocalizedText } from "../i18n/content";
import type { MessageKey } from "../i18n/messages";
import type { Translator } from "../i18n/translate";

export const SESSION_HREF = "/student/session";
export const LESSON_PARAM = "lesson";
/** Objective codes are short (e.g. "MATH-G4-F.2"); anything longer is not one. */
const MAX_CODE = 64;

/** The session link that opens one lesson; the plain session (AI picks) when there is no code. */
export function lessonHref(objectiveCode: string | null | undefined): string {
  const code = (objectiveCode ?? "").trim();
  if (!code) return SESSION_HREF;
  return `${SESSION_HREF}?${LESSON_PARAM}=${encodeURIComponent(code)}`;
}

/** The chosen lesson from the page's search params; null for none (the AI teacher picks). */
export function readChosenLesson(params: { get(name: string): string | null } | null | undefined): string | null {
  const raw = params?.get(LESSON_PARAM);
  const code = (raw ?? "").trim();
  if (!code || code.length > MAX_CODE || /[\s<>"]/.test(code)) return null;
  return code;
}

export interface PrerequisiteWire {
  objective_code: string;
  title: Record<string, string> | null;
}

export interface LearnerChoiceWire {
  objective_code: string;
  chosen_by: "learner";
  rationale: string[];
  reasons?: Array<{ code: string; params?: Record<string, string | number> }>;
  recommended?: { decision: string; objective_code: string | null } | null;
  prerequisite_hint: { unmet: PrerequisiteWire[] } | null;
}

export interface PrerequisiteLine {
  code: string;
  title: LocalizedText;
  href: string;
}

export interface ChoiceNoticeView {
  title: string;
  body: string;
  /** null: no unmet prerequisites (nothing to hint). */
  hint: { intro: string; prerequisites: PrerequisiteLine[] } | null;
}

export const CHOICE_COPY = {
  title: "student.session.chosen.title",
  body: "student.session.chosen.body",
  hintIntro: "student.session.chosen.hintIntro",
  unavailable: "student.session.chosen.unavailable",
} as const satisfies Record<string, MessageKey>;

/** What the session shows above a learner-chosen lesson; null when the AI teacher chose it. */
export function choiceNotice(
  choice: LearnerChoiceWire | null | undefined,
  t: Translator,
  preference: readonly string[],
): ChoiceNoticeView | null {
  if (!choice || choice.chosen_by !== "learner") return null;
  const unmet = (choice.prerequisite_hint?.unmet ?? []).filter((p) => p && typeof p.objective_code === "string" && p.objective_code);
  const prerequisites = unmet.map((p) => {
    const picked = p.title ? pickLocalized(p.title, preference) : null;
    return {
      code: p.objective_code,
      title: picked ?? { text: t("progression.path.untitledLesson", { code: p.objective_code }), locale: "" },
      href: lessonHref(p.objective_code),
    };
  });
  return {
    title: t(CHOICE_COPY.title),
    body: t(CHOICE_COPY.body),
    hint: prerequisites.length > 0 ? { intro: t(CHOICE_COPY.hintIntro), prerequisites } : null,
  };
}
