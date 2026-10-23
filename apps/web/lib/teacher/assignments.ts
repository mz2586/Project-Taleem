// Assigning a published lesson. Pure; unit-tested.
//
// Two honest limits shape this module:
// - The lesson list is GET /v1/school/lessons (the teacher's curriculum pack, titles only). If it
//   cannot be read, `lessonChoices` says so rather than claiming nothing is published: a list,
//   "none are published yet", or "the list is not available".
// - The server is the judge of "published": an objective code typed by hand is checked there
//   (422 LESSON_NOT_PUBLISHED), never assumed here.

import type { MessageKey } from "../i18n/messages";
import { ApiError } from "../student/types";
import type { Assignment, PublishedLesson } from "./types";

/** Server limit (AssignmentIn.objectiveCode maxLength 64). */
export const OBJECTIVE_CODE_MAX = 64;

export interface LessonChoice {
  objectiveCode: string;
  /** The title in the requested locale, else English, else any; "" if the lesson has none. */
  title: string;
}

function pickTitle(title: Record<string, string> | undefined, locale: string): string {
  if (!title) return "";
  return title[locale] || title.en || Object.values(title).find((v) => v) || "";
}

export type LessonChoices =
  | { kind: "list"; lessons: LessonChoice[] }
  | { kind: "none-published" }
  | { kind: "unavailable" };

export type Outcome<T> = { ok: true; value: T } | { ok: false; error: unknown };

export function lessonChoices(
  outcome: Outcome<{ lessons?: PublishedLesson[] }>,
  locale = "en",
): LessonChoices {
  if (!outcome.ok) {
    // 403, 404, offline, anything: the list cannot be shown. Not "none exist".
    return { kind: "unavailable" };
  }
  const seen = new Set<string>();
  const lessons: LessonChoice[] = [];
  for (const p of outcome.value.lessons ?? []) {
    if (!p.objective_code || seen.has(p.objective_code)) continue;
    seen.add(p.objective_code);
    lessons.push({ objectiveCode: p.objective_code, title: pickTitle(p.title, locale) });
  }
  if (lessons.length === 0) return { kind: "none-published" };
  lessons.sort((a, b) => a.objectiveCode.localeCompare(b.objectiveCode));
  return { kind: "list", lessons };
}

export function isForbiddenOrMissing(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 403 || error.status === 404);
}

export function objectiveCodeProblem(code: string): MessageKey | null {
  const trimmed = code.trim();
  if (!trimmed) return "teacher.assign.codeEmpty";
  if (trimmed.length > OBJECTIVE_CODE_MAX) return "teacher.assign.codeLong";
  return null;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** `YYYY-MM-DD` for a date input, in the device's local calendar. */
export function localDateInput(epochSeconds: number): string {
  const d = new Date(epochSeconds * 1000);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export type DueAt = { ok: true; dueAt: number } | { ok: false; problem: MessageKey };

/**
 * A date-input value → the Unix-seconds `dueAt` the API wants: the END of that local day (23:59:59),
 * so "due Friday" means a learner can still practise on Friday evening. The server rejects a due
 * date that is not in the future; this checks the same thing first so the message is immediate.
 */
export function dueAtFromDateInput(value: string, nowSeconds: number): DueAt {
  if (!value.trim()) return { ok: false, problem: "teacher.assign.dueEmpty" };
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
  if (!match) return { ok: false, problem: "teacher.assign.dueInvalid" };
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const end = new Date(year, month - 1, day, 23, 59, 59);
  if (end.getFullYear() !== year || end.getMonth() !== month - 1 || end.getDate() !== day) {
    return { ok: false, problem: "teacher.assign.dueInvalid" };
  }
  const dueAt = Math.floor(end.getTime() / 1000);
  if (dueAt <= nowSeconds) return { ok: false, problem: "teacher.assign.duePast" };
  return { ok: true, dueAt };
}

/** Soonest due first, so the assignment that needs attention is at the top. */
export function sortAssignments(assignments: readonly Assignment[]): Assignment[] {
  return [...assignments].sort((a, b) => a.due_at - b.due_at || a.objective_code.localeCompare(b.objective_code));
}

export function isPastDue(assignment: Pick<Assignment, "due_at">, nowSeconds: number): boolean {
  return nowSeconds > assignment.due_at;
}
