// Concurrent diagnostics updates must not lose increments (read-modify-write is serialized).
import "fake-indexeddb/auto";

import { describe, expect, it } from "vitest";

import { SyncDiagnosticsStore } from "../diagnostics";
import type { KVStore } from "../kv";
import { IdbStore, MemoryStore, STORES } from "../kv";

const N = 50;

// A store whose reads and writes yield to the event loop, so unserialized updates interleave.
function slowStore(): KVStore {
  const inner = new MemoryStore();
  const tick = () => new Promise((r) => setTimeout(r, Math.random() * 3));
  return {
    get: async (s, k) => (await tick(), inner.get(s, k)),
    put: async (s, k, v) => (await tick(), inner.put(s, k, v)),
    getAll: (s) => inner.getAll(s),
    delete: (s, k) => inner.delete(s, k),
    clear: (s) => inner.clear(s),
  };
}

describe("diagnostics updates are atomic", () => {
  it(`keeps all ${N} concurrent increments on a slow store`, async () => {
    const diag = new SyncDiagnosticsStore(slowStore());
    await Promise.all(Array.from({ length: N }, () => diag.recordSignatureFailure()));
    expect((await diag.get()).signatureFailures).toBe(N);
  });

  it("serializes across instances that share a store, and across counter kinds", async () => {
    const store = slowStore();
    const a = new SyncDiagnosticsStore(store);
    const b = new SyncDiagnosticsStore(store);
    await Promise.all([
      ...Array.from({ length: N }, (_, i) => (i % 2 ? a : b).recordQueued()),
      ...Array.from({ length: N }, () => a.recordEviction(10)),
      a.recordKeyPinning(false),
    ]);
    const d = await b.get();
    expect(d.queued).toBe(N);
    expect(d.evictions).toBe(N);
    expect(d.evictedBytes).toBe(N * 10);
    expect(d.signingKeysPinned).toBe(false);
  });

  it(`keeps all ${N} concurrent increments in IndexedDB`, async () => {
    const store = new IdbStore(indexedDB);
    await store.clear(STORES.syncMeta);
    const diag = new SyncDiagnosticsStore(store);
    await Promise.all(Array.from({ length: N }, () => diag.recordIntegrityFailure()));
    expect((await diag.get()).integrityFailures).toBe(N);
  });

  it("a failing write does not block later updates", async () => {
    const inner = new MemoryStore();
    let fail = true;
    const store: KVStore = {
      ...inner,
      get: (s, k) => inner.get(s, k),
      put: async (s, k, v) => {
        if (fail) {
          fail = false;
          throw new Error("disk full");
        }
        return inner.put(s, k, v);
      },
      getAll: (s) => inner.getAll(s),
      delete: (s, k) => inner.delete(s, k),
      clear: (s) => inner.clear(s),
    };
    const diag = new SyncDiagnosticsStore(store);
    await expect(diag.recordPurge()).rejects.toThrow("disk full");
    await diag.recordPurge();
    expect((await diag.get()).purges).toBe(1);
  });
});
