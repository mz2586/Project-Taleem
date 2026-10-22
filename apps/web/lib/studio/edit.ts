// Draft editing: the author's working copy of a draft's localized fields, and the minimal PATCH it
// becomes. Pure; unit-tested.
//
// PATCH semantics (curriculum-studio.openapi.yaml LessonPatchIn): omitted fields are unchanged;
// localized fields are `{locale: text}` maps merged per locale, and an empty string removes that
// locale. So the patch carries exactly the (field, locale) pairs the author changed — re-sending
// unchanged text would be harmless, but a minimal patch keeps the review history readable and
// makes "nothing changed" detectable. The request is guarded by If-Match with the lesson's ETag.

import type { MessageKey } from "../i18n/messages";
import { PATCHABLE_LOCALIZED, type LessonPatchIn, type LessonView, type PatchableLocalized } from "../studio-api";

export type EditableFields = Record<PatchableLocalized, Record<string, string>>;

/** The draft's current localized fields, one `{locale: text}` map per patchable field. */
export function editableFields(lesson: LessonView): EditableFields {
  const out = {} as EditableFields;
  for (const field of PATCHABLE_LOCALIZED) {
    if (field === "title") out.title = { ...lesson.title };
    else out[field] = { ...(lesson[field]?.text ?? {}) };
  }
  return out;
}

/** The PATCH body for what changed between `original` and `edited`, or null when nothing did. */
export function buildPatch(original: EditableFields, edited: EditableFields): LessonPatchIn | null {
  const patch: LessonPatchIn = {};
  for (const field of PATCHABLE_LOCALIZED) {
    const before = original[field] ?? {};
    const after = edited[field] ?? {};
    const changes: Record<string, string> = {};
    for (const locale of new Set([...Object.keys(before), ...Object.keys(after)])) {
      const was = (before[locale] ?? "").trim();
      const now = (after[locale] ?? "").trim();
      if (was !== now) changes[locale] = now; // "" removes the locale
    }
    if (Object.keys(changes).length > 0) patch[field] = changes;
  }
  return Object.keys(patch).length > 0 ? patch : null;
}

/** A draft must keep a title in at least one locale. */
export function editErrors(edited: EditableFields): MessageKey | null {
  return Object.values(edited.title).some((t) => t.trim() !== "") ? null : "studio.edit.titleRequired";
}
