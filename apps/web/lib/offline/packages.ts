// Download manager + offline lesson store (Phase 6.2A).
//
// Fetches an offline package, VERIFIES its content against the manifest hash, and installs it
// atomically into the local store (content + a package registry record). Also exposes the cached
// lesson for offline rendering and a storage pre-flight so a device is never over-filled.
// No background sync, no signing (6.2B/6.2C). Operates over injected deps for testability.

import { isPackageCurrent } from "./cacheVersion";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import { verifyContent } from "./sha256";
import type {
  OfflineContent,
  OfflinePackage,
  PackageManifest,
  StorageEstimate,
  StoredPackage,
} from "./types";

export interface DownloadDeps {
  store: KVStore;
  // Fetch a full package (manifest + content) for a lesson.
  fetchPackage: (lessonId: string) => Promise<OfflinePackage>;
  // Current time in ms (injectable for tests).
  now: () => number;
  // Storage estimate (injectable; wraps navigator.storage.estimate in the browser).
  estimate?: () => Promise<StorageEstimate>;
  // Reserve headroom so the device is never filled to the brim.
  headroomBytes?: number;
}

export class QuotaExceededError extends Error {
  constructor(
    readonly needed: number,
    readonly available: number,
  ) {
    super(`insufficient storage: need ${needed}, have ${available}`);
    this.name = "QuotaExceededError";
  }
}

export class IntegrityError extends Error {
  constructor(readonly lessonId: string) {
    super(`content integrity check failed for ${lessonId}`);
    this.name = "IntegrityError";
  }
}

// Pure storage pre-flight (mirrors backend fits_in_quota).
export function fitsInQuota(
  totalBytes: number,
  estimate: StorageEstimate,
  headroomBytes = 0,
): boolean {
  const available = Math.max(0, estimate.quota - estimate.usage);
  return totalBytes + headroomBytes <= available;
}

export class DownloadManager {
  constructor(private readonly deps: DownloadDeps) {}

  async installedPackages(): Promise<StoredPackage[]> {
    return this.deps.store.getAll<StoredPackage>(STORES.packages);
  }

  async installed(lessonId: string): Promise<StoredPackage | undefined> {
    return this.deps.store.get<StoredPackage>(STORES.packages, lessonId);
  }

  // Is the cached copy present + current for the given manifest?
  async isCurrent(manifest: PackageManifest): Promise<boolean> {
    return isPackageCurrent(await this.installed(manifest.lesson_id), manifest);
  }

  // Download, verify, and install a lesson package. Returns the installed record.
  // onProgress receives a 0..1 fraction (fetch → verify → store).
  async download(
    lessonId: string,
    onProgress?: (fraction: number) => void,
  ): Promise<StoredPackage> {
    onProgress?.(0);
    const pkg = await this.deps.fetchPackage(lessonId);
    onProgress?.(0.4);

    // Storage pre-flight — refuse rather than half-install.
    if (this.deps.estimate) {
      const est = await this.deps.estimate();
      if (!fitsInQuota(pkg.manifest.total_bytes, est, this.deps.headroomBytes ?? 0)) {
        throw new QuotaExceededError(
          pkg.manifest.total_bytes,
          Math.max(0, est.quota - est.usage),
        );
      }
    }

    // Integrity: the received content must match the manifest's content hash.
    const ok = await verifyContent(pkg.content, pkg.manifest.content_hash);
    if (!ok) throw new IntegrityError(lessonId);
    onProgress?.(0.7);

    // Atomic-ish install: write content, then flip the registry record to "ready".
    await this.deps.store.put<OfflineContent>(STORES.content, lessonId, pkg.content);
    const record: StoredPackage = {
      package_id: pkg.manifest.package_id,
      lesson_id: pkg.manifest.lesson_id,
      content_hash: pkg.manifest.content_hash,
      version: pkg.manifest.version,
      state: "ready",
      total_bytes: pkg.manifest.total_bytes,
      installed_at: this.deps.now(),
      last_used_at: this.deps.now(),
    };
    await this.deps.store.put<StoredPackage>(STORES.packages, lessonId, record);
    onProgress?.(1);
    return record;
  }

  // The cached lesson content for offline rendering (undefined if not installed).
  async getLesson(lessonId: string): Promise<OfflineContent | undefined> {
    const content = await this.deps.store.get<OfflineContent>(STORES.content, lessonId);
    if (content) {
      const rec = await this.installed(lessonId);
      if (rec) {
        rec.last_used_at = this.deps.now();
        await this.deps.store.put<StoredPackage>(STORES.packages, lessonId, rec);
      }
    }
    return content;
  }

  // Remove an installed package (used by low-storage eviction of disposable content).
  async remove(lessonId: string): Promise<void> {
    await this.deps.store.delete(STORES.content, lessonId);
    await this.deps.store.delete(STORES.packages, lessonId);
  }
}

// Browser storage estimate wrapper (StorageManager). Returns zeros where unavailable.
export async function browserEstimate(): Promise<StorageEstimate> {
  if (typeof navigator !== "undefined" && navigator.storage?.estimate) {
    const e = await navigator.storage.estimate();
    return { usage: e.usage ?? 0, quota: e.quota ?? 0 };
  }
  return { usage: 0, quota: 0 };
}

// Ask the browser to keep our data resistant to eviction (best-effort).
export async function requestPersistentStorage(): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.storage?.persist) {
    return navigator.storage.persist();
  }
  return false;
}
