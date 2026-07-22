// Sync diagnostics (Phase 6.2B) — LOCAL counters only.
//
// Records what the sync engine did (queued / applied / duplicate / ignored / conflict / failed /
// dead-lettered / drains + last sync time + last error) so the UI and support can see health.
// This is NOT telemetry upload — nothing leaves the device (consent-gated upload is out of scope).

import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { SyncDiagnostics } from "./types";

const KEY = "sync_diagnostics";

function empty(): SyncDiagnostics {
  return {
    queued: 0,
    applied: 0,
    duplicate: 0,
    ignored: 0,
    conflict: 0,
    failed: 0,
    deadLettered: 0,
    drains: 0,
    lastSyncAt: null,
    lastError: null,
    signatureFailures: 0,
    integrityFailures: 0,
    evictions: 0,
    evictedBytes: 0,
    purges: 0,
  };
}

// Tolerate diagnostics written by an older build (6.2B) that lacked the 6.2C-1 counters.
function hydrate(stored: SyncDiagnostics | undefined): SyncDiagnostics {
  return { ...empty(), ...(stored ?? {}) };
}

export class SyncDiagnosticsStore {
  constructor(
    private readonly store: KVStore,
    private readonly now: () => number = Date.now,
  ) {}

  async get(): Promise<SyncDiagnostics> {
    return hydrate(await this.store.get<SyncDiagnostics>(STORES.syncMeta, KEY));
  }

  private async update(fn: (d: SyncDiagnostics) => SyncDiagnostics): Promise<void> {
    const current = await this.get();
    await this.store.put<SyncDiagnostics>(STORES.syncMeta, KEY, fn(current));
  }

  async recordQueued(n = 1): Promise<void> {
    await this.update((d) => ({ ...d, queued: d.queued + n }));
  }

  async recordSignatureFailure(): Promise<void> {
    await this.update((d) => ({ ...d, signatureFailures: d.signatureFailures + 1 }));
  }

  async recordIntegrityFailure(): Promise<void> {
    await this.update((d) => ({ ...d, integrityFailures: d.integrityFailures + 1 }));
  }

  async recordEviction(bytes: number): Promise<void> {
    await this.update((d) => ({
      ...d,
      evictions: d.evictions + 1,
      evictedBytes: d.evictedBytes + Math.max(0, bytes),
    }));
  }

  async recordPurge(): Promise<void> {
    await this.update((d) => ({ ...d, purges: d.purges + 1 }));
  }

  async recordDrain(delta: Partial<SyncDiagnostics>, error?: string): Promise<void> {
    await this.update((d) => ({
      ...d,
      applied: d.applied + (delta.applied ?? 0),
      duplicate: d.duplicate + (delta.duplicate ?? 0),
      ignored: d.ignored + (delta.ignored ?? 0),
      conflict: d.conflict + (delta.conflict ?? 0),
      failed: d.failed + (delta.failed ?? 0),
      deadLettered: d.deadLettered + (delta.deadLettered ?? 0),
      drains: d.drains + 1,
      lastSyncAt: this.now(),
      lastError: error ?? d.lastError,
    }));
  }

  async reset(): Promise<void> {
    await this.store.put<SyncDiagnostics>(STORES.syncMeta, KEY, empty());
  }
}
