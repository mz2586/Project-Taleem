// Item interactions — the pure core of every answerable item kind (ITEM_INTERACTION_CONTRACT.md).
//
// The server projects each item with a `kind` and the display fields the learner needs; this module
// turns the child's taps or typing into exactly one contract answer field:
//   choose {option} · fill {text} · order {order: [...]} · match/sort {pairs: [[left, right], ...]}
// An item with no `kind` is a choose item (servers and packages from before the contract).
//
// Everything here is pure, so the interaction rules are tested without a browser; the renderers in
// components/student/ItemInteraction.tsx are thin views over these functions. Nothing here grades:
// the answer key never reaches the device, and a draft is only "complete" or "not yet".

import type { AnswerBody } from "../offline/types";

export type { AnswerBody };

export type ItemKind = "choose" | "fill" | "order" | "match" | "sort";

const KNOWN_KINDS: readonly ItemKind[] = ["choose", "fill", "order", "match", "sort"];

/** The contract's limit on a typed answer. */
export const FILL_MAX_LENGTH = 200;

/** The fields of an item (online or offline) that decide how it is answered. */
export interface InteractiveItem {
  options: string[];
  kind?: string | null;
  left_count?: number | null;
}

/** The item's kind; a missing (or unknown) kind is "choose", which keeps older content working. */
export function itemKind(item: { kind?: string | null }): ItemKind {
  const kind = item.kind ?? "choose";
  return (KNOWN_KINDS as readonly string[]).includes(kind) ? (kind as ItemKind) : "choose";
}

/**
 * For match/sort: how many options are the items (or cards) — the rest are the matches (or groups).
 * Null when the item does not describe a usable split (both sides need at least one option).
 */
export function splitPoint(item: InteractiveItem): number | null {
  const k = item.left_count;
  if (typeof k !== "number" || !Number.isInteger(k)) return null;
  return k > 0 && k < item.options.length ? k : null;
}

/** Whether this device can render the item at all. */
export function isRenderable(item: InteractiveItem): boolean {
  switch (itemKind(item)) {
    case "fill":
      return true;
    case "choose":
    case "order":
      return item.options.length > 0;
    case "match":
    case "sort":
      return splitPoint(item) !== null;
  }
}

// ---- fill ---------------------------------------------------------------------------------------------

/** The `{text}` answer for what the child typed, or null while it is still empty. */
export function fillAnswer(text: string): AnswerBody | null {
  const trimmed = text.trim().slice(0, FILL_MAX_LENGTH);
  return trimmed === "" ? null : { text: trimmed };
}

// ---- order --------------------------------------------------------------------------------------------

/**
 * Tap an item: an unplaced item goes to the end of the sequence; a placed item is taken back out
 * (the items after it close up), so a slip never needs a full restart.
 */
export function orderTap(sequence: readonly number[], index: number): number[] {
  return sequence.includes(index) ? sequence.filter((i) => i !== index) : [...sequence, index];
}

export function orderUndo(sequence: readonly number[]): number[] {
  return sequence.slice(0, -1);
}

/** The `{order}` answer once every item is placed exactly once, else null. */
export function orderAnswer(sequence: readonly number[], optionCount: number): AnswerBody | null {
  if (optionCount === 0 || sequence.length !== optionCount) return null;
  if (new Set(sequence).size !== optionCount || sequence.some((i) => i < 0 || i >= optionCount)) return null;
  return { order: [...sequence] };
}

// ---- match + sort (pairs) -----------------------------------------------------------------------------

export type PairMode = "match" | "sort";

export interface PairDraft {
  /** The item/card the child tapped and has not placed yet. */
  selected: number | null;
  /** item/card index -> match/group index (both are option indices). */
  pairs: Record<number, number>;
}

export const emptyPairDraft: PairDraft = { selected: null, pairs: {} };

/** What a tap did, so the view can announce it and move focus. */
export type PairEvent =
  | { type: "selected"; left: number }
  | { type: "deselected"; left: number }
  | { type: "paired"; left: number; right: number }
  | { type: "unpaired"; left: number }
  | { type: "needLeft" };

export interface PairStep {
  draft: PairDraft;
  event: PairEvent;
}

function without(pairs: Record<number, number>, left: number): Record<number, number> {
  const next = { ...pairs };
  delete next[left];
  return next;
}

/**
 * Tap an item (match) or a card (sort).
 * - match: tapping a matched item unmatches it; otherwise it becomes (or stops being) the selection.
 * - sort: a card may already be in a group; selecting it again lets the child move it.
 */
export function tapLeft(draft: PairDraft, left: number, mode: PairMode): PairStep {
  if (mode === "match" && draft.pairs[left] !== undefined) {
    return { draft: { selected: null, pairs: without(draft.pairs, left) }, event: { type: "unpaired", left } };
  }
  if (draft.selected === left) return { draft: { ...draft, selected: null }, event: { type: "deselected", left } };
  return { draft: { ...draft, selected: left }, event: { type: "selected", left } };
}

/**
 * Tap a match (match) or a group (sort).
 * - With an item selected, it is paired with this one. In match each match is used once, so a match
 *   already taken moves to the new item; in sort a group holds any number of cards.
 * - With nothing selected: in match, tapping a used match unpairs it; otherwise the child is told to
 *   tap an item first.
 */
export function tapRight(draft: PairDraft, right: number, mode: PairMode): PairStep {
  if (draft.selected !== null) {
    const left = draft.selected;
    let pairs = { ...draft.pairs };
    if (mode === "match") {
      for (const [l, r] of Object.entries(pairs)) if (r === right) delete pairs[Number(l)];
    }
    pairs = { ...pairs, [left]: right };
    return { draft: { selected: null, pairs }, event: { type: "paired", left, right } };
  }
  if (mode === "match") {
    const owner = leftFor(draft, right);
    if (owner !== null) return { draft: { selected: null, pairs: without(draft.pairs, owner) }, event: { type: "unpaired", left: owner } };
  }
  return { draft, event: { type: "needLeft" } };
}

/** The item paired with `right` (match), or null. */
export function leftFor(draft: PairDraft, right: number): number | null {
  for (const [l, r] of Object.entries(draft.pairs)) if (r === right) return Number(l);
  return null;
}

/** The cards in group `right` (sort), in card order. */
export function leftsIn(draft: PairDraft, right: number): number[] {
  return Object.entries(draft.pairs)
    .filter(([, r]) => r === right)
    .map(([l]) => Number(l))
    .sort((a, b) => a - b);
}

export function pairedCount(draft: PairDraft, leftCount: number): number {
  let n = 0;
  for (let l = 0; l < leftCount; l++) if (draft.pairs[l] !== undefined) n++;
  return n;
}

/** The first item/card (from `after`, wrapping) that is not yet placed, or null when all are. */
export function nextUnpaired(draft: PairDraft, leftCount: number, after = -1): number | null {
  for (let step = 1; step <= leftCount; step++) {
    const l = (after + step + leftCount) % leftCount;
    if (draft.pairs[l] === undefined) return l;
  }
  return null;
}

/** The `{pairs}` answer once every item/card is placed, else null. Pairs are in item order. */
export function pairsAnswer(draft: PairDraft, leftCount: number): AnswerBody | null {
  if (leftCount <= 0 || pairedCount(draft, leftCount) !== leftCount) return null;
  const pairs: Array<[number, number]> = [];
  for (let l = 0; l < leftCount; l++) pairs.push([l, draft.pairs[l]!]);
  return { pairs };
}
