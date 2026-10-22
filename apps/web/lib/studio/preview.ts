// Lesson detail view-models for reviewers. Pure; unit-tested.
//
// - `learnerPreview` turns a studio lesson into the `TeachView` the student lesson player
//   consumes, so reviewers see the lesson the way a child will: the same paced steps, items and
//   hint ladder, driven by the same lesson-player reducer (lib/student/lessonPlayer.ts, used
//   read-only). The mapping follows what the learning runtime presents: title, then the student
//   explanation, then each worked-example prompt and its steps.
// - `localizedRows` lays every localized field side by side across the lesson's locales, with a
//   missing translation flagged rather than silently blank.
// - `lessonLocales` decides which locales those are: the lesson's declared instructional locales,
//   else its pack's, plus any locale the content actually carries.

import type { CurriculumPackSummary, LessonView, LocalizedTextView } from "../studio-api";
import type { TeachView } from "../student/types";

/** Whether the API returned the lesson's content (it does not yet — see studio-api.ts). */
export function hasContent(lesson: LessonView): boolean {
  return (
    lesson.student_explanation !== undefined ||
    lesson.worked_examples !== undefined ||
    lesson.practice_questions !== undefined
  );
}

function textOf(field: LocalizedTextView | undefined, locale: string): string {
  return field?.text?.[locale]?.trim() ?? "";
}

export function lessonLocales(lesson: LessonView, pack?: CurriculumPackSummary | null): string[] {
  const declared = lesson.instructional_locales?.length ? lesson.instructional_locales : (pack?.instructional_locales ?? []);
  const carried = new Set<string>(Object.keys(lesson.title));
  const out = [...declared];
  for (const l of carried) if (!out.includes(l)) out.push(l);
  return out;
}

/**
 * The learner's view of the lesson in `locale`, as a `TeachView`. Empty strings are kept out of the
 * steps by the player itself (`presentationSteps` drops blank utterances), so a missing translation
 * shows as a missing step here exactly as it would for a child.
 */
export function learnerPreview(lesson: LessonView, locale: string): TeachView {
  const utterances: TeachView["utterances"] = [];
  const present = (text: string) => utterances.push({ kind: "present", text });
  present(lesson.title[locale] ?? "");
  present(textOf(lesson.student_explanation, locale));
  for (const ex of lesson.worked_examples ?? []) {
    present(textOf(ex.prompt, locale));
    for (const step of ex.steps ?? []) present(textOf(step, locale));
  }
  const items = (lesson.practice_questions ?? []).map((q) => ({
    item_ref: q.item_id,
    prompt: { [locale]: textOf(q.stem, locale) },
    options: (q.options ?? []).map((o) => textOf(o, locale)),
    hint_count: (q.hints ?? []).length,
  }));
  return { utterances, items };
}

/** The authored hint ladder of one item in `locale`, in order (the player reveals it rung by rung). */
export function itemHints(lesson: LessonView, itemRef: string, locale: string): string[] {
  const item = (lesson.practice_questions ?? []).find((q) => q.item_id === itemRef);
  return (item?.hints ?? []).map((h) => textOf(h.hint, locale));
}

export interface LocalizedRow {
  /** Stable id for the field ("title", "worked_examples[0].steps[1]", ...). */
  field: string;
  values: { locale: string; text: string; missing: boolean }[];
  /** True when any locale is missing this field. */
  incomplete: boolean;
}

function row(field: string, texts: Record<string, string> | undefined, locales: readonly string[]): LocalizedRow {
  const values = locales.map((locale) => {
    const text = texts?.[locale]?.trim() ?? "";
    return { locale, text, missing: text === "" };
  });
  return { field, values, incomplete: values.some((v) => v.missing) };
}

export function localizedRows(lesson: LessonView, locales: readonly string[]): LocalizedRow[] {
  const rows: LocalizedRow[] = [row("title", lesson.title, locales)];
  if (lesson.student_explanation) rows.push(row("student_explanation", lesson.student_explanation.text, locales));
  (lesson.worked_examples ?? []).forEach((ex, i) => {
    rows.push(row(`worked_examples[${i}].prompt`, ex.prompt.text, locales));
    (ex.steps ?? []).forEach((s, j) => rows.push(row(`worked_examples[${i}].steps[${j}]`, s.text, locales)));
  });
  (lesson.practice_questions ?? []).forEach((q) => {
    rows.push(row(`${q.item_id}.stem`, q.stem.text, locales));
    (q.options ?? []).forEach((o, j) => rows.push(row(`${q.item_id}.options[${j}]`, o.text, locales)));
    (q.hints ?? []).forEach((h, j) => rows.push(row(`${q.item_id}.hints[${j}]`, h.hint.text, locales)));
  });
  (lesson.hints ?? []).forEach((h, j) => rows.push(row(`hints[${j}]`, h.hint.text, locales)));
  return rows;
}

// ---- versions ----------------------------------------------------------------------------------

export interface VersionRow {
  version: number;
  contentHash: string;
  changeSummary: string;
  authorRole: string;
  /** Whether the content changed from the previous version (hash differs). */
  contentChanged: boolean;
  isCurrent: boolean;
}

/** Version history, newest first. The API returns hashes, not snapshots, so this is a hash diff. */
export function versionRows(
  versions: readonly { version: number; content_hash: string; change_summary: string; author_role: string }[],
  current: number,
): VersionRow[] {
  const ordered = [...versions].sort((a, b) => a.version - b.version);
  return ordered
    .map((v, i) => ({
      version: v.version,
      contentHash: v.content_hash,
      changeSummary: v.change_summary,
      authorRole: v.author_role,
      contentChanged: i === 0 || ordered[i - 1]!.content_hash !== v.content_hash,
      isCurrent: v.version === current,
    }))
    .reverse();
}
