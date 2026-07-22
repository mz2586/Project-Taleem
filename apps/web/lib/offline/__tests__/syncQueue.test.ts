import { describe, expect, it } from "vitest";

import { MemoryStore } from "../kv";
import { SyncQueue } from "../syncQueue";
import type { AttemptPayload, SyncDelta } from "../types";

function delta(id: string, seq: number): Omit<SyncDelta, "clientSeq"> & { clientSeq?: number } {
  return {
    clientEventId: id,
    type: "attempt.submitted",
    entityKey: "student:S1|item:i1",
    payload: { evidence_id: `ev-${id}`, student_ref: "S1", item_ref: "i1", option: 0 },
    clientSeq: seq,
  };
}

const attempt: AttemptPayload = {
  student_ref: "S1",
  objective_code: "O1",
  item_ref: "i1",
  option: 0,
  evidence_id: "ev-1",
};

describe("sync queue", () => {
  it("assigns a monotonic client_seq that never regresses", async () => {
    const q = new SyncQueue(new MemoryStore(), () => 1);
    expect(await q.nextSeq()).toBe(1);
    expect(await q.nextSeq()).toBe(2);
    expect(await q.nextSeq()).toBe(3);
  });

  it("enqueues and returns pending deltas ordered by (clientSeq, clientEventId)", async () => {
    const q = new SyncQueue(new MemoryStore(), () => 1);
    await q.enqueue(delta("b", 2));
    await q.enqueue(delta("a", 1));
    await q.enqueue(delta("c", 1));
    const pending = await q.pending();
    expect(pending.map((d) => d.clientEventId)).toEqual(["a", "c", "b"]);
  });

  it("builds an attempt delta carrying the evidence_id idempotency key", async () => {
    const q = new SyncQueue(new MemoryStore(), () => 1);
    const rec = await q.enqueueAttempt(attempt);
    expect(rec.type).toBe("attempt.submitted");
    expect(rec.payload["evidence_id"]).toBe("ev-1");
    expect(rec.syncState).toBe("pending");
  });

  it("removes a settled delta and counts pending", async () => {
    const q = new SyncQueue(new MemoryStore(), () => 1);
    await q.enqueue(delta("a", 1));
    await q.enqueue(delta("b", 2));
    expect(await q.pendingCount()).toBe(2);
    await q.remove("a");
    expect(await q.pendingCount()).toBe(1);
  });

  it("retries a failed delta, then dead-letters it past the cap", async () => {
    const q = new SyncQueue(new MemoryStore(), () => 1, 3); // maxAttempts = 3
    await q.enqueue(delta("a", 1));
    await q.markFailed("a", "network");
    await q.markFailed("a", "network");
    expect((await q.pending()).length).toBe(1); // still retryable (failed)
    await q.markFailed("a", "network"); // 3rd → dead
    expect(await q.pendingCount()).toBe(0);
    expect((await q.deadLetters()).map((d) => d.clientEventId)).toEqual(["a"]);
  });

  it("dead-letters a conflict immediately so it never blocks the queue", async () => {
    const q = new SyncQueue(new MemoryStore(), () => 1);
    await q.enqueue(delta("a", 1));
    await q.deadLetter("a", "conflict");
    expect(await q.pendingCount()).toBe(0);
    expect((await q.deadLetters())[0]?.lastError).toBe("conflict");
  });
});
