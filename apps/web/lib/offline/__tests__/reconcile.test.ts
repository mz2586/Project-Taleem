import { describe, expect, it } from "vitest";

import { CheckpointStore } from "../checkpoint";
import { MemoryStore } from "../kv";
import { ProgressStore } from "../progress";
import { reconcileAndResume } from "../reconcile";
import { SyncQueue } from "../syncQueue";
import type { DrainSummary } from "../types";

function noopDrain(): Promise<DrainSummary> {
  return Promise.resolve({
    sent: 0,
    applied: 0,
    duplicate: 0,
    ignored: 0,
    conflict: 0,
    remaining: 0,
    cursor: 0,
  });
}

describe("session reconciliation + resume", () => {
  it("enqueues locally-recorded attempts that are not yet in the queue", async () => {
    const store = new MemoryStore();
    const progress = new ProgressStore(store, () => 1);
    const checkpoints = new CheckpointStore(store, () => 1);
    const queue = new SyncQueue(store, () => 1);

    // Two answered items recorded offline (progress), but nothing enqueued (crash before enqueue).
    await progress.record(
      { student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "item_attempted", item_ref: "i1", selected_option: 0 },
      "ev-1",
    );
    await progress.record(
      { student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "item_attempted", item_ref: "i2", selected_option: 1 },
      "ev-2",
    );

    const { enqueued } = await reconcileAndResume("S1", { progress, checkpoints, queue, drain: noopDrain });
    expect(enqueued).toBe(2);
    const pending = await queue.pending();
    expect(pending.map((d) => d.payload["evidence_id"]).sort()).toEqual(["ev-1", "ev-2"]);
  });

  it("is idempotent: a second reconcile does not re-enqueue the same attempts", async () => {
    const store = new MemoryStore();
    const progress = new ProgressStore(store, () => 1);
    const checkpoints = new CheckpointStore(store, () => 1);
    const queue = new SyncQueue(store, () => 1);
    await progress.record(
      { student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "item_attempted", item_ref: "i1", selected_option: 0 },
      "ev-1",
    );

    const first = await reconcileAndResume("S1", { progress, checkpoints, queue, drain: noopDrain });
    const second = await reconcileAndResume("S1", { progress, checkpoints, queue, drain: noopDrain });
    expect(first.enqueued).toBe(1);
    expect(second.enqueued).toBe(0); // already queued — stable evidence_id de-dupes
    expect(await queue.pendingCount()).toBe(1);
  });

  it("ignores non-attempt progress events (opened / completed)", async () => {
    const store = new MemoryStore();
    const progress = new ProgressStore(store, () => 1);
    const checkpoints = new CheckpointStore(store, () => 1);
    const queue = new SyncQueue(store, () => 1);
    await progress.record({ student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "lesson_opened" }, "o-1");
    await progress.record({ student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "lesson_completed" }, "c-1");
    const { enqueued } = await reconcileAndResume("S1", { progress, checkpoints, queue, drain: noopDrain });
    expect(enqueued).toBe(0);
  });
});
