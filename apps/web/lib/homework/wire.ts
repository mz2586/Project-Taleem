// Normalising the homework wire into plain values. Pure. Every tolerance for an open field spelling
// in the contract lives here (see ./types.ts), so the view models never touch raw wire objects.

import { pickLocalized, type LocalizedText } from "../i18n/content";
import type {
  CompareWire,
  HomeworkAssignmentWire,
  HomeworkItemWire,
  HomeworkMarking,
  HomeworkSource,
  LearnerSubmissionWire,
  LocalizedWire,
  SubmissionRowWire,
  SubmissionState,
} from "./types";

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

const MARKINGS: readonly HomeworkMarking[] = ["auto", "self_check", "teacher"];

/**
 * §6: where an item came from. The item's own tag wins, then the entry's; an untagged entry with a
 * real due date is a teacher's assignment, anything else is the learner's own lesson practice.
 */
export function itemSource(item: HomeworkItemWire, entry: Pick<HomeworkAssignmentWire, "source" | "due_at">): HomeworkSource {
  const raw = item.source ?? entry.source;
  if (raw === "self_paced" || raw === "assignment") return raw;
  return typeof entry.due_at === "number" && entry.due_at > 0 ? "assignment" : "self_paced";
}

/** §6: how the item is marked (the item's tag, else the submission's); unknown ⇒ null (never "auto"). */
export function itemMarking(item: HomeworkItemWire): HomeworkMarking | null {
  const raw = item.marking ?? item.submission?.marking ?? null;
  return raw && MARKINGS.includes(raw) ? raw : null;
}

export interface CompareText {
  sample: LocalizedText | null;
  guidance: LocalizedText | null;
}

/** §6: the self-check comparison, or null when there is nothing to show. */
export function compareText(value: CompareWire | null | undefined, preference: readonly string[]): CompareText | null {
  if (!value || typeof value !== "object") return null;
  const sample = localized(value.sample_answer, preference);
  const guidance = localized(value.guidance, preference);
  return sample || guidance ? { sample, guidance } : null;
}

/**
 * The submit response (`POST …:submit`, and a sync `homework.submitted` result) as ONE submission.
 * The server nests the submission (`{state, marking, compare, can_retry, submission: {...}}`); the
 * view models read a flat `LearnerSubmissionWire`. Item-level fields fill only what the nested
 * submission leaves out. An already-flat or non-object value is returned as it is (or null).
 */
export function flattenSubmitView(value: unknown): LearnerSubmissionWire | null {
  if (!value || typeof value !== "object") return null;
  const view = value as Record<string, unknown>;
  const nested = view["submission"];
  if (!nested || typeof nested !== "object") return view as unknown as LearnerSubmissionWire;
  const sub = nested as Record<string, unknown>;
  const pick = (key: string) => (sub[key] !== undefined && sub[key] !== null ? sub[key] : view[key]);
  return {
    ...(sub as unknown as LearnerSubmissionWire),
    state: (pick("state") as SubmissionState | undefined) ?? "submitted",
    marking: (pick("marking") as HomeworkMarking | null | undefined) ?? null,
    compare: (pick("compare") as CompareWire | null | undefined) ?? null,
    can_retry: (pick("can_retry") as boolean | null | undefined) ?? null,
  };
}
