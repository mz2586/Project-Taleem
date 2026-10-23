// The @noble/ed25519 fallback verifier: chosen only where WebCrypto Ed25519 is unavailable, as strict
// as the WebCrypto path, and never used to second-guess a WebCrypto verification failure.
import "fake-indexeddb/auto";

import { Point, verifyAsync } from "@noble/ed25519";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createOfflineClient } from "..";
import { nobleVerify } from "../ed25519Fallback";
import { IdbStore, STORES } from "../kv";
import { SignatureError } from "../packages";
import { contentHash } from "../sha256";
import {
  detectSignatureVerifier,
  hexToBytes,
  importPublicKey,
  isNobleKey,
  publicKeyBytes,
  signatureBytes,
  signingMessage,
  verifyManifestSignature,
} from "../signature";
import type { VerifyKey } from "../signature";
import type { OfflineContent, OfflinePackage, PackageManifest } from "../types";

// Pass-through spy: proves when the fallback library is (and is not) consulted.
vi.mock("@noble/ed25519", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@noble/ed25519")>();
  return { ...mod, verifyAsync: vi.fn(mod.verifyAsync) };
});

const realSubtle = globalThis.crypto.subtle;

function isEd25519(alg: unknown): boolean {
  return (typeof alg === "string" ? alg : (alg as { name?: string } | null)?.name) === "Ed25519";
}

// WebCrypto as on Chromium < 137: SHA digests work, Ed25519 is "NotSupportedError".
function subtleWithoutEd25519(): SubtleCrypto {
  const notSupported = () => Promise.reject(new DOMException("Unrecognized name.", "NotSupportedError"));
  const call = (fn: keyof SubtleCrypto, args: unknown[]) =>
    (realSubtle[fn] as (...a: unknown[]) => Promise<unknown>).apply(realSubtle, args);
  return {
    digest: (...a: unknown[]) => call("digest", a),
    importKey: (...a: unknown[]) => (isEd25519(a[2]) ? notSupported() : call("importKey", a)),
    verify: (...a: unknown[]) => (isEd25519(a[0]) ? notSupported() : call("verify", a)),
  } as unknown as SubtleCrypto;
}

// A fresh wrapper over the real WebCrypto (a new object, so it gets its own probe).
function realSubtleWrapper(overrides: Partial<Record<"verify" | "importKey", (...a: unknown[]) => Promise<unknown>>> = {}): SubtleCrypto {
  const call = (fn: keyof SubtleCrypto, args: unknown[]) =>
    (realSubtle[fn] as (...a: unknown[]) => Promise<unknown>).apply(realSubtle, args);
  return {
    digest: (...a: unknown[]) => call("digest", a),
    importKey: overrides.importKey ?? ((...a: unknown[]) => call("importKey", a)),
    verify: overrides.verify ?? ((...a: unknown[]) => call("verify", a)),
  } as unknown as SubtleCrypto;
}

function hex(bytes: ArrayBuffer | Uint8Array): string {
  return Array.from(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// RFC 8032 §7.1 TEST 1–3.
const RFC8032 = [
  {
    name: "TEST 1",
    publicKey: "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
    message: "",
    signature:
      "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
  },
  {
    name: "TEST 2",
    publicKey: "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
    message: "72",
    signature:
      "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
  },
  {
    name: "TEST 3",
    publicKey: "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
    message: "af82",
    signature:
      "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
  },
];

// The backend interop vector (see signature.test.ts).
const BACKEND = {
  keyId: "dev-ed25519-1",
  publicKeyHex: "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8",
  manifest: {
    package_id: "pkg/math-g4-intro-fractions",
    lesson_id: "L-frac",
    objective_code: "MATH-G4-FR-01",
    version: "1a2b3c4d5e6f",
    content_hash: "deadbeef",
    assets: [],
    total_bytes: 10,
    created_at_ms: 0,
    signature:
      "416f96e195fdd7f9bdb85229b8ad2c5b25d4dec068119fcba6d1006eaecb9671" +
      "841d4cf2f17a3f691f92b539ccf4ea147b076380b73194d486a7cf76ad6fae06",
    signing_key_id: "dev-ed25519-1",
  } satisfies PackageManifest,
};

const L = 2n ** 252n + 27742317777372353535851937790883648493n;

// S + L: the same signature with a non-canonical (malleated) S.
function malleate(signatureHex: string): string {
  const sig = hexToBytes(signatureHex);
  let s = 0n;
  for (let i = 63; i >= 32; i--) s = (s << 8n) + BigInt(sig[i] ?? 0);
  s += L;
  for (let i = 32; i < 64; i++) {
    sig[i] = Number(s & 0xffn);
    s >>= 8n;
  }
  return hex(sig);
}

const flipBit = (h: string, byte: number): string => {
  const b = hexToBytes(h);
  b[byte] = (b[byte] ?? 0) ^ 0x01;
  return hex(b);
};

const PATHS = [
  { verifier: "webcrypto" as const, subtle: () => realSubtleWrapper() },
  { verifier: "noble" as const, subtle: () => subtleWithoutEd25519() },
];

beforeEach(() => {
  vi.mocked(verifyAsync).mockClear();
});

describe("verifier selection (probe)", () => {
  it("selects WebCrypto where it supports Ed25519", async () => {
    expect(await detectSignatureVerifier(realSubtleWrapper())).toBe("webcrypto");
  });

  it("selects noble where WebCrypto Ed25519 is unavailable, or WebCrypto is missing", async () => {
    expect(await detectSignatureVerifier(subtleWithoutEd25519())).toBe("noble");
    expect(await detectSignatureVerifier(null)).toBe("noble");
  });

  it("selects noble when WebCrypto answers the known-answer test wrongly", async () => {
    expect(await detectSignatureVerifier(realSubtleWrapper({ verify: async () => true }))).toBe("noble");
    expect(await detectSignatureVerifier(realSubtleWrapper({ verify: async () => false }))).toBe("noble");
  });

  it("probes once per WebCrypto instance and caches the answer", async () => {
    const importKey = vi.fn((...a: unknown[]) => (realSubtle.importKey as (...x: unknown[]) => Promise<unknown>).apply(realSubtle, a));
    const subtle = realSubtleWrapper({ importKey });
    await detectSignatureVerifier(subtle);
    await detectSignatureVerifier(subtle);
    expect(importKey).toHaveBeenCalledTimes(1);
  });

  it("importPublicKey returns a fallback key only on the noble path", async () => {
    expect(isNobleKey(await importPublicKey(BACKEND.publicKeyHex, realSubtleWrapper()))).toBe(false);
    expect(isNobleKey(await importPublicKey(BACKEND.publicKeyHex, subtleWithoutEd25519()))).toBe(true);
  });
});

describe("RFC 8032 test vectors", () => {
  for (const v of RFC8032) {
    it(`${v.name} verifies on the noble path`, async () => {
      expect(await nobleVerify(signatureBytes(v.signature), hexToBytes(v.message), publicKeyBytes(v.publicKey))).toBe(true);
      expect(verifyAsync).toHaveBeenCalled();
    });

    it(`${v.name} verifies on the WebCrypto path (same vector, same answer)`, async () => {
      const key = await realSubtle.importKey("raw", publicKeyBytes(v.publicKey), { name: "Ed25519" }, false, ["verify"]);
      expect(await realSubtle.verify({ name: "Ed25519" }, key, signatureBytes(v.signature), hexToBytes(v.message))).toBe(true);
    });

    it(`${v.name} with a tampered message or signature fails on the noble path`, async () => {
      const msg = v.message === "" ? "00" : flipBit(v.message, 0);
      expect(await nobleVerify(signatureBytes(v.signature), hexToBytes(msg), publicKeyBytes(v.publicKey))).toBe(false);
      expect(await nobleVerify(signatureBytes(flipBit(v.signature, 40)), hexToBytes(v.message), publicKeyBytes(v.publicKey))).toBe(false);
    });
  }
});

describe.each(PATHS)("strictness on the $verifier path", ({ verifier, subtle: makeSubtle }) => {
  async function check(manifest: Partial<PackageManifest>, keyHex = BACKEND.publicKeyHex): Promise<boolean> {
    const subtle = makeSubtle();
    let key: VerifyKey;
    try {
      key = await importPublicKey(keyHex, subtle);
    } catch {
      return false; // a malformed key never becomes a usable key
    }
    expect(isNobleKey(key)).toBe(verifier === "noble");
    return verifyManifestSignature({ ...BACKEND.manifest, ...manifest }, key, subtle);
  }

  it("accepts the backend's signature", async () => {
    expect(await check({})).toBe(true);
    expect(vi.mocked(verifyAsync).mock.calls.length > 0).toBe(verifier === "noble");
  });

  it("rejects a tampered message (content hash, version, package id)", async () => {
    expect(await check({ content_hash: "deadbee0" })).toBe(false);
    expect(await check({ version: "ffffffffffff" })).toBe(false);
    expect(await check({ package_id: "pkg/other" })).toBe(false);
  });

  it("rejects a tampered signature (R or S bit flipped, all zeros)", async () => {
    expect(await check({ signature: flipBit(BACKEND.manifest.signature, 1) })).toBe(false);
    expect(await check({ signature: flipBit(BACKEND.manifest.signature, 40) })).toBe(false);
    expect(await check({ signature: "00".repeat(64) })).toBe(false);
  });

  it("rejects a different (valid) key", async () => {
    expect(await check({}, RFC8032[1]!.publicKey)).toBe(false);
  });

  it("rejects wrong-length keys and signatures, and non-hex input", async () => {
    expect(await check({}, BACKEND.publicKeyHex.slice(0, 62))).toBe(false);
    expect(await check({}, `${BACKEND.publicKeyHex}00`)).toBe(false);
    expect(await check({}, `${BACKEND.publicKeyHex.slice(0, 62)}zz`)).toBe(false);
    expect(await check({ signature: BACKEND.manifest.signature.slice(0, 126) })).toBe(false);
    expect(await check({ signature: `${BACKEND.manifest.signature}00` })).toBe(false);
    expect(await check({ signature: `${BACKEND.manifest.signature.slice(0, 126)}g0` })).toBe(false);
  });

  it("rejects a non-canonical S (S + L, signature malleability)", async () => {
    expect(await check({ signature: malleate(BACKEND.manifest.signature) })).toBe(false);
  });

  it("rejects a non-canonical public key encoding (y >= p)", async () => {
    // y = p = 2^255 - 19, which is y = 0 unreduced.
    expect(await check({}, `ed${"ff".repeat(30)}7f`)).toBe(false);
  });

  it("rejects small-order public keys (trivial forgeries)", async () => {
    const identity = `01${"00".repeat(31)}`;
    // R = identity, S = 0 "verifies" under any message for the identity key in a lax verifier.
    expect(await check({ signature: `${identity}${"00".repeat(32)}` }, identity)).toBe(false);
    for (const k of SMALL_ORDER) expect(await check({}, k)).toBe(false);
  });
});

const SMALL_ORDER = [
  "0100000000000000000000000000000000000000000000000000000000000000",
  "0100000000000000000000000000000000000000000000000000000000000080",
  "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
  "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "0000000000000000000000000000000000000000000000000000000000000000",
  "0000000000000000000000000000000000000000000000000000000000000080",
  "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
  "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc85",
  "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
  "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac03fa",
];

describe("encoding checks at the boundaries (shared by both paths)", () => {
  function le(n: bigint): string {
    const out = new Uint8Array(32);
    for (let i = 0; i < 32; i++) {
      out[i] = Number(n & 0xffn);
      n >>= 8n;
    }
    return hex(out);
  }
  const P = 2n ** 255n - 19n;
  const R = RFC8032[0]!.signature.slice(0, 64);

  it("S = L - 1 passes the encoding check; S = L and S = 2^256 - 1 do not", () => {
    expect(() => signatureBytes(R + le(L - 1n))).not.toThrow();
    expect(() => signatureBytes(R + le(L))).toThrow("non-canonical S");
    expect(() => signatureBytes(R + "ff".repeat(32))).toThrow("non-canonical S");
  });

  it("R or A with y = p - 1 is canonical; y = p and y = 2^255 - 1 are not (sign bit ignored)", () => {
    const S = le(1n);
    expect(() => signatureBytes(le(P - 1n) + S)).not.toThrow();
    expect(() => signatureBytes(le(P) + S)).toThrow("non-canonical R");
    expect(() => signatureBytes(le(2n ** 255n - 1n) + S)).toThrow("non-canonical R");
    const pSigned = hexToBytes(le(P));
    pSigned[31] = (pSigned[31] ?? 0) | 0x80;
    expect(() => publicKeyBytes(hex(pSigned))).toThrow("non-canonical public key");
  });
});

describe("the small-order blocklist", () => {
  it("lists only small-order points or invalid x = 0 encodings (checked against noble)", () => {
    for (const k of SMALL_ORDER) {
      let smallOrder: boolean;
      try {
        smallOrder = Point.fromHex(k, true).isSmallOrder();
      } catch {
        smallOrder = true; // not a point at all
      }
      expect(smallOrder, k).toBe(true);
      expect(() => publicKeyBytes(k)).toThrow();
    }
  });

  it("noble's strict mode independently refuses the identity-key forgery", async () => {
    const identity = hexToBytes(`01${"00".repeat(31)}`);
    const sig = hexToBytes(`01${"00".repeat(63)}`);
    expect(await nobleVerify(sig, new Uint8Array([1, 2, 3]), identity)).toBe(false);
  });
});

describe("no fallback after a WebCrypto verification failure", () => {
  it("a signature WebCrypto rejects is not re-checked with noble", async () => {
    const subtle = realSubtleWrapper();
    const key = await importPublicKey(BACKEND.publicKeyHex, subtle);
    expect(await verifyManifestSignature({ ...BACKEND.manifest, content_hash: "deadbee0" }, key, subtle)).toBe(false);
    expect(verifyAsync).not.toHaveBeenCalled();
  });

  it("a WebCrypto verify that throws is a failure, not a reason to try noble", async () => {
    // Ed25519 is supported (the probe passes), but verifying a package throws.
    const subtle = realSubtleWrapper({
      verify: (...a: unknown[]) =>
        (a[3] as Uint8Array).byteLength === 0
          ? (realSubtle.verify as (...x: unknown[]) => Promise<unknown>).apply(realSubtle, a)
          : Promise.reject(new DOMException("boom", "OperationError")),
    });
    expect(await detectSignatureVerifier(subtle)).toBe("webcrypto");
    const key = await importPublicKey(BACKEND.publicKeyHex, subtle);
    expect(await verifyManifestSignature(BACKEND.manifest, key, subtle)).toBe(false);
    expect(verifyAsync).not.toHaveBeenCalled();
  });

  it("a CryptoKey is never verified by noble, whatever the WebCrypto answer", async () => {
    const key = await importPublicKey(BACKEND.publicKeyHex, realSubtleWrapper());
    expect(await verifyManifestSignature(BACKEND.manifest, key, realSubtleWrapper({ verify: async () => false }))).toBe(false);
    expect(verifyAsync).not.toHaveBeenCalled();
  });
});

describe("end to end: install with the fallback forced (IndexedDB)", () => {
  const content: OfflineContent = {
    lesson_id: "L-fb",
    objective_code: "O1",
    title: { ur: "کسر", en: "Fractions" },
    explanation: { en: "E" },
    worked_example_steps: [],
    practice_items: [],
    homework_items: [],
    assessment_formative: [],
    summative_mentor_mediated: true,
  };

  async function signedFixture(): Promise<{ pkg: OfflinePackage; publicKeyHex: string }> {
    const pair = (await realSubtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
    const hash = await contentHash(content);
    const manifest: PackageManifest = {
      package_id: "pkg/L-fb",
      lesson_id: "L-fb",
      objective_code: "O1",
      version: hash.slice(0, 12),
      content_hash: hash,
      assets: [],
      total_bytes: 10,
      created_at_ms: 0,
      signing_key_id: "k-fb",
    };
    const sig = await realSubtle.sign({ name: "Ed25519" }, pair.privateKey, signingMessage(manifest.package_id, manifest.version, hash));
    return {
      pkg: { manifest: { ...manifest, signature: hex(sig) }, content },
      publicKeyHex: hex(await realSubtle.exportKey("raw", pair.publicKey)),
    };
  }

  async function freshStore(): Promise<IdbStore> {
    const store = new IdbStore(indexedDB);
    for (const s of Object.values(STORES)) await store.clear(s);
    return store;
  }

  function client(store: IdbStore, pkg: OfflinePackage, publicKeyHex: string, subtle: SubtleCrypto) {
    return createOfflineClient({
      store,
      fetchPackage: async () => pkg,
      postBatch: async (cursor) => ({ cursor, results: [] }),
      pinnedKeys: { "k-fb": publicKeyHex },
      subtle,
    });
  }

  it("installs a signed package via noble and records the verifier in diagnostics", async () => {
    const store = await freshStore();
    const { pkg, publicKeyHex } = await signedFixture();
    const c = client(store, pkg, publicKeyHex, subtleWithoutEd25519());
    const rec = await c.downloads.download("L-fb");
    expect(rec.signature_ok).toBe(true);
    expect(verifyAsync).toHaveBeenCalledTimes(1);
    expect((await c.downloads.getLesson("L-fb"))?.title.ur).toBe("کسر");
    await c.signatureVerifierRecorded;
    expect((await c.sync.diagnostics.get()).signatureVerifier).toBe("noble");
  });

  it("refuses a tampered package via noble and installs nothing", async () => {
    const store = await freshStore();
    const { pkg, publicKeyHex } = await signedFixture();
    const tampered: OfflinePackage = { ...pkg, manifest: { ...pkg.manifest, signature: flipBit(pkg.manifest.signature!, 3) } };
    const c = client(store, tampered, publicKeyHex, subtleWithoutEd25519());
    await expect(c.downloads.download("L-fb")).rejects.toBeInstanceOf(SignatureError);
    expect(await c.downloads.installed("L-fb")).toBeUndefined();
    expect(await store.get(STORES.content, "L-fb")).toBeUndefined();
  });

  it("uses WebCrypto (and never loads noble) where WebCrypto Ed25519 exists", async () => {
    const store = await freshStore();
    const { pkg, publicKeyHex } = await signedFixture();
    const c = client(store, pkg, publicKeyHex, realSubtleWrapper());
    expect((await c.downloads.download("L-fb")).signature_ok).toBe(true);
    expect(verifyAsync).not.toHaveBeenCalled();
    await c.signatureVerifierRecorded;
    expect((await c.sync.diagnostics.get()).signatureVerifier).toBe("webcrypto");
  });
});
