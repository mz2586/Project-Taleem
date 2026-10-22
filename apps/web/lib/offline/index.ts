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
import { configuredSigningKeys, keyPinningDiagnostic, trustedKeyResolver } from "./keys";
import type { KeyPinningDiagnostic } from "./keys";
import type { DownloadEvents } from "./packages";
import { SyncClient } from "./syncClient";
import { SyncQueue } from "./syncQueue";
import { AckLedger } from "./syncStatus";
import type { PurgeResult } from "./purge";
import type { BatchResult, DrainSummary, OfflinePackage, SigningKey, StorageEstimate, SyncDelta } from "./types";

export * from "./types";
export { STORES } from "./kv";
export { SHELL_CACHE, APP_SHELL_VERSION, packageIsStale, isPackageCurrent } from "./cacheVersion";
export { fitsInQuota, QuotaExceededError, IntegrityError, SignatureError, DownloadManager } from "./packages";
export {
  configuredSigningKeys,
  keyPinningDiagnostic,
  mergeSigningKeys,
  trustedKeyResolver,
} from "./keys";
export type { KeyMerge, KeyPinningDiagnostic } from "./keys";
export { watchConnectivity, currentlyOnline, makeProbe } from "./connectivity";
export { SyncQueue, ownerOf } from "./syncQueue";
export { SyncClient, backoffMs, classifyFailure, LEARNER_LEVEL_REFUSALS } from "./syncClient";
export {
  AckLedger,
  ackedItemStatus,
  isDurableAck,
  itemStatus,
  queuedItemStatus,
  summarizeSyncStatus,
} from "./syncStatus";
export type { ItemBlock, ItemStatus, ItemSyncState, SyncStatusSummary } from "./syncStatus";
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
  acks: AckLedger;
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
  /** Non-null when this build relies on trust-on-first-use keys in production. */
  keyPinning: KeyPinningDiagnostic | null;
  /** Resolves once the key-pinning state is recorded in diagnostics. */
  keyPinningRecorded: Promise<void>;
}

export interface CreateClientOptions {
  store?: KVStore;
  fetchPackage: (lessonId: string) => Promise<OfflinePackage>;
  // POST a sync batch (wired to the /v1/sync/batch client). Required for the sync engine to drain.
  postBatch: (cursor: number, deltas: SyncDelta[]) => Promise<BatchResult>;
  now?: () => number;
  headroomBytes?: number;
  // Build-time pinned Ed25519 public keys { key_id -> public_key_hex }. Defaults to
  // NEXT_PUBLIC_OFFLINE_SIGNING_KEYS. Preferred over trust-on-first-use.
  pinnedKeys?: Record<string, string>;
  // GET /v1/offline/signing-keys, for trust-on-first-use of a key_id this device has never seen.
  fetchSigningKeys?: () => Promise<{ keys: SigningKey[] }>;
  // Signatures are always required (see DownloadDeps). Kept so `true` still type-checks.
  requireSignature?: true;
  // Test-only opt-out, honoured only under Vitest (see DownloadDeps.allowUnsignedForTests).
  allowUnsignedForTests?: true;
  // The build mode, for the key-pinning diagnostic (default process.env.NODE_ENV).
  nodeEnv?: string;
  // Force one session refresh after a 401 during a drain (the session store's single-flight
  // refresh). Resolves true when a usable session exists afterwards.
  refreshSession?: () => Promise<boolean>;
  // The signed-in learner whose token carries the batch (null = none; nothing is sent).
  currentLearner?: () => string | null;
}

export interface DownloadConfig {
  store: KVStore;
  fetchPackage: (lessonId: string) => Promise<OfflinePackage>;
  now?: () => number;
  estimate?: () => Promise<StorageEstimate>;
  headroomBytes?: number;
  pinnedKeys?: Record<string, string>;
  fetchSigningKeys?: () => Promise<{ keys: SigningKey[] }>;
  allowUnsignedForTests?: true;
  events?: DownloadEvents;
}

// THE download-manager configuration: every install path goes through this, so every package is
// signature-verified against the same trusted keys (pinned, else trust-on-first-use).
export function createDownloadManager(config: DownloadConfig): DownloadManager {
  return new DownloadManager({
    store: config.store,
    fetchPackage: config.fetchPackage,
    now: config.now ?? Date.now,
    ...(config.estimate ? { estimate: config.estimate } : {}),
    ...(config.headroomBytes !== undefined ? { headroomBytes: config.headroomBytes } : {}),
    resolveKey: trustedKeyResolver({
      store: config.store,
      configured: config.pinnedKeys ?? configuredSigningKeys(),
      ...(config.fetchSigningKeys ? { fetchKeys: config.fetchSigningKeys } : {}),
    }),
    requireSignature: true,
    ...(config.allowUnsignedForTests ? { allowUnsignedForTests: true as const } : {}),
    ...(config.events ? { events: config.events } : {}),
  });
}

// Build an offline client over the given (or default IndexedDB) store.
export function createOfflineClient(opts: CreateClientOptions): OfflineClient {
  const store = opts.store ?? createStore();
  const now = opts.now ?? Date.now;
  const diagnostics = new SyncDiagnosticsStore(store, now);

  const pinnedKeys = opts.pinnedKeys ?? configuredSigningKeys();
  const keyPinning = keyPinningDiagnostic({ configured: pinnedKeys, nodeEnv: opts.nodeEnv ?? process.env.NODE_ENV });
  if (keyPinning && typeof console !== "undefined") console.warn(`[taleem] ${keyPinning.code}: ${keyPinning.message}`);
  const keyPinningRecorded = diagnostics
    .recordKeyPinning(Object.keys(pinnedKeys).length > 0)
    .catch(() => undefined);

  const downloads = createDownloadManager({
    store,
    fetchPackage: opts.fetchPackage,
    now,
    estimate: browserEstimate,
    ...(opts.headroomBytes !== undefined ? { headroomBytes: opts.headroomBytes } : {}),
    pinnedKeys,
    ...(opts.fetchSigningKeys ? { fetchSigningKeys: opts.fetchSigningKeys } : {}),
    ...(opts.allowUnsignedForTests ? { allowUnsignedForTests: true as const } : {}),
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
  const acks = new AckLedger(store);
  const client = new SyncClient({
    queue,
    store,
    diagnostics,
    acks,
    now,
    postBatch: opts.postBatch,
    ...(opts.refreshSession ? { refreshSession: opts.refreshSession } : {}),
    ...(opts.currentLearner ? { currentLearner: opts.currentLearner } : {}),
    onPurge: async (refs) => {
      for (const ref of refs) {
        await purge.purgeStudent(ref);
        await acks.forget(ref);
      }
    },
  });
  const drain = () => client.drain();

  const sync: OfflineSync = {
    queue,
    client,
    diagnostics,
    acks,
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
    keyPinning,
    keyPinningRecorded,
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
