import { describe, expect, it, vi } from "vitest";

import { MemoryStore, STORES } from "../kv";
import { DownloadManager, QuotaExceededError, SignatureError } from "../packages";
import { importPublicKey, signingMessage } from "../signature";
import { contentHash } from "../sha256";
import type { KeyResolver } from "../signature";
import type { OfflineContent, OfflinePackage, StorageEstimate } from "../types";

const VECTOR = {
  keyId: "dev-ed25519-1",
  publicKeyHex: "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8",
};

function content(lessonId = "L1"): OfflineContent {
  return {
    lesson_id: lessonId,
    objective_code: "O1",
    title: { en: "T" },
    explanation: { en: "E" },
    worked_example_steps: [],
    practice_items: [],
    homework_items: [],
    assessment_formative: [],
    summative_mentor_mediated: true,
  };
}

// Build a package whose manifest is signed by a freshly-generated keypair; return the pkg + resolver.
async function signedPackage(
  lessonId = "L1",
  bytesTotal = 100,
): Promise<{ pkg: OfflinePackage; resolve: KeyResolver; keyId: string }> {
  const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, [
    "sign",
    "verify",
  ])) as CryptoKeyPair;
  const c = content(lessonId);
  const hash = await contentHash(c);
  const version = hash.slice(0, 12);
  const packageId = `pkg/${lessonId}`;
  const msg = signingMessage(packageId, version, hash);
  const sig = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, pair.privateKey, msg));
  const sigHex = Array.from(sig)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  const pkg: OfflinePackage = {
    manifest: {
      package_id: packageId,
      lesson_id: lessonId,
      objective_code: "O1",
      version,
      content_hash: hash,
      assets: [{ ref: `${lessonId}/content.json`, kind: "content", sha256: hash, bytes: bytesTotal }],
      total_bytes: bytesTotal,
      created_at_ms: 0,
      signature: sigHex,
      signing_key_id: "gen-1",
    },
    content: c,
  };
  const resolve: KeyResolver = async (id) => (id === "gen-1" ? pair.publicKey : null);
  return { pkg, resolve, keyId: "gen-1" };
}

async function unsignedPackage(lessonId = "L1"): Promise<OfflinePackage> {
  const c = content(lessonId);
  const hash = await contentHash(c);
  return {
    manifest: {
      package_id: `pkg/${lessonId}`,
      lesson_id: lessonId,
      objective_code: "O1",
      version: hash.slice(0, 12),
      content_hash: hash,
      assets: [],
      total_bytes: 50,
      created_at_ms: 0,
    },
    content: c,
  };
}

describe("package signature enforcement (6.2C-1)", () => {
  it("installs a validly-signed package and records signature_ok", async () => {
    const store = new MemoryStore();
    const { pkg, resolve } = await signedPackage();
    const mgr = new DownloadManager({ store, fetchPackage: async () => pkg, now: () => 1, resolveKey: resolve, requireSignature: true });
    const rec = await mgr.download("L1");
    expect(rec.signature_ok).toBe(true);
    expect((await mgr.getLesson("L1"))?.lesson_id).toBe("L1");
  });

  it("rejects a tampered signature and installs nothing", async () => {
    const store = new MemoryStore();
    const { pkg, resolve } = await signedPackage();
    const tampered: OfflinePackage = {
      ...pkg,
      manifest: { ...pkg.manifest, signature: "00".repeat(64) },
    };
    const mgr = new DownloadManager({ store, fetchPackage: async () => tampered, now: () => 1, resolveKey: resolve, requireSignature: true });
    await expect(mgr.download("L1")).rejects.toBeInstanceOf(SignatureError);
    expect(await mgr.installed("L1")).toBeUndefined();
  });

  it("rejects an unknown signing key", async () => {
    const store = new MemoryStore();
    const { pkg } = await signedPackage();
    const noKey: KeyResolver = async () => null;
    const mgr = new DownloadManager({ store, fetchPackage: async () => pkg, now: () => 1, resolveKey: noKey, requireSignature: true });
    await expect(mgr.download("L1")).rejects.toBeInstanceOf(SignatureError);
  });

  it("requireSignature rejects an unsigned package", async () => {
    const store = new MemoryStore();
    const pkg = await unsignedPackage();
    const mgr = new DownloadManager({ store, fetchPackage: async () => pkg, now: () => 1, requireSignature: true });
    await expect(mgr.download("L1")).rejects.toBeInstanceOf(SignatureError);
  });

  it("backward-compatible: an unsigned package installs when signatures are not required", async () => {
    const store = new MemoryStore();
    const pkg = await unsignedPackage();
    const mgr = new DownloadManager({ store, fetchPackage: async () => pkg, now: () => 1 });
    const rec = await mgr.download("L1");
    expect(rec.signature_ok).toBe(false);
    expect((await mgr.getLesson("L1"))?.lesson_id).toBe("L1");
  });

  it("interop: verifies the backend public key can be imported", async () => {
    // The pinned dev key from the server imports as a verify key (sanity for real wiring).
    const key = await importPublicKey(VECTOR.publicKeyHex);
    expect(key.type).toBe("public");
  });
});

describe("LRU eviction (6.2C-1)", () => {
  function est(usage: number, quota: number): () => Promise<StorageEstimate> {
    return async () => ({ usage, quota });
  }

  it("evicts least-recently-used disposable packages to make room", async () => {
    const store = new MemoryStore();
    let usage = 0;
    // estimate reflects installed package bytes (simplified): usage grows as we install.
    const mgr = new DownloadManager({
      store,
      fetchPackage: async () => await unsignedPackage("X"),
      now: () => 1,
      estimate: async () => ({ usage, quota: 120 }),
      events: { onEviction: () => undefined },
    });

    // Pre-install two disposable packages; A is least-recently-used (last_used_at = 1).
    await store.put(STORES.packages, "A", { package_id: "pkg/A", lesson_id: "A", content_hash: "a", version: "a", state: "ready", total_bytes: 50, installed_at: 1, last_used_at: 1 });
    await store.put(STORES.packages, "B", { package_id: "pkg/B", lesson_id: "B", content_hash: "b", version: "b", state: "ready", total_bytes: 50, installed_at: 1, last_used_at: 2 });
    usage = 100;

    // Free ≥ 40: evicting A (50 bytes, oldest) suffices → A gone, B kept.
    const freed = await mgr.evictLRU(40);
    expect(freed).toBe(50);
    expect(await store.get(STORES.packages, "A")).toBeUndefined();
    expect(await store.get(STORES.packages, "B")).toBeDefined();
  });

  it("refuses a download that cannot fit even after eviction", async () => {
    const store = new MemoryStore();
    const mgr = new DownloadManager({
      store,
      fetchPackage: async () => await unsignedPackage("Big"),
      now: () => 1,
      estimate: est(100, 100), // 0 free, nothing to evict
    });
    await expect(mgr.download("Big")).rejects.toBeInstanceOf(QuotaExceededError);
  });

  it("evictLRU returns 0 when nothing needs freeing", async () => {
    const store = new MemoryStore();
    const mgr = new DownloadManager({ store, fetchPackage: async () => await unsignedPackage(), now: () => 1 });
    expect(await mgr.evictLRU(0)).toBe(0);
  });
});
