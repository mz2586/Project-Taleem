// Offline-lite public surface (Phase 6.2A). Composes the local stores over IndexedDB and exposes a
// single `OfflineClient`. Browser-only side effects are guarded so this is import-safe under SSR.

import { watchConnectivity } from "./connectivity";
import type { ConnectivityListener } from "./connectivity";
import { CheckpointStore } from "./checkpoint";
import { SyncDiagnosticsStore } from "./diagnostics";
import { createStore } from "./kv";
import type { KVStore } from "./kv";
import {
  browserEstimate,
  DownloadManager,
  requestPersistentStorage,
} from "./packages";
import { ProgressStore } from "./progress";
import { PurgeService } from "./purge";
import { ReadCache } from "./readCache";
import { registerBackgroundSync, startAutoDrain } from "./backgroundSync";
import { reconcileAndResume } from "./reconcile";
import { pinnedKeyResolver } from "./signature";
import type { KeyResolver } from "./signature";
import { SyncClient } from "./syncClient";
import { SyncQueue } from "./syncQueue";
import type { PurgeResult } from "./purge";
import type { BatchResult, DrainSummary, OfflinePackage, SyncDelta } from "./types";

export * from "./types";
export { STORES } from "./kv";
export { SHELL_CACHE, APP_SHELL_VERSION, packageIsStale, isPackageCurrent } from "./cacheVersion";
export { fitsInQuota, QuotaExceededError, IntegrityError, SignatureError } from "./packages";
export { watchConnectivity, currentlyOnline, makeProbe } from "./connectivity";
export { SyncQueue } from "./syncQueue";
export { SyncClient, backoffMs } from "./syncClient";
export { SyncDiagnosticsStore } from "./diagnostics";
export { registerBackgroundSync, startAutoDrain, SYNC_TAG } from "./backgroundSync";
export { reconcileAndResume } from "./reconcile";
export { PurgeService } from "./purge";
export { pinnedKeyResolver, importPublicKey, verifyManifestSignature } from "./signature";
export { FaultyStore, faultyPostBatch } from "./chaos";
export { uuid7 } from "./ids";

export interface OfflineSync {
  queue: SyncQueue;
  client: SyncClient;
  diagnostics: SyncDiagnosticsStore;
  drain: () => Promise<DrainSummary>;
  reconcile: (studentRef: string) => Promise<{ enqueued: number; drain: DrainSummary }>;
  startAutoDrain: () => () => void;
  registerBackgroundSync: () => Promise<boolean>;
}

export interface OfflineClient {
  downloads: DownloadManager;
  progress: ProgressStore;
  checkpoints: CheckpointStore;
  reads: ReadCache;
  sync: OfflineSync;
  purge: PurgeService;
  purgeStudent: (studentRef: string) => Promise<PurgeResult>;
  requestPersistentStorage: () => Promise<boolean>;
  watchConnectivity: (l: ConnectivityListener) => () => void;
}

export interface CreateClientOptions {
  store?: KVStore;
  fetchPackage: (lessonId: string) => Promise<OfflinePackage>;
  // POST a sync batch (wired to the /v1/sync/batch client). Required for the sync engine to drain.
  postBatch: (cursor: number, deltas: SyncDelta[]) => Promise<BatchResult>;
  now?: () => number;
  headroomBytes?: number;
  // 6.2C-1: pinned Ed25519 public keys { key_id -> public_key_hex } to verify package signatures.
  pinnedKeys?: Record<string, string>;
  // 6.2C-1: reject an unsigned/unverifiable package rather than installing it.
  requireSignature?: boolean;
}

// Build an offline client over the given (or default IndexedDB) store.
export function createOfflineClient(opts: CreateClientOptions): OfflineClient {
  const store = opts.store ?? createStore();
  const now = opts.now ?? Date.now;
  const diagnostics = new SyncDiagnosticsStore(store, now);

  const resolveKey: KeyResolver | undefined = opts.pinnedKeys
    ? pinnedKeyResolver(opts.pinnedKeys)
    : undefined;

  const downloads = new DownloadManager({
    store,
    fetchPackage: opts.fetchPackage,
    now,
    estimate: browserEstimate,
    ...(opts.headroomBytes !== undefined ? { headroomBytes: opts.headroomBytes } : {}),
    ...(resolveKey ? { resolveKey } : {}),
    ...(opts.requireSignature !== undefined ? { requireSignature: opts.requireSignature } : {}),
    events: {
      onSignatureFailure: () => void diagnostics.recordSignatureFailure(),
      onIntegrityFailure: () => void diagnostics.recordIntegrityFailure(),
      onEviction: (_lesson, bytes) => void diagnostics.recordEviction(bytes),
    },
  });
  const progress = new ProgressStore(store, now);
  const checkpoints = new CheckpointStore(store, now);
  const reads = new ReadCache(store, now);
  const purge = new PurgeService(store, diagnostics);

  const queue = new SyncQueue(store, now);
  const client = new SyncClient({
    queue,
    store,
    diagnostics,
    postBatch: opts.postBatch,
    onPurge: async (refs) => {
      for (const ref of refs) await purge.purgeStudent(ref);
    },
  });
  const drain = () => client.drain();

  const sync: OfflineSync = {
    queue,
    client,
    diagnostics,
    drain,
    reconcile: (studentRef: string) =>
      reconcileAndResume(studentRef, { progress, checkpoints, queue, drain }),
    startAutoDrain: () => startAutoDrain({ drain }),
    registerBackgroundSync: () => registerBackgroundSync(),
  };

  return {
    downloads,
    progress,
    checkpoints,
    reads,
    sync,
    purge,
    purgeStudent: (studentRef: string) => purge.purgeStudent(studentRef),
    requestPersistentStorage,
    watchConnectivity: (l: ConnectivityListener) => watchConnectivity(l),
  };
}

// Register the service worker (app-shell + runtime caching). No-op off the browser / unsupported.
export async function registerServiceWorker(path = "/sw.js"): Promise<void> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register(path);
  } catch {
    // Registration failure must never break the app; offline simply won't be available.
  }
}
