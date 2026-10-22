// The new-draft form: what an author fills in, checked before it is sent. Pure; unit-tested.
//
// The create contract (LessonDraftIn) takes `title_ur` and `title_en` and nothing locale-generic
// yet, so the form asks for exactly those. The server still runs every gate; this only spares an
// author a round trip for the obvious mistakes.

import type { MessageKey } from "../i18n/messages";
import type { LessonDraftIn } from "../studio-api";

export interface DraftForm {
  lessonId: string;
  titleUr: string;
  titleEn: string;
  pack: string;
  grade: string;
  subject: string;
  /** Free text: SLO codes separated by commas, spaces or new lines. */
  outcomes: string;
}

export const EMPTY_DRAFT: DraftForm = {
  lessonId: "",
  titleUr: "",
  titleEn: "",
  pack: "",
  grade: "",
  subject: "",
  outcomes: "",
};

export type DraftErrors = Partial<Record<keyof DraftForm, MessageKey>>;

export function parseOutcomes(text: string): string[] {
  return [...new Set(text.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean))];
}

const LESSON_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export function draftErrors(
  form: DraftForm,
  hierarchy: { grades: string[]; subjects_by_grade: Record<string, string[]> } | null,
): DraftErrors {
  const e: DraftErrors = {};
  if (!LESSON_ID.test(form.lessonId.trim())) e.lessonId = "studio.draft.errors.lessonId";
  if (!form.titleUr.trim()) e.titleUr = "studio.draft.errors.required";
  if (!form.titleEn.trim()) e.titleEn = "studio.draft.errors.required";
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
  return {
    lesson_id: form.lessonId.trim(),
    title_ur: form.titleUr.trim(),
    title_en: form.titleEn.trim(),
    grade: form.grade,
    subject: form.subject,
    ...(form.pack ? { curriculum_pack: form.pack } : {}),
    learning_outcomes: outcomes,
    provenance: { aligned_slo_codes: outcomes },
  };
}
