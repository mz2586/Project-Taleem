import { describe, expect, it } from "vitest";

import { SyncDiagnosticsStore } from "../diagnostics";
import { MemoryStore } from "../kv";
import { STORES } from "../kv";
import type { SyncDiagnostics } from "../types";

describe("diagnostics enhancements (6.2C-1)", () => {
  it("records the new hardening counters (local-only, no PII)", async () => {
    const store = new MemoryStore();
    const diag = new SyncDiagnosticsStore(store, () => 1);
    await diag.recordSignatureFailure();
    await diag.recordIntegrityFailure();
    await diag.recordEviction(500);
    await diag.recordEviction(100);
    await diag.recordPurge();
    const d = await diag.get();
    expect(d.signatureFailures).toBe(1);
    expect(d.integrityFailures).toBe(1);
    expect(d.evictions).toBe(2);
    expect(d.evictedBytes).toBe(600);
    expect(d.purges).toBe(1);
    // No student_ref / content anywhere in the diagnostics payload (C1 counters only).
    expect(JSON.stringify(d)).not.toContain("student");
  });

  it("hydrates diagnostics written by an older build that lacked the new counters", async () => {
    const store = new MemoryStore();
    // Simulate a 6.2B-shaped record missing the 6.2C-1 fields.
    await store.put(STORES.syncMeta, "sync_diagnostics", {
      queued: 3,
      applied: 2,
      duplicate: 0,
      ignored: 0,
      conflict: 0,
      failed: 0,
      deadLettered: 0,
      drains: 1,
      lastSyncAt: 10,
      lastError: null,
    } satisfies Partial<SyncDiagnostics> as SyncDiagnostics);
    const diag = new SyncDiagnosticsStore(store, () => 1);
    const d = await diag.get();
    expect(d.applied).toBe(2); // old fields preserved
    expect(d.signatureFailures).toBe(0); // new fields defaulted
    expect(d.evictedBytes).toBe(0);
    // and recording still works after hydration
    await diag.recordEviction(42);
    expect((await diag.get()).evictedBytes).toBe(42);
  });
});
