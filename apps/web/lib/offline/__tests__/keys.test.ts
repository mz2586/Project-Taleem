// Signing-key trust and the fail-closed install default across the shared client.
import { describe, expect, it, vi } from "vitest";

import { createOfflineClient } from "..";
import { keyPinningDiagnostic, trustedKeyResolver } from "../keys";
import { MemoryStore, STORES } from "../kv";
import { SignatureError } from "../packages";
import { contentHash } from "../sha256";
import { signingMessage } from "../signature";
import type { OfflineContent, OfflinePackage, SigningKey } from "../types";

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

const content: OfflineContent = {
  lesson_id: "L1",
  objective_code: "O1",
  title: { en: "T" },
  explanation: { en: "E" },
  worked_example_steps: [],
  practice_items: [],
  homework_items: [],
  assessment_formative: [],
  summative_mentor_mediated: true,
};

async function fixture(keyId = "k1") {
  const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
  const hash = await contentHash(content);
  const manifest = {
    package_id: "pkg/L1",
    lesson_id: "L1",
    objective_code: "O1",
    version: hash.slice(0, 12),
    content_hash: hash,
    assets: [],
    total_bytes: 10,
    created_at_ms: 0,
  };
  const sig = hex(await crypto.subtle.sign({ name: "Ed25519" }, pair.privateKey, signingMessage(manifest.package_id, manifest.version, hash)));
  const key: SigningKey = { key_id: keyId, algorithm: "Ed25519", public_key_hex: hex(await crypto.subtle.exportKey("raw", pair.publicKey)) };
  const signed: OfflinePackage = { manifest: { ...manifest, signature: sig, signing_key_id: keyId }, content };
  const unsigned: OfflinePackage = { manifest, content };
  return { signed, unsigned, key };
}

function client(pkg: OfflinePackage, extra: Partial<Parameters<typeof createOfflineClient>[0]> = {}) {
  return createOfflineClient({
    store: new MemoryStore(),
    fetchPackage: async () => pkg,
    postBatch: async (cursor) => ({ cursor, results: [] }),
    pinnedKeys: {},
    ...extra,
  });
}

describe("shared client installs are fail-closed", () => {
  it("rejects an unsigned package with no options", async () => {
    const { unsigned } = await fixture();
    await expect(client(unsigned).downloads.download("L1")).rejects.toBeInstanceOf(SignatureError);
  });

  it("installs a package signed by a trusted-on-first-use key", async () => {
    const { signed, key } = await fixture();
    const rec = await client(signed, { fetchSigningKeys: async () => ({ keys: [key] }) }).downloads.download("L1");
    expect(rec.signature_ok).toBe(true);
  });

  it("installs a package signed by a build-pinned key with no network", async () => {
    const { signed, key } = await fixture();
    const c = client(signed, { pinnedKeys: { [key.key_id]: key.public_key_hex } });
    expect((await c.downloads.download("L1")).signature_ok).toBe(true);
  });

  it("records signature failures in diagnostics", async () => {
    const { unsigned } = await fixture();
    const c = client(unsigned);
    await c.keyPinningRecorded;
    await expect(c.downloads.download("L1")).rejects.toBeInstanceOf(SignatureError);
    await new Promise((r) => setTimeout(r, 0));
    expect((await c.sync.diagnostics.get()).signatureFailures).toBe(1);
  });
});

describe("trustedKeyResolver (trust on first use)", () => {
  it("remembers a key and refuses a later change for the same key id", async () => {
    const store = new MemoryStore();
    const a = await fixture("k1");
    const b = await fixture("k1"); // same key id, different key
    expect(await trustedKeyResolver({ store, configured: {}, fetchKeys: async () => ({ keys: [a.key] }) })("k1")).not.toBeNull();
    expect(await store.get(STORES.prefs, "offline_signing_keys")).toEqual({ k1: a.key.public_key_hex });

    // A new page load where the server now answers with a different key for k1: the remembered key
    // is still used (no fetch for a known id), so b's package fails to verify.
    const c = createOfflineClient({
      store,
      fetchPackage: async () => b.signed,
      postBatch: async (cursor) => ({ cursor, results: [] }),
      pinnedKeys: {},
      fetchSigningKeys: async () => ({ keys: [b.key] }),
    });
    await expect(c.downloads.download("L1")).rejects.toBeInstanceOf(SignatureError);
    expect(await store.get(STORES.prefs, "offline_signing_keys")).toEqual({ k1: a.key.public_key_hex });
  });

  it("works offline with remembered keys (a failed fetch is not fatal)", async () => {
    const store = new MemoryStore();
    expect(await trustedKeyResolver({ store, configured: {}, fetchKeys: async () => Promise.reject(new Error("offline")) })("k1")).toBeNull();
  });
});

describe("key-pinning diagnostic", () => {
  it("flags a production build without pinned keys", async () => {
    expect(keyPinningDiagnostic({ configured: {}, nodeEnv: "production" })?.code).toBe("OFFLINE_SIGNING_KEYS_NOT_PINNED");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    try {
      const { signed } = await fixture();
      const c = client(signed, { nodeEnv: "production" });
      expect(c.keyPinning?.code).toBe("OFFLINE_SIGNING_KEYS_NOT_PINNED");
      expect(warn).toHaveBeenCalledWith(expect.stringContaining("OFFLINE_SIGNING_KEYS_NOT_PINNED"));
      await c.keyPinningRecorded;
      expect((await c.sync.diagnostics.get()).signingKeysPinned).toBe(false);
    } finally {
      warn.mockRestore();
    }
  });

  it("does not flag a production build with pinned keys, or a development build", async () => {
    expect(keyPinningDiagnostic({ configured: { k1: "aa" }, nodeEnv: "production" })).toBeNull();
    expect(keyPinningDiagnostic({ configured: {}, nodeEnv: "development" })).toBeNull();
    const { signed, key } = await fixture();
    const c = client(signed, { nodeEnv: "production", pinnedKeys: { [key.key_id]: key.public_key_hex } });
    expect(c.keyPinning).toBeNull();
    await c.keyPinningRecorded;
    expect((await c.sync.diagnostics.get()).signingKeysPinned).toBe(true);
  });
});
