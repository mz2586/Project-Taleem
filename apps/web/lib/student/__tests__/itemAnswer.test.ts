// The interaction rules for every answerable item kind (ITEM_INTERACTION_CONTRACT.md) and the answer
// body each one produces. Pure: the renderers in components/student/ItemInteraction.tsx are views
// over exactly these functions.
import { describe, expect, it } from "vitest";

import {
  emptyPairDraft,
  fillAnswer,
  FILL_MAX_LENGTH,
  isRenderable,
  itemKind,
  leftFor,
  leftsIn,
  nextUnpaired,
  orderAnswer,
  orderTap,
  orderUndo,
  pairsAnswer,
  splitPoint,
  tapLeft,
  tapRight,
  type PairDraft,
  type PairMode,
} from "../itemAnswer";

describe("item kind", () => {
  it("a missing kind is choose (servers and packages from before the contract)", () => {
    expect(itemKind({})).toBe("choose");
    expect(itemKind({ kind: null })).toBe("choose");
    expect(itemKind({ kind: undefined })).toBe("choose");
  });

  it("reads every contract kind, and falls back to choose for an unknown one", () => {
    for (const k of ["choose", "fill", "order", "match", "sort"]) expect(itemKind({ kind: k })).toBe(k);
    expect(itemKind({ kind: "clock_hands" })).toBe("choose");
  });

  it("match/sort need a split with at least one option on each side", () => {
    const opts = ["a", "b", "c", "d"];
    expect(splitPoint({ options: opts, kind: "match", left_count: 2 })).toBe(2);
    expect(splitPoint({ options: opts, kind: "match", left_count: 0 })).toBeNull();
    expect(splitPoint({ options: opts, kind: "match", left_count: 4 })).toBeNull();
    expect(splitPoint({ options: opts, kind: "match", left_count: 1.5 })).toBeNull();
    expect(splitPoint({ options: opts, kind: "match" })).toBeNull();
    expect(isRenderable({ options: opts, kind: "sort" })).toBe(false);
    expect(isRenderable({ options: opts, kind: "sort", left_count: 3 })).toBe(true);
    expect(isRenderable({ options: [], kind: "fill" })).toBe(true);
    expect(isRenderable({ options: [], kind: "order" })).toBe(false);
  });
});

describe("fill", () => {
  it("is incomplete while empty or blank", () => {
    expect(fillAnswer("")).toBeNull();
    expect(fillAnswer("   ")).toBeNull();
  });

  it("produces {text} for Urdu, English and digits alike, trimmed and capped at the contract limit", () => {
    expect(fillAnswer(" ۴۰ ")).toEqual({ text: "۴۰" });
    expect(fillAnswer("forty")).toEqual({ text: "forty" });
    expect(fillAnswer("پانی")).toEqual({ text: "پانی" });
    expect(fillAnswer("40")).toEqual({ text: "40" });
    const long = fillAnswer("x".repeat(FILL_MAX_LENGTH + 50));
    expect(long && "text" in long ? long.text.length : 0).toBe(FILL_MAX_LENGTH);
  });
});

describe("order (tap to build a sequence)", () => {
  it("taps append in order; the answer is the sequence of option indices", () => {
    let seq: number[] = [];
    for (const i of [1, 2, 0]) seq = orderTap(seq, i);
    expect(seq).toEqual([1, 2, 0]);
    expect(orderAnswer(seq, 3)).toEqual({ order: [1, 2, 0] });
  });

  it("is incomplete until every item is placed", () => {
    expect(orderAnswer([], 3)).toBeNull();
    expect(orderAnswer([2, 0], 3)).toBeNull();
    expect(orderAnswer([], 0)).toBeNull();
  });

  it("tapping a placed item takes it back out; undo removes the last; clear is the empty sequence", () => {
    expect(orderTap([1, 2, 0], 2)).toEqual([1, 0]);
    expect(orderUndo([1, 2, 0])).toEqual([1, 2]);
    expect(orderUndo([])).toEqual([]);
  });

  it("never yields an answer with duplicates or out-of-range indices", () => {
    expect(orderAnswer([0, 0, 1], 3)).toBeNull();
    expect(orderAnswer([0, 1, 3], 3)).toBeNull();
  });
});

function tapAll(mode: PairMode, taps: Array<["L" | "R", number]>): PairDraft {
  let d = emptyPairDraft;
  for (const [side, i] of taps) d = (side === "L" ? tapLeft(d, i, mode) : tapRight(d, i, mode)).draft;
  return d;
}

describe("match (tap an item, then its match)", () => {
  // options: 0,1 = items; 2,3 = matches (left_count 2)
  it("pairs an item with the match tapped next, and produces {pairs} in item order", () => {
    const step = tapLeft(emptyPairDraft, 1, "match");
    expect(step.event).toEqual({ type: "selected", left: 1 });
    expect(step.draft.selected).toBe(1);
    const paired = tapRight(step.draft, 2, "match");
    expect(paired.event).toEqual({ type: "paired", left: 1, right: 2 });
    const d = tapAll("match", [["L", 1], ["R", 2], ["L", 0], ["R", 3]]);
    expect(pairsAnswer(d, 2)).toEqual({ pairs: [[0, 3], [1, 2]] });
  });

  it("is incomplete until every item has a match", () => {
    expect(pairsAnswer(emptyPairDraft, 2)).toBeNull();
    expect(pairsAnswer(tapAll("match", [["L", 0], ["R", 2]]), 2)).toBeNull();
  });

  it("tapping a matched item (or its match) again unpairs it", () => {
    const d = tapAll("match", [["L", 0], ["R", 2]]);
    const viaLeft = tapLeft(d, 0, "match");
    expect(viaLeft.event).toEqual({ type: "unpaired", left: 0 });
    expect(viaLeft.draft.pairs).toEqual({});
    const viaRight = tapRight(d, 2, "match");
    expect(viaRight.event).toEqual({ type: "unpaired", left: 0 });
    expect(viaRight.draft.pairs).toEqual({});
  });

  it("each match is used once: giving a taken match to another item moves it", () => {
    const d = tapAll("match", [["L", 0], ["R", 2], ["L", 1], ["R", 2]]);
    expect(d.pairs).toEqual({ 1: 2 });
    expect(leftFor(d, 2)).toBe(1);
  });

  it("tapping the selected item again deselects it; a match with nothing selected asks for an item", () => {
    const sel = tapLeft(emptyPairDraft, 0, "match").draft;
    expect(tapLeft(sel, 0, "match")).toEqual({ draft: { selected: null, pairs: {} }, event: { type: "deselected", left: 0 } });
    expect(tapRight(emptyPairDraft, 3, "match").event).toEqual({ type: "needLeft" });
  });

  it("finds the next free item for focus, wrapping", () => {
    const d = tapAll("match", [["L", 1], ["R", 2]]);
    expect(nextUnpaired(d, 3, 1)).toBe(2);
    expect(nextUnpaired(d, 3, 2)).toBe(0);
    expect(nextUnpaired(tapAll("match", [["L", 0], ["R", 3], ["L", 1], ["R", 4], ["L", 2], ["R", 5]]), 3)).toBeNull();
  });
});

describe("sort (tap a card, then a group)", () => {
  // options: 0,1,2 = cards; 3,4 = groups (left_count 3)
  it("a group holds many cards; produces {pairs} of [card, group] for every card", () => {
    const d = tapAll("sort", [["L", 0], ["R", 3], ["L", 1], ["R", 3], ["L", 2], ["R", 4]]);
    expect(leftsIn(d, 3)).toEqual([0, 1]);
    expect(pairsAnswer(d, 3)).toEqual({ pairs: [[0, 3], [1, 3], [2, 4]] });
  });

  it("is incomplete until every card is in a group", () => {
    expect(pairsAnswer(tapAll("sort", [["L", 0], ["R", 3]]), 3)).toBeNull();
  });

  it("tapping a sorted card selects it again so it can move to another group", () => {
    let d = tapAll("sort", [["L", 0], ["R", 3]]);
    const step = tapLeft(d, 0, "sort");
    expect(step.event).toEqual({ type: "selected", left: 0 });
    d = tapRight(step.draft, 4, "sort").draft;
    expect(d.pairs).toEqual({ 0: 4 });
  });

  it("tapping a group with no card chosen asks for a card and changes nothing", () => {
    const d = tapAll("sort", [["L", 0], ["R", 3]]);
    expect(tapRight(d, 4, "sort")).toEqual({ draft: d, event: { type: "needLeft" } });
  });
});
