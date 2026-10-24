// Normalising the homework wire into plain values. Pure. Every tolerance for an open field spelling
// in the contract lives here (see ./types.ts), so the view models never touch raw wire objects.

import { pickLocalized, type LocalizedText } from "../i18n/content";
import type { HomeworkItemWire, LocalizedWire, SubmissionRowWire, SubmissionState } from "./types";

const STATES: readonly SubmissionState[] = ["not_started", "submitted", "returned", "marked"];

/** One rendition of authored text. A plain string carries no declared locale (direction is read from it). */
export function localized(value: LocalizedWire | null | undefined, preference: readonly string[]): LocalizedText | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.trim() ? { text: value, locale: "" } : null;
  return pickLocalized(value, preference);
}

/** The item's latest submission state; anything unknown reads as "not started" (never as marked). */
export function itemState(item: HomeworkItemWire): SubmissionState {
  const raw = item.submission?.state ?? item.state ?? "not_started";
  return STATES.includes(raw) ? raw : "not_started";
}

export function learnerName(row: SubmissionRowWire): string {
  return (row.learner_display_name ?? row.display_name ?? "").trim();
}
