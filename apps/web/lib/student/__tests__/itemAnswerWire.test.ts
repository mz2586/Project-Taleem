// The answer field on the wire, per item kind (ITEM_INTERACTION_CONTRACT §3): the online `:answer`
// body and the offline `attempt.submitted` payload (plus its reconcile re-queue). Choose stays
// byte-identical to the pre-contract client.
import { afterEach, describe, expect, it, vi } from "vitest";

import { CheckpointStore } from "../../offline/checkpoint";
import { MemoryStore } from "../../offline/kv";
import { ProgressStore } from "../../offline/progress";
import { reconcileAndResume } from "../../offline/reconcile";
import { SyncQueue } from "../../offline/syncQueue";
import type { AnswerBody, OfflineContent, OfflineItem } from "../../offline/types";
import { learningApi } from "../api";
import { itemKind } from "../itemAnswer";
import { createOfflineRunner, toTeachView } from "../offlinePlayer";

const ANSWERS: Record<string, AnswerBody> = {
  choose: { option: 2 },
  fill: { text: "۴۰" },
  order: { order: [1, 2, 0] },
  match: { pairs: [[0, 3], [1, 2]] },
  sort: { pairs: [[0, 3], [1, 3], [2, 4]] },
};

describe("online :answer body", () => {
  afterEach(() => vi.unstubAllGlobals());

  async function sentBody(answer: AnswerBody): Promise<string> {
    const fetchMock = vi.fn(async (..._args: unknown[]) =>
      new Response(JSON.stringify({ outcome: "correct", mastery: 0.5, state: "s", post_decision: "continue", confirmed_misconceptions: [], cleared_misconceptions: [], feedback: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    await learningApi.answer("sess-1", { objective_code: "OBJ", item_ref: "it-1", ...answer, hints_used: 1 });
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/v1/learning/sessions/sess-1:answer");
    return String(init.body);
  }

  it("choose is byte-identical to the pre-contract body", async () => {
    expect(await sentBody({ option: 2 })).toBe('{"objective_code":"OBJ","item_ref":"it-1","option":2,"hints_used":1}');
  });

  it.each(["fill", "order", "match", "sort"])("%s sends exactly its own answer field", async (kind) => {
    const body = JSON.parse(await sentBody(ANSWERS[kind]!)) as Record<string, unknown>;
    expect(body).toEqual({ objective_code: "OBJ", item_ref: "it-1", ...ANSWERS[kind], hints_used: 1 });
    const fields = ["option", "text", "order", "pairs"].filter((f) => f in body);
    expect(fields).toHaveLength(1);
  });
});

function item(ref: string, kind?: string, extra: Partial<OfflineItem> = {}): OfflineItem {
  return {
    item_ref: ref,
    objective_code: "SYN-OBJ",
    prompt: { ur: "سوال" },
    options: ["a", "b", "c", "d", "e"],
    hints: [],
    ...(kind ? { kind } : {}),
    ...extra,
  };
}

function content(items: OfflineItem[]): OfflineContent {
  return {
    lesson_id: "L-syn",
    objective_code: "SYN-OBJ",
    title: { ur: "سبق" },
    explanation: {},
    worked_example_steps: [],
    practice_items: items,
    homework_items: [],
    assessment_formative: [],
    summative_mentor_mediated: true,
  };
}

async function world(items: OfflineItem[]) {
  const store = new MemoryStore();
  const progress = new ProgressStore(store, () => 1);
  const checkpoints = new CheckpointStore(store, () => 1);
  const queue = new SyncQueue(store, () => 1);
  const c = content(items);
  const runner = createOfflineRunner({ getLesson: async () => c, progress, checkpoints, queue }, "stu_syn_01");
  const opened = (await runner.open("L-syn"))!;
  return { progress, checkpoints, queue, runner, opened };
}

describe("offline attempt.submitted payload", () => {
  it("passes kind and left_count through to the player, and leaves older items untouched", () => {
    const teach = toTeachView(content([item("c1"), item("m1", "match", { left_count: 2 })]));
    expect(teach.items[0]).toEqual({ item_ref: "c1", prompt: { ur: "سوال" }, options: ["a", "b", "c", "d", "e"], hint_count: 0 });
    expect(itemKind(teach.items[0]!)).toBe("choose");
    expect(teach.items[1]).toMatchObject({ kind: "match", left_count: 2 });
  });

  it("choose (old `option` shorthand and `{option}` answer) is identical to the pre-contract payload", async () => {
    for (const input of [{ option: 2 }, { answer: { option: 2 } as AnswerBody }]) {
      const w = await world([item("c1")]);
      await w.runner.answer({ checkpoint: w.opened.checkpoint, item: w.opened.content.practice_items[0]!, ...input, hintsUsed: 0, responseTimeMs: 5 });
      const [delta] = await w.queue.all();
      expect(Object.keys(delta!.payload)).toEqual([
        "student_ref",
        "objective_code",
        "item_ref",
        "option",
        "evidence_id",
        "session_id",
        "hints_used",
        "response_time_ms",
        "context",
      ]);
      expect(delta!.payload["option"]).toBe(2);
      const [, attempted] = await w.progress.forStudent("stu_syn_01");
      expect(attempted).toMatchObject({ kind: "item_attempted", selected_option: 2 });
      expect(attempted).not.toHaveProperty("answer");
    }
  });

  it.each(["fill", "order", "match", "sort"])("%s queues exactly its own answer field", async (kind) => {
    const it0 = item("x1", kind, kind === "match" || kind === "sort" ? { left_count: 3 } : {});
    const w = await world([it0]);
    await w.runner.answer({ checkpoint: w.opened.checkpoint, item: it0, answer: ANSWERS[kind]!, hintsUsed: 1 });
    const [delta] = await w.queue.all();
    expect(delta!.type).toBe("attempt.submitted");
    expect(delta!.payload).toMatchObject({ item_ref: "x1", ...ANSWERS[kind], hints_used: 1, context: "practice" });
    expect(["option", "text", "order", "pairs"].filter((f) => f in delta!.payload)).toHaveLength(1);
  });

  it("reconcile re-queues a lost non-choose attempt with the same answer field", async () => {
    const it0 = item("o1", "order");
    const w = await world([it0]);
    // Crash between the progress event and the enqueue: only the event exists.
    await w.progress.record({ student_ref: "stu_syn_01", lesson_id: "L-syn", objective_code: "SYN-OBJ", kind: "item_attempted", item_ref: "o1", answer: { order: [2, 0, 1] } });
    const r = await reconcileAndResume("stu_syn_01", {
      progress: w.progress,
      checkpoints: w.checkpoints,
      queue: w.queue,
      drain: async () => ({ sent: 0, applied: 0, duplicate: 0, ignored: 0, conflict: 0, remaining: 0, cursor: 0 }),
    });
    expect(r.enqueued).toBe(1);
    const [delta] = await w.queue.all();
    expect(delta!.payload).toMatchObject({ item_ref: "o1", order: [2, 0, 1] });
    expect(delta!.payload).not.toHaveProperty("option");
  });
});
