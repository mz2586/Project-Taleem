// Fault-injection framework (Phase 6.2C-1).
//
// Reusable primitives for chaos / resilience testing of the offline subsystem: a KVStore wrapper
// that injects storage faults (throw, quota-exceeded, crash-after-N-ops) and a network wrapper that
// injects intermittent/flapping failures. Deterministic + injectable so the chaos scenarios in the
// test plan (CX-1 kill mid-op, CX-3 flapping network, CX-4 quota exhaustion) run without a browser.
//
// This lives in lib (not tests) so it is a maintained, typed framework — usable by any offline test
// and by future integration harnesses. It touches no real storage of its own.

import type { KVStore, StoreName } from "./kv";
import { QuotaExceededError } from "./packages";
import type { BatchResult, SyncDelta } from "./types";

export type FaultMode = "throw" | "quota";

export interface StoreFaultConfig {
  // Fail operations of these kinds (default: all writes).
  failOn?: Array<"get" | "put" | "getAll" | "delete" | "clear">;
  // Begin failing at (and after) this 1-based operation count on the matched kinds.
  failAfterOps?: number;
  // Stop failing after this many failures (so a "crash" can be followed by recovery).
  maxFailures?: number;
  mode?: FaultMode;
  // A live toggle — when false, the wrapper passes through untouched.
  enabled?: boolean;
}

// Wraps a KVStore and injects faults per config. The inner store is never corrupted by the wrapper.
export class FaultyStore implements KVStore {
  private opCount = 0;
  private failures = 0;

  constructor(
    private readonly inner: KVStore,
    public config: StoreFaultConfig = {},
  ) {}

  private shouldFail(kind: "get" | "put" | "getAll" | "delete" | "clear"): boolean {
    if (this.config.enabled === false) return false;
    const kinds = this.config.failOn ?? ["put", "delete", "clear"];
    if (!kinds.includes(kind)) return false;
    this.opCount++;
    if (this.opCount < (this.config.failAfterOps ?? 1)) return false;
    if (this.config.maxFailures !== undefined && this.failures >= this.config.maxFailures) {
      return false;
    }
    this.failures++;
    return true;
  }

  private fault(kind: string): never {
    if ((this.config.mode ?? "throw") === "quota") throw new QuotaExceededError(1, 0);
    throw new Error(`injected fault on ${kind}`);
  }

  async get<T>(store: StoreName, key: string): Promise<T | undefined> {
    if (this.shouldFail("get")) this.fault("get");
    return this.inner.get<T>(store, key);
  }

  async put<T>(store: StoreName, key: string, value: T): Promise<void> {
    if (this.shouldFail("put")) this.fault("put");
    return this.inner.put<T>(store, key, value);
  }

  async getAll<T>(store: StoreName): Promise<T[]> {
    if (this.shouldFail("getAll")) this.fault("getAll");
    return this.inner.getAll<T>(store);
  }

  async delete(store: StoreName, key: string): Promise<void> {
    if (this.shouldFail("delete")) this.fault("delete");
    return this.inner.delete(store, key);
  }

  async clear(store: StoreName): Promise<void> {
    if (this.shouldFail("clear")) this.fault("clear");
    return this.inner.clear(store);
  }
}

export interface NetworkFaultConfig {
  // Throw (simulate offline) for the first N calls, then pass through.
  offlineForFirst?: number;
  // A live toggle for flapping: when true, every call throws.
  offline?: boolean;
}

// Wrap a postBatch with intermittent/flapping network faults for drain-resilience tests.
export function faultyPostBatch(
  inner: (cursor: number, deltas: SyncDelta[]) => Promise<BatchResult>,
  config: NetworkFaultConfig,
): (cursor: number, deltas: SyncDelta[]) => Promise<BatchResult> {
  let calls = 0;
  return async (cursor: number, deltas: SyncDelta[]) => {
    calls++;
    if (config.offline) throw new Error("injected network fault (offline)");
    if (config.offlineForFirst !== undefined && calls <= config.offlineForFirst) {
      throw new Error("injected network fault (offline)");
    }
    return inner(cursor, deltas);
  };
}
