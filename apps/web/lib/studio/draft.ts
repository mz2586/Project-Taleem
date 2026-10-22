// The new-draft form: what an author fills in, checked before it is sent. Pure; unit-tested.
//
// Titles are locale-keyed (`title: {locale: text}`); the form offers exactly the locales of the
// chosen curriculum pack, and at least one title is required. The server still runs every gate;
// this only spares an author a round trip for the obvious mistakes.

import type { MessageKey } from "../i18n/messages";
import type { CurriculumPackSummary, LessonDraftIn } from "../studio-api";

export interface DraftForm {
  lessonId: string;
  /** Title per pack locale. */
  titles: Record<string, string>;
  pack: string;
  grade: string;
  subject: string;
  /** Free text: SLO codes separated by commas, spaces or new lines. */
  outcomes: string;
}

export const EMPTY_DRAFT: DraftForm = {
  lessonId: "",
  titles: {},
  pack: "",
  grade: "",
  subject: "",
  outcomes: "",
};

export type DraftErrors = Partial<Record<"lessonId" | "titles" | "grade" | "subject" | "outcomes", MessageKey>>;

export function parseOutcomes(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean))];
}

/** The locales a pack's lessons may carry: its declared locales, else its instructional locales. */
export function packLocales(pack: CurriculumPackSummary | null | undefined): { tag: string; name: string; direction: "ltr" | "rtl" }[] {
  if (!pack) return [];
  if (pack.locales?.length) return pack.locales;
  return pack.instructional_locales.map((tag) => ({ tag, name: tag, direction: "ltr" as const }));
}

const LESSON_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function draftErrors(
  form: DraftForm,
  hierarchy: { grades: string[]; subjects_by_grade: Record<string, string[]> } | null,
  allowedLocales?: readonly string[],
): DraftErrors {
  const e: DraftErrors = {};
  if (!LESSON_ID.test(form.lessonId.trim())) e.lessonId = "studio.draft.errors.lessonId";
  const titled = Object.entries(form.titles).filter(([, v]) => v.trim() !== "");
  if (titled.length === 0) e.titles = "studio.draft.errors.title";
  else if (allowedLocales && titled.some(([loc]) => !allowedLocales.includes(loc))) e.titles = "studio.draft.errors.locale";
  if (!form.grade) e.grade = "studio.draft.errors.required";
  else if (hierarchy && !hierarchy.grades.includes(form.grade)) e.grade = "studio.draft.errors.notInPack";
  if (!form.subject) e.subject = "studio.draft.errors.required";
  else if (hierarchy && form.grade && !(hierarchy.subjects_by_grade[form.grade] ?? []).includes(form.subject)) {
    e.subject = "studio.draft.errors.notInPack";
  }
  if (parseOutcomes(form.outcomes).length === 0) e.outcomes = "studio.draft.errors.outcomes";
  return e;
}

export function toDraftIn(form: DraftForm): LessonDraftIn {
  const outcomes = parseOutcomes(form.outcomes);
  const title = Object.fromEntries(
    Object.entries(form.titles)
      .map(([loc, text]) => [loc, text.trim()] as const)
      .filter(([, text]) => text !== ""),
  );
  return {
    lesson_id: form.lessonId.trim(),
    title,
    grade: form.grade,
    subject: form.subject,
    ...(form.pack ? { curriculum_pack: form.pack } : {}),
    learning_outcomes: outcomes,
    provenance: { aligned_slo_codes: outcomes },
  };
}
