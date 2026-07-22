// Chaos / fault-injection framework tests (Phase 6.2C-1) — proves the framework injects faults and
// that the sync engine survives them with no data loss (CX-3 flapping network, CX-1/2 mid-op crash).
import { describe, expect, it } from "vitest";

import { FaultyStore, faultyPostBatch } from "../chaos";
import { MemoryStore } from "../kv";
import { QuotaExceededError } from "../packages";
import { SyncClient } from "../syncClient";
import { SyncQueue } from "../syncQueue";
import type { BatchResult, SyncDelta } from "../types";

function idempotentServer() {
  const seen = new Set<string>();
  return async (_c: number, deltas: SyncDelta[]): Promise<BatchResult> => ({
    cursor: seen.size,
    results: deltas.map((d) => {
      const dup = seen.has(d.clientEventId);
      if (!dup) seen.add(d.clientEventId);
      return { clientEventId: d.clientEventId, status: dup ? ("duplicate" as const) : ("applied" as const), version: 1 };
    }),
  });
}

async function seed(q: SyncQueue, n: number): Promise<void> {
  for (let i = 0; i < n; i++) {
    await q.enqueue({
      clientEventId: `d${i}`,
      type: "attempt.submitted",
      entityKey: `S1|i${i}`,
      payload: { evidence_id: `ev${i}`, student_ref: "S1", item_ref: `i${i}`, option: 0 },
      clientSeq: i + 1,
    });
  }
}

describe("FaultyStore", () => {
  it("injects a throw fault on the configured op, then recovers after maxFailures", async () => {
    const store = new FaultyStore(new MemoryStore(), { failOn: ["put"], maxFailures: 1 });
    await expect(store.put("prefs", "k", { v: 1 })).rejects.toThrow(/injected fault/);
    // second put succeeds (maxFailures reached)
    await store.put("prefs", "k", { v: 2 });
    expect(await store.get("prefs", "k")).toEqual({ v: 2 });
  });

  it("can simulate quota-exceeded", async () => {
    const store = new FaultyStore(new MemoryStore(), { failOn: ["put"], mode: "quota" });
    await expect(store.put("packages", "k", {})).rejects.toBeInstanceOf(QuotaExceededError);
  });

  it("passes through untouched when disabled", async () => {
    const store = new FaultyStore(new MemoryStore(), { failOn: ["put"], enabled: false });
    await store.put("prefs", "k", { v: 9 });
    expect(await store.get("prefs", "k")).toEqual({ v: 9 });
  });
});

describe("network chaos", () => {
  it("a flapping network (offline-for-first-N) drains with no loss once it recovers", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, 10);
    const post = faultyPostBatch(idempotentServer(), { offlineForFirst: 2 });
    const client = new SyncClient({ queue: q, store, postBatch: post, batchSize: 5 });

    // First two drains fail (offline) — the queue is kept, attempts increment.
    await client.drain();
    await client.drain();
    expect(await q.pendingCount()).toBe(10);

    // Third drain succeeds → everything applied exactly once, queue empties.
    const summary = await client.drain();
    expect(summary.applied).toBe(10);
    expect(await q.pendingCount()).toBe(0);
  });

  it("a live-toggle offline network keeps the queue intact (no data loss)", async () => {
    const store = new MemoryStore();
    const q = new SyncQueue(store, () => 1);
    await seed(q, 4);
    const cfg = { offline: true };
    const post = faultyPostBatch(idempotentServer(), cfg);
    const client = new SyncClient({ queue: q, store, postBatch: post });

    await client.drain();
    expect(await q.pendingCount()).toBe(4); // nothing lost while offline

    cfg.offline = false; // network returns
    const summary = await client.drain();
    expect(summary.applied).toBe(4);
    expect(await q.pendingCount()).toBe(0);
  });
});
