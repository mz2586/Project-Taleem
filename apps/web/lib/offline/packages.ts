// Download manager + offline lesson store (Phase 6.2A; hardened in 6.2C-1).
//
// Fetches an offline package, VERIFIES its Ed25519 signature (6.2C-1) and its content hash, and
// installs it atomically into the local store (content + a package registry record). Also exposes
// the cached lesson for offline rendering, a storage pre-flight, and LRU eviction of disposable
// packages (6.2C-1) — never touching the un-synced queue/checkpoints. Operates over injected deps.

import { isPackageCurrent } from "./cacheVersion";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import { verifyContent } from "./sha256";
import { verifyManifestSignature } from "./signature";
import type { KeyResolver } from "./signature";
import type {
  OfflineContent,
  OfflinePackage,
  PackageManifest,
  StorageEstimate,
  StoredPackage,
} from "./types";

// Optional hook so the download path can record hardening events (6.2C-1) without a hard dependency.
export interface DownloadEvents {
  onSignatureFailure?: (lessonId: string, keyId: string) => void;
  onIntegrityFailure?: (lessonId: string) => void;
  onEviction?: (lessonId: string, bytes: number) => void;
}

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
  // 6.2C-1 signature verification: resolves a pinned public key by signing_key_id.
  resolveKey?: KeyResolver;
  // 6.2C-1: if true, an unsigned manifest (or one whose key is unknown) is rejected.
  requireSignature?: boolean;
  // 6.2C-1: optional hardening-event hook (diagnostics).
  events?: DownloadEvents;
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

export class SignatureError extends Error {
  constructor(
    readonly lessonId: string,
    readonly keyId: string,
  ) {
    super(`package signature verification failed for ${lessonId} (key ${keyId || "none"})`);
    this.name = "SignatureError";
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
    onProgress?.(0.3);

    // Signature verification (6.2C-1) — BEFORE trusting any bytes. Provenance + downgrade-resistance.
    const signatureOk = await this.verifySignature(pkg.manifest);
    onProgress?.(0.5);

    // Storage pre-flight — try LRU eviction of disposable packages, then refuse rather than half-install.
    await this.ensureSpace(pkg.manifest.total_bytes);

    // Integrity: the received content must match the manifest's content hash.
    const ok = await verifyContent(pkg.content, pkg.manifest.content_hash);
    if (!ok) {
      this.deps.events?.onIntegrityFailure?.(lessonId);
      throw new IntegrityError(lessonId);
    }
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
      signature_ok: signatureOk,
    };
    await this.deps.store.put<StoredPackage>(STORES.packages, lessonId, record);
    onProgress?.(1);
    return record;
  }

  // Verify the manifest signature against a pinned key. Returns whether a valid signature was
  // present; throws SignatureError when verification fails or a signature is required but absent.
  private async verifySignature(manifest: PackageManifest): Promise<boolean> {
    const keyId = manifest.signing_key_id ?? "";
    const hasSignature = Boolean(manifest.signature) && Boolean(keyId);
    if (!hasSignature) {
      if (this.deps.requireSignature) {
        this.deps.events?.onSignatureFailure?.(manifest.lesson_id, keyId);
        throw new SignatureError(manifest.lesson_id, keyId);
      }
      return false; // unsigned + not required → backward-compatible (6.2A/6.2B) install
    }
    if (!this.deps.resolveKey) {
      // A signature is present but the client cannot resolve keys.
      if (this.deps.requireSignature) {
        this.deps.events?.onSignatureFailure?.(manifest.lesson_id, keyId);
        throw new SignatureError(manifest.lesson_id, keyId);
      }
      return false;
    }
    const key = await this.deps.resolveKey(keyId);
    const ok = key !== null && (await verifyManifestSignature(manifest, key));
    if (!ok) {
      this.deps.events?.onSignatureFailure?.(manifest.lesson_id, keyId);
      throw new SignatureError(manifest.lesson_id, keyId);
    }
    return true;
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

  // Ensure `needBytes` can fit: if not, LRU-evict disposable packages, then refuse if still short.
  // Only ever evicts installed packages/content (C0 curriculum, always re-downloadable) — NEVER the
  // un-synced evidence queue or checkpoints (those live in other stores and are untouched here).
  async ensureSpace(needBytes: number): Promise<void> {
    if (!this.deps.estimate) return;
    const headroom = this.deps.headroomBytes ?? 0;
    let est = await this.deps.estimate();
    if (fitsInQuota(needBytes, est, headroom)) return;

    const deficit = needBytes + headroom - Math.max(0, est.quota - est.usage);
    await this.evictLRU(deficit);

    est = await this.deps.estimate();
    if (!fitsInQuota(needBytes, est, headroom)) {
      throw new QuotaExceededError(needBytes, Math.max(0, est.quota - est.usage));
    }
  }

  // Evict disposable packages, least-recently-used first, until ≥ bytesToFree is removed.
  // Returns bytes freed. Safe: packages/content are re-downloadable curriculum (C0).
  async evictLRU(bytesToFree: number): Promise<number> {
    if (bytesToFree <= 0) return 0;
    const byLru = (await this.installedPackages()).sort(
      (a, b) => a.last_used_at - b.last_used_at,
    );
    let freed = 0;
    for (const pkg of byLru) {
      if (freed >= bytesToFree) break;
      await this.remove(pkg.lesson_id);
      freed += pkg.total_bytes;
      this.deps.events?.onEviction?.(pkg.lesson_id, pkg.total_bytes);
    }
    return freed;
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
