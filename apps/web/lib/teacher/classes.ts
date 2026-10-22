// Classes on the teacher screens. Pure; unit-tested.

import type { MessageKey } from "../i18n/messages";
import type { ClassLearner, Classroom } from "./types";

/** Server limit (school.openapi.yaml: name maxLength 80). */
export const CLASS_NAME_MAX = 80;

export function classNameProblem(name: string): "teacher.classes.nameEmpty" | "teacher.classes.nameLong" | null {
  const trimmed = name.trim();
  if (!trimmed) return "teacher.classes.nameEmpty";
  if (trimmed.length > CLASS_NAME_MAX) return "teacher.classes.nameLong";
  return null;
}

/** Newest class first; name as a stable tie-break. */
export function sortClasses(classes: readonly Classroom[]): Classroom[] {
  return [...classes].sort((a, b) => b.created_at - a.created_at || a.name.localeCompare(b.name));
}

export interface LearnerRow {
  ref: string;
  /** The display name the API returned, or null when it returned none. */
  name: string | null;
  fallbackKey: MessageKey;
  joinedAt: number;
}

/**
 * The learner list exactly as the API returned it — no extra fields, no ids on screen. An empty
 * display name (the server sends "" when it has none) is shown as a neutral placeholder, never as
 * the opaque ref.
 */
export function learnerRows(learners: readonly ClassLearner[]): LearnerRow[] {
  return [...learners]
    .map((l) => ({
      ref: l.student_ref,
      name: l.display_name.trim() ? l.display_name : null,
      fallbackKey: "teacher.detail.unnamed" as const,
      joinedAt: l.joined_at,
    }))
    .sort((a, b) => (a.name ?? "￿").localeCompare(b.name ?? "￿"));
}
