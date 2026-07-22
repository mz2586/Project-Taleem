// Automatic cache versioning (Phase 6.2A) — pure functions, no I/O.
//
// The app-shell cache is named by app version; content packages are addressed by content_hash, so a
// content change yields a new version and the client treats the cached copy as stale (automatic
// invalidation). Mirrors OFFLINE_ARCHITECTURE.md §6 and the backend `version = content_hash[:12]`.

import type { PackageManifest, StoredPackage } from "./types";

export const APP_SHELL_VERSION = "v1";
export const SHELL_CACHE = `taleem-shell-${APP_SHELL_VERSION}`;

// Cache names this app owns; the service worker deletes every other `taleem-*` cache on activate.
export function ownedCaches(): string[] {
  return [SHELL_CACHE];
}

export function isOwnedCache(name: string): boolean {
  return ownedCaches().includes(name);
}

// True if a cache should be purged on activate: ours by prefix, but not the current version.
export function isStaleShellCache(name: string): boolean {
  return name.startsWith("taleem-shell-") && !isOwnedCache(name);
}

// A stored package is stale relative to a freshly-fetched manifest iff the content hash differs.
export function packageIsStale(stored: StoredPackage, latest: PackageManifest): boolean {
  return stored.content_hash !== latest.content_hash;
}

// Does the installed package satisfy the wanted manifest (present + same content hash + ready)?
export function isPackageCurrent(
  stored: StoredPackage | undefined,
  latest: PackageManifest,
): boolean {
  return (
    stored !== undefined && stored.state === "ready" && stored.content_hash === latest.content_hash
  );
}
