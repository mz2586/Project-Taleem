// Diagnostic placement on the student screens — "Find your starting point". Pure; tested.
//
// Contract: packages/contracts/learning.openapi.yaml (`PlacementView`). The server runs the whole
// placement (which question next, when to stop, the priors it seeds); this module only decides what
// the child sees:
//
// - Today offers the entry only when a placement is possible for this learner right now
//   (`available` / `in_progress`). With nothing published (`unavailable`) or a learner who has
//   already practised (`not_eligible`), there is no entry at all.
// - The question screen shows the prompt in the interface language when the item has it, and never
//   says right or wrong: it is not a test, and one answer is never a verdict.
// - A retried answer (`duplicate`) and a "not the current question" conflict both just reload.

import { SUPPORTED_LOCALES, type Locale } from "../i18n/config";
import type { MessageKey } from "../i18n/messages";
import { ApiError } from "./types";

export type PlacementStatus = "unavailable" | "not_eligible" | "available" | "in_progress" | "completed";

export interface PlacementItemWire {
  item_ref: string;
  objective_code: string;
  prompt: Record<string, string>;
  options: string[];
}

export interface PlacementObjectiveWire {
  objective_code: string;
  status: "secure" | "not_yet" | "uncertain";
  prior: number;
  uncertainty: number;
  correct: number;
  incorrect: number;
  inferred_from: string | null;
  item_refs: string[];
  source: string;
  recorded_at: number;
}

export interface PlacementWire {
  student_ref: string;
  status: PlacementStatus;
  reason: string | null;
  placement_id: string | null;
  items_used: number;
  max_items: number;
  stop_reason: string | null;
  placement_uncertainty: number;
  start_objective: string | null;
  next_item: PlacementItemWire | null;
  objectives: PlacementObjectiveWire[];
  duplicate?: boolean;
}

// ---- the entry on Today ---------------------------------------------------------------------------

export interface PlacementEntry {
  title: MessageKey;
  body: MessageKey;
  action: MessageKey;
  href: string;
}

export const PLACEMENT_HREF = "/student/placement";

/** The Today card, or null when no placement is possible (never a button into nothing). */
export function placementEntry(wire: PlacementWire | null): PlacementEntry | null {
  if (!wire) return null;
  if (wire.status !== "available" && wire.status !== "in_progress") return null;
  if (!wire.next_item) return null;
  return {
    title: "student.today.placementTitle",
    body: "student.today.placementBody",
    action: wire.status === "in_progress" ? "student.today.placementContinue" : "student.today.placementStart",
    href: PLACEMENT_HREF,
  };
}

// ---- the question screen --------------------------------------------------------------------------

export interface PlacementQuestion {
  itemRef: string;
  prompt: string;
  /** The prompt's own language (it may differ from the interface when only one is authored). */
  promptLocale: Locale | null;
  options: Array<{ index: number; label: string }>;
  /** 1-based number of this question. */
  number: number;
  max: number;
}

export type PlacementScreen =
  | { kind: "question"; question: PlacementQuestion }
  | { kind: "done" }
  | { kind: "unavailable" }
  | { kind: "not-eligible" };

function promptFor(prompt: Record<string, string>, locale: Locale): { text: string; locale: Locale | null } {
  const own = prompt[locale];
  if (own && own.trim()) return { text: own, locale };
  for (const [lang, text] of Object.entries(prompt)) {
    if (text && text.trim()) {
      const known = (SUPPORTED_LOCALES as readonly string[]).includes(lang) ? (lang as Locale) : null;
      return { text, locale: known };
    }
  }
  return { text: "", locale: null };
}

export function placementScreen(wire: PlacementWire, locale: Locale): PlacementScreen {
  if (wire.status === "completed") return { kind: "done" };
  if (wire.status === "not_eligible") return { kind: "not-eligible" };
  const item = wire.next_item;
  if (wire.status === "unavailable" || !item) return { kind: "unavailable" };
  const { text, locale: promptLocale } = promptFor(item.prompt ?? {}, locale);
  return {
    kind: "question",
    question: {
      itemRef: item.item_ref,
      prompt: text,
      promptLocale,
      options: (item.options ?? []).map((label, index) => ({ index, label })),
      number: Math.min(wire.items_used + 1, Math.max(1, wire.max_items)),
      max: wire.max_items,
    },
  };
}

// ---- answering ------------------------------------------------------------------------------------

export type PlacementFailure = "offline" | "error";

export type AnswerState =
  | { status: "idle" }
  | { status: "saving"; option: number }
  | { status: "failed"; error: PlacementFailure };

export type AnswerAction =
  | { type: "submit"; option: number }
  | { type: "saved" }
  | { type: "failed"; error: PlacementFailure }
  | { type: "reset" };

export const initialAnswerState: AnswerState = { status: "idle" };

export function answerReducer(state: AnswerState, action: AnswerAction): AnswerState {
  switch (action.type) {
    case "submit":
      // One answer at a time: a double tap never sends two.
      return state.status === "saving" ? state : { status: "saving", option: action.option };
    case "saved":
    case "reset":
      return initialAnswerState;
    case "failed":
      return state.status === "saving" ? { status: "failed", error: action.error } : state;
  }
}

/**
 * What to do with an answer that failed. A 409 means the server has moved on (a retry already
 * counted, or the question changed): reload instead of showing an error.
 */
export function classifyAnswerError(error: unknown): PlacementFailure | "reload" {
  if (error instanceof ApiError) {
    if (error.status === 0) return "offline";
    if (error.status === 409) return "reload";
  }
  return "error";
}

export const PLACEMENT_FAILURE_COPY: Record<PlacementFailure, MessageKey> = {
  offline: "student.placement.offline",
  error: "student.placement.error",
};

export const PLACEMENT_SCREEN_COPY: Record<"unavailable" | "not-eligible" | "done", { title: MessageKey; body: MessageKey }> = {
  unavailable: { title: "student.placement.unavailableTitle", body: "student.placement.unavailableBody" },
  "not-eligible": { title: "student.placement.notEligibleTitle", body: "student.placement.notEligibleBody" },
  done: { title: "student.placement.doneTitle", body: "student.placement.doneBody" },
};
