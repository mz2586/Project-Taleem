// Crash recovery + long offline session (Phase 6.2B) — exercises the durable queue over real
// IndexedDB (fake-indexeddb) so the "queue survives a crash/reopen" and "drains a long session"
// guarantees are validated with browser storage semantics.
import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it } from "vitest";

import { IdbStore, STORES } from "../kv";
import { SyncClient } from "../syncClient";
import { SyncQueue } from "../syncQueue";
import type { BatchResult, SyncDelta } from "../types";

async function reset(): Promise<void> {
  const store = new IdbStore(indexedDB);
  for (const s of Object.values(STORES)) await store.clear(s);
}

function idempotentServer() {
  const seen = new Set<string>();
  let cursor = 0;
  const post = async (_c: number, deltas: SyncDelta[]): Promise<BatchResult> => ({
    cursor: (cursor += deltas.filter((d) => !seen.has(d.clientEventId)).length),
    results: deltas.map((d) => {
      if (seen.has(d.clientEventId)) return { clientEventId: d.clientEventId, status: "duplicate" as const, version: cursor };
      seen.add(d.clientEventId);
      return { clientEventId: d.clientEventId, status: "applied" as const, version: cursor };
    }),
  });
  return { post, seen };
}

async function enqueueAttempts(q: SyncQueue, n: number): Promise<void> {
  for (let i = 0; i < n; i++) {
    await q.enqueue({
      clientEventId: `att-${i}`,
      type: "attempt.submitted",
      entityKey: `student:S1|item:i${i}`,
      payload: { evidence_id: `ev-${i}`, student_ref: "S1", item_ref: `i${i}`, option: 0 },
      clientSeq: i + 1,
    });
  }
}

describe("crash recovery + long offline session (IndexedDB)", () => {
  beforeEach(async () => {
    await reset();
  });

  it("persists the queue across a reopen (crash) and drains it after", async () => {
    // Session 1: enqueue 3 attempts offline, then the tab is 'killed' (no drain).
    await enqueueAttempts(new SyncQueue(new IdbStore(indexedDB), () => 1), 3);

    // Session 2: a fresh store over the same DB still sees all 3 queued deltas.
    const q2 = new SyncQueue(new IdbStore(indexedDB), () => 1);
    expect(await q2.pendingCount()).toBe(3);

    const server = idempotentServer();
    const client = new SyncClient({ queue: q2, store: new IdbStore(indexedDB), postBatch: server.post });
    const summary = await client.drain();
    expect(summary.applied).toBe(3);
    expect(await q2.pendingCount()).toBe(0);
  });

  it("drains a long offline session (120 attempts) with no loss or double-count", async () => {
    const store = new IdbStore(indexedDB);
    const q = new SyncQueue(store, () => 1);
    await enqueueAttempts(q, 120);
    expect(await q.pendingCount()).toBe(120);

    const server = idempotentServer();
    const client = new SyncClient({ queue: q, store, postBatch: server.post, batchSize: 25 });
    const summary = await client.drain();

    expect(summary.applied).toBe(120);
    expect(await q.pendingCount()).toBe(0);
    expect(server.seen.size).toBe(120); // exactly once each — no double count
  });

  it("a partial drain then reopen resumes the remainder (no loss, no double-apply)", async () => {
    // First run: server applies the first batch, then 'goes offline' for the rest.
    const store = new IdbStore(indexedDB);
    const q = new SyncQueue(store, () => 1);
    await enqueueAttempts(q, 40);

    let allow = 20;
    const seen = new Set<string>();
    const flaky = async (_c: number, deltas: SyncDelta[]): Promise<BatchResult> => {
      if (allow <= 0) throw new Error("OFFLINE");
      allow -= deltas.length;
      return {
        cursor: seen.size + deltas.length,
        results: deltas.map((d) => {
          const dup = seen.has(d.clientEventId);
          if (!dup) seen.add(d.clientEventId);
          return { clientEventId: d.clientEventId, status: dup ? ("duplicate" as const) : ("applied" as const), version: 1 };
        }),
      };
    };
    const client1 = new SyncClient({ queue: q, store, postBatch: flaky, batchSize: 20 });
    await client1.drain(); // applies 20, then throws → remaining 20 kept
    expect(await q.pendingCount()).toBe(20);

    // Reopen and finish with a healthy server; the already-applied 20 are never re-applied.
    const q2 = new SyncQueue(new IdbStore(indexedDB), () => 1);
    const client2 = new SyncClient({
      queue: q2,
      store: new IdbStore(indexedDB),
      postBatch: async (_c, deltas) => ({
        cursor: seen.size,
        results: deltas.map((d) => {
          const dup = seen.has(d.clientEventId);
          if (!dup) seen.add(d.clientEventId);
          return { clientEventId: d.clientEventId, status: dup ? ("duplicate" as const) : ("applied" as const), version: 1 };
        }),
      }),
    });
    const summary = await client2.drain();
    expect(summary.applied).toBe(20); // only the remainder
    expect(await q2.pendingCount()).toBe(0);
    expect(seen.size).toBe(40); // 40 distinct, exactly once
  });
});
