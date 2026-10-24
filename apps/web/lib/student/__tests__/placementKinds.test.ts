// Placement serves fill/order/match/sort items too (ITEM_INTERACTION_CONTRACT §3): the screen model
// carries what ItemInteraction needs, and the answer endpoint gets exactly one answer field. Choose
// is unchanged, byte for byte.
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AnswerBody } from "../../offline/types";
import { learningApi } from "../api";
import { itemKind } from "../itemAnswer";
import { answerReducer, initialAnswerState, placementScreen, type PlacementWire } from "../placement";

const base: PlacementWire = {
  student_ref: "s1",
  status: "in_progress",
  reason: null,
  placement_id: "pl1",
  items_used: 1,
  max_items: 12,
  stop_reason: null,
  placement_uncertainty: 1,
  start_objective: null,
  next_item: { item_ref: "p2", objective_code: "OBJ", prompt: { ur: "ترتیب دیں" }, options: ["b", "c", "a"] },
  objectives: [],
};

describe("placement screen per kind", () => {
  it("an item without kind is a plain choose question (no interaction model)", () => {
    const s = placementScreen(base, "ur");
    expect(s.kind === "question" && s.question.interaction).toBeUndefined();
  });

  it("an item with a kind carries kind, options and left_count for the renderer", () => {
    const order = placementScreen({ ...base, next_item: { ...base.next_item!, kind: "order" } }, "ur");
    expect(order.kind === "question" && order.question.interaction).toEqual({ item_ref: "p2", options: ["b", "c", "a"], kind: "order" });
    const match = placementScreen(
      { ...base, next_item: { ...base.next_item!, kind: "match", options: ["a", "b", "1", "2"], left_count: 2 } },
      "ur",
    );
    const m = match.kind === "question" ? match.question.interaction : undefined;
    expect(m).toMatchObject({ kind: "match", left_count: 2 });
    expect(itemKind(m!)).toBe("match");
  });

  it("saving a non-choose answer has no option spinner", () => {
    expect(answerReducer(initialAnswerState, { type: "submit", option: null })).toEqual({ status: "saving", option: null });
  });
});

describe("placement answer body", () => {
  afterEach(() => vi.unstubAllGlobals());

  async function sent(body: AnswerBody): Promise<string> {
    const fetchMock = vi.fn(async (..._args: unknown[]) => new Response(JSON.stringify(base), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await learningApi.placementAnswer("s1", { item_ref: "p2", ...body });
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/v1/learning/students/s1/placement:answer");
    return String((fetchMock.mock.calls[0]![1] as RequestInit).body);
  }

  it("choose is byte-identical to the pre-contract body", async () => {
    expect(await sent({ option: 1 })).toBe('{"item_ref":"p2","option":1}');
  });

  it.each<[string, AnswerBody]>([
    ["fill", { text: "۴۰" }],
    ["order", { order: [2, 0, 1] }],
    ["match", { pairs: [[0, 3], [1, 2]] }],
    ["sort", { pairs: [[0, 3], [1, 3]] }],
  ])("%s sends exactly its own answer field", async (_kind, body) => {
    const parsed = JSON.parse(await sent(body)) as Record<string, unknown>;
    expect(parsed).toEqual({ item_ref: "p2", ...body });
    expect(["option", "text", "order", "pairs"].filter((f) => f in parsed)).toHaveLength(1);
  });
});
