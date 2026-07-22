import { describe, expect, it } from "vitest";

import {
  isPackageCurrent,
  isStaleShellCache,
  ownedCaches,
  packageIsStale,
  SHELL_CACHE,
} from "../cacheVersion";
import type { PackageManifest, StoredPackage } from "../types";

function manifest(hash: string): PackageManifest {
  return {
    package_id: "pkg/L1",
    lesson_id: "L1",
    objective_code: "O1",
    version: hash.slice(0, 12),
    content_hash: hash,
    assets: [],
    total_bytes: 10,
    created_at_ms: 0,
  };
}

function stored(hash: string, state: StoredPackage["state"] = "ready"): StoredPackage {
  return {
    package_id: "pkg/L1",
    lesson_id: "L1",
    content_hash: hash,
    version: hash.slice(0, 12),
    state,
    total_bytes: 10,
    installed_at: 0,
    last_used_at: 0,
  };
}

describe("cache versioning", () => {
  it("names the shell cache by app version and owns only it", () => {
    expect(SHELL_CACHE).toBe("taleem-shell-v1");
    expect(ownedCaches()).toContain(SHELL_CACHE);
  });

  it("flags old shell caches as stale, keeps the current one", () => {
    expect(isStaleShellCache("taleem-shell-v0")).toBe(true);
    expect(isStaleShellCache(SHELL_CACHE)).toBe(false);
    expect(isStaleShellCache("some-other-cache")).toBe(false);
  });

  it("detects a stale package when content hash differs (cache invalidation)", () => {
    expect(packageIsStale(stored("aaaa"), manifest("bbbb"))).toBe(true);
    expect(packageIsStale(stored("aaaa"), manifest("aaaa"))).toBe(false);
  });

  it("treats a package as current only when present, ready, and same hash", () => {
    expect(isPackageCurrent(stored("aaaa"), manifest("aaaa"))).toBe(true);
    expect(isPackageCurrent(stored("aaaa", "downloading"), manifest("aaaa"))).toBe(false);
    expect(isPackageCurrent(stored("aaaa"), manifest("bbbb"))).toBe(false);
    expect(isPackageCurrent(undefined, manifest("aaaa"))).toBe(false);
  });
});
