import { describe, expect, it, vi } from "vitest";

import { SyncDiagnosticsStore } from "../diagnostics";
import { MemoryStore } from "../kv";
import { backoffMs, SyncClient } from "../syncClient";
import { SyncQueue } from "../syncQueue";
import type { BatchResult, SyncDelta } from "../types";

// A fake server that mirrors the real one: idempotent by clientEventId, returns per-item statuses.
function fakeServer(opts: { conflictIds?: Set<string>; ignoreIds?: Set<string> } = {}) {
  const seen = new Set<string>();
  let cursor = 0;
  const calls: SyncDelta[][] = [];
  const post = async (_cursor: number, deltas: SyncDelta[]): Promise<BatchResult> => {
    calls.push(deltas);
    const results = deltas.map((d) => {
      if (opts.conflictIds?.has(d.clientEventId)) return { clientEventId: d.clientEventId, status: "conflict" as const, version: cursor };
      if (opts.ignoreIds?.has(d.clientEventId)) return { clientEventId: d.clientEventId, status: "ignored" as const, version: cursor };
      if (seen.has(d.clientEventId)) return { clientEventId: d.clientEventId, status: "duplicate" as const, version: cursor };
      seen.add(d.clientEventId);
      cursor++;
      return { clientEventId: d.clientEventId, status: "applied" as const, version: cursor };
    });
    return { cursor, results };
  };
  return { post, calls, seen };
}

async function seed(q: SyncQueue, ids: string[]): Promise<void> {
  let seq = 1;
  for (const id of ids) {
    await q.enqueue({
      clientEventId: id,
      type: "attempt.submitted",
      entityKey: `student:S1|item:${id}`,
      payload: { evidence_id: `ev-${id}`, student_ref: "S1", item_ref: id, option: 0 },
      clientSeq: seq++,
    });
  }
}

describe("sync client drain", () => {
  it("drains applied deltas and empties the queue", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, ["a", "b", "c"]);
    const server = fakeServer();
    const client = new SyncClient({ queue: q, store, postBatch: server.post });

    const summary = await client.drain();
    expect(summary.applied).toBe(3);
    expect(summary.remaining).toBe(0);
    expect(await q.pendingCount()).toBe(0);
    expect(await client.cursor()).toBe(3);
  });

  it("is idempotent: re-draining the same attempts yields duplicates, no double-send effect", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, ["a", "b"]);
    const server = fakeServer();
    const client = new SyncClient({ queue: q, store, postBatch: server.post });

    await client.drain(); // applied
    // Re-enqueue the SAME ids (simulating a re-queue) and drain again → server says duplicate.
    await seed(q, ["a", "b"]);
    const again = await client.drain();
    expect(again.duplicate).toBe(2);
    expect(await q.pendingCount()).toBe(0); // duplicates are settled + removed
  });

  it("keeps the queue and retries on a network failure (offline)", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, ["a", "b"]);
    let online = false;
    const post = vi.fn(async (_c: number, d: SyncDelta[]): Promise<BatchResult> => {
      if (!online) throw new Error("OFFLINE");
      return { cursor: d.length, results: d.map((x) => ({ clientEventId: x.clientEventId, status: "applied" as const, version: 1 })) };
    });
    const client = new SyncClient({ queue: q, store, postBatch: post });

    const offlineSummary = await client.drain();
    expect(offlineSummary.applied).toBe(0);
    expect(await q.pendingCount()).toBe(2); // kept for retry
    const failed = await q.pending();
    expect(failed.every((d) => d.attempts === 1)).toBe(true);

    online = true; // reconnect
    const onlineSummary = await client.drain();
    expect(onlineSummary.applied).toBe(2);
    expect(await q.pendingCount()).toBe(0);
  });

  it("dead-letters a conflict so it never blocks the queue, but applies the rest", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, ["good", "bad"]);
    const server = fakeServer({ conflictIds: new Set(["bad"]) });
    const client = new SyncClient({ queue: q, store, postBatch: server.post });

    const summary = await client.drain();
    expect(summary.applied).toBe(1);
    expect(summary.conflict).toBe(1);
    expect(await q.pendingCount()).toBe(0); // both settled (one applied, one dead-lettered)
    expect((await q.deadLetters()).map((d) => d.clientEventId)).toEqual(["bad"]);
  });

  it("removes ignored deltas (e.g. summative never auto-graded)", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, ["x"]);
    const server = fakeServer({ ignoreIds: new Set(["x"]) });
    const client = new SyncClient({ queue: q, store, postBatch: server.post });
    const summary = await client.drain();
    expect(summary.ignored).toBe(1);
    expect(await q.pendingCount()).toBe(0);
  });

  it("records diagnostics across drains", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, ["a"]);
    const diagnostics = new SyncDiagnosticsStore(store, () => 5000);
    const client = new SyncClient({ queue: q, store, diagnostics, postBatch: fakeServer().post });
    await client.drain();
    const d = await diagnostics.get();
    expect(d.applied).toBe(1);
    expect(d.lastSyncAt).toBe(5000);
    expect(d.drains).toBeGreaterThanOrEqual(1);
  });
});

describe("backoff", () => {
  it("is bounded, non-negative, and grows with attempts (full jitter)", () => {
    expect(backoffMs(0, 1000, 60000, () => 1)).toBe(1000);
    expect(backoffMs(3, 1000, 60000, () => 1)).toBe(8000);
    expect(backoffMs(100, 1000, 60000, () => 1)).toBe(60000); // capped
    expect(backoffMs(5, 1000, 60000, () => 0)).toBe(0); // full jitter can be 0
  });
});
