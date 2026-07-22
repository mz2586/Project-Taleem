// Offline-lite public surface (Phase 6.2A). Composes the local stores over IndexedDB and exposes a
// single `OfflineClient`. Browser-only side effects are guarded so this is import-safe under SSR.

import { watchConnectivity } from "./connectivity";
import type { ConnectivityListener } from "./connectivity";
import { CheckpointStore } from "./checkpoint";
import { createStore } from "./kv";
import type { KVStore } from "./kv";
import {
  browserEstimate,
  DownloadManager,
  requestPersistentStorage,
} from "./packages";
import { ProgressStore } from "./progress";
import { ReadCache } from "./readCache";
import type { OfflinePackage } from "./types";

export * from "./types";
export { STORES } from "./kv";
export { SHELL_CACHE, APP_SHELL_VERSION, packageIsStale, isPackageCurrent } from "./cacheVersion";
export { fitsInQuota, QuotaExceededError, IntegrityError } from "./packages";
export { watchConnectivity, currentlyOnline, makeProbe } from "./connectivity";
export { uuid7 } from "./ids";

export interface OfflineClient {
  downloads: DownloadManager;
  progress: ProgressStore;
  checkpoints: CheckpointStore;
  reads: ReadCache;
  requestPersistentStorage: () => Promise<boolean>;
  watchConnectivity: (l: ConnectivityListener) => () => void;
}

export interface CreateClientOptions {
  store?: KVStore;
  fetchPackage: (lessonId: string) => Promise<OfflinePackage>;
  now?: () => number;
  headroomBytes?: number;
}

// Build an offline client over the given (or default IndexedDB) store.
export function createOfflineClient(opts: CreateClientOptions): OfflineClient {
  const store = opts.store ?? createStore();
  const now = opts.now ?? Date.now;
  const downloads = new DownloadManager({
    store,
    fetchPackage: opts.fetchPackage,
    now,
    estimate: browserEstimate,
    ...(opts.headroomBytes !== undefined ? { headroomBytes: opts.headroomBytes } : {}),
  });
  return {
    downloads,
    progress: new ProgressStore(store, now),
    checkpoints: new CheckpointStore(store, now),
    reads: new ReadCache(store, now),
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
