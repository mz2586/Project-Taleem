// Learner management rules for the family screen. Pure; unit-tested.
import type { MessageKey } from "../i18n/messages";
import type { GradeBand } from "../session/types";

/** Grades a guardian can enrol into (KG = 0). Mirrors the API's 0..12 range. */
export const GRADE_LEVELS: readonly number[] = Array.from({ length: 13 }, (_, i) => i);

/** The API's grade band, derived from the grade so the guardian answers one question, not two. */
export function gradeBandFor(gradeLevel: number): GradeBand {
  if (gradeLevel <= 2) return "early";
  if (gradeLevel <= 5) return "middle";
  return "senior";
}

export function gradeOption(gradeLevel: number): { key: MessageKey; params?: { grade: number } } {
  return gradeLevel <= 0 ? { key: "guardian.enrol.gradeKg" } : { key: "guardian.enrol.gradeOption", params: { grade: gradeLevel } };
}

/** Client-side PIN check, so the guardian hears about a typo before a round trip. */
export type PinProblem = "empty" | "format" | null;

export function pinProblem(pin: string): PinProblem {
  if (pin.length === 0) return "empty";
  return /^[0-9]{4,6}$/.test(pin) ? null : "format";
}

/** Keep digits only, at most six — what a PIN field accepts as the guardian types. */
export function sanitizePin(value: string): string {
  return value.replace(/\D/g, "").slice(0, 6);
}

/** The API's display-name limit. */
export const NAME_MAX = 60;

export function nameProblem(name: string): "empty" | "long" | null {
  const trimmed = name.trim();
  if (trimmed.length === 0) return "empty";
  return trimmed.length > NAME_MAX ? "long" : null;
}
