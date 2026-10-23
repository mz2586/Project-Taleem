// Ed25519 package signature verification (Phase 6.2C-1) — client side.
//
// Verifies that an offline package manifest was signed by a pinned server key. The signed message
// is the canonicalization-free `signing_payload` the backend produces (offline_package.py):
// `${package_id}\n${version}\n${content_hash}`. The client holds ONLY the public key; the private
// seed never leaves the server. No child data.
//
// Two verifiers, ONE is chosen per device and never switched on a failed verification:
//   - "webcrypto": `crypto.subtle` with { name: "Ed25519" } (Chromium >= 137, Safari 17, Firefox 129).
//   - "noble":     `@noble/ed25519` (audited, MIT), used ONLY where WebCrypto Ed25519 is missing or
//                  broken (older Android WebViews). Loaded lazily, so devices with WebCrypto Ed25519
//                  never download it.
// The choice is made once by `detectSignatureVerifier` (a known-answer test on RFC 8032 TEST 1) and
// is baked into the key object `importPublicKey` returns: a CryptoKey verifies via WebCrypto, a
// `NobleEd25519Key` via noble. A WebCrypto verification that fails — or throws — is a failure; it is
// never retried on the other path. Verification stays mandatory and fail closed on both.
//
// Strictness parity: before either verifier runs, the same encoding checks apply to every key and
// signature (`publicKeyBytes`, `signatureBytes`): strict hex, exact lengths, canonical point
// encodings (y < p), no small-order public key, and canonical S (S < L, no malleability). See
// OFFLINE_SECURITY_REVIEW.md §8.2.

import type { PackageManifest } from "./types";

export type SignatureVerifier = "webcrypto" | "noble";

/** A raw public key for the fallback verifier (what `importPublicKey` returns on the noble path). */
export interface NobleEd25519Key {
  readonly kind: "noble-ed25519";
  readonly bytes: Uint8Array;
}

/** What a KeyResolver hands back: a WebCrypto key, or a fallback key. */
export type VerifyKey = CryptoKey | NobleEd25519Key;

export function isNobleKey(key: VerifyKey): key is NobleEd25519Key {
  return (key as Partial<NobleEd25519Key>).kind === "noble-ed25519";
}

export function hexToBytes(hex: string): Uint8Array<ArrayBuffer> {
  if (hex.length % 2 !== 0) throw new Error("odd-length hex");
  if (!/^[0-9a-fA-F]*$/.test(hex)) throw new Error("non-hex character");
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

// --- encoding checks shared by both verifiers ------------------------------------------------

// Byte comparisons only: a BigInt literal in this always-loaded module would be a syntax error on
// the oldest browsers the app still renders on (Next.js targets Chrome 64), breaking the page.

// The group order L = 2^252 + 27742317777372353535851937790883648493, little-endian.
const L_LE = [
  0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2, 0xde, 0xf9, 0xde, 0x14,
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x10,
];

// S (32 bytes, little-endian) < L: compare from the most significant byte down.
function scalarBelowOrder(s: Uint8Array): boolean {
  for (let i = 31; i >= 0; i--) {
    const a = s[i] ?? 0;
    const b = L_LE[i] ?? 0;
    if (a !== b) return a < b;
  }
  return false; // S == L
}

// A 32-byte point encoding's y (sign bit of x cleared) is reduced mod p = 2^255 - 19. The only
// unreduced values are p .. 2^255 - 1: bytes ed..ff, ff x 30, 7f (sign bit ignored).
function canonicalPoint(enc: Uint8Array): boolean {
  if (((enc[31] ?? 0) & 0x7f) !== 0x7f) return true;
  for (let i = 30; i >= 1; i--) if (enc[i] !== 0xff) return true;
  return (enc[0] ?? 0) < 0xed;
}

// Every canonical encoding of a point of small order (orders 1, 2, 4, 8), plus the two x = 0
// encodings with the sign bit set. A small-order public key makes "valid" signatures trivial to
// forge, so it is refused at import on both paths. (Non-canonical variants fail `canonicalPoint`.)
const SMALL_ORDER_KEYS = new Set([
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
]);

/** A 32-byte, canonically encoded, not-small-order Ed25519 public key; throws otherwise. */
export function publicKeyBytes(publicKeyHex: string): Uint8Array<ArrayBuffer> {
  const bytes = hexToBytes(publicKeyHex);
  if (bytes.length !== 32) throw new Error("Ed25519 public key must be 32 bytes");
  if (!canonicalPoint(bytes)) throw new Error("non-canonical public key encoding");
  if (SMALL_ORDER_KEYS.has(publicKeyHex.toLowerCase())) throw new Error("small-order public key");
  return bytes;
}

/** A 64-byte signature with a canonical R encoding and S < L; throws otherwise. */
export function signatureBytes(signatureHex: string): Uint8Array<ArrayBuffer> {
  const sig = hexToBytes(signatureHex);
  if (sig.length !== 64) throw new Error("Ed25519 signature must be 64 bytes");
  if (!canonicalPoint(sig.subarray(0, 32))) throw new Error("non-canonical R");
  if (!scalarBelowOrder(sig.subarray(32, 64))) throw new Error("non-canonical S");
  return sig;
}

// --- verifier selection -----------------------------------------------------------------------

// RFC 8032 §7.1 TEST 1 (empty message). The probe needs the good signature to verify AND a
// one-bit-flipped copy to fail, so a stub that answers `true` to everything is not "available".
const PROBE = {
  publicKeyHex: "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
  signatureHex:
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
};

const probes = new WeakMap<object, Promise<SignatureVerifier>>();

function defaultSubtle(): SubtleCrypto | undefined {
  return globalThis.crypto?.subtle;
}

async function probe(subtle: SubtleCrypto): Promise<SignatureVerifier> {
  try {
    const key = await subtle.importKey("raw", hexToBytes(PROBE.publicKeyHex), { name: "Ed25519" }, false, ["verify"]);
    const good = hexToBytes(PROBE.signatureHex);
    const bad = hexToBytes(PROBE.signatureHex);
    bad[0] = (bad[0] ?? 0) ^ 0x01;
    const empty = new Uint8Array(0);
    const accepts = await subtle.verify({ name: "Ed25519" }, key, good, empty);
    const rejects = !(await subtle.verify({ name: "Ed25519" }, key, bad, empty));
    return accepts === true && rejects ? "webcrypto" : "noble";
  } catch {
    return "noble"; // NotSupportedError on browsers without WebCrypto Ed25519
  }
}

/** Which verifier this device uses. Probed once per SubtleCrypto and cached. null = no WebCrypto. */
export function detectSignatureVerifier(subtle: SubtleCrypto | null | undefined = defaultSubtle()): Promise<SignatureVerifier> {
  if (!subtle) return Promise.resolve("noble");
  let entry = probes.get(subtle);
  if (!entry) {
    entry = probe(subtle);
    probes.set(subtle, entry);
  }
  return entry;
}

let fallback: Promise<typeof import("./ed25519Fallback")> | null = null;

function loadFallback(): Promise<typeof import("./ed25519Fallback")> {
  fallback ??= import("./ed25519Fallback").catch((e: unknown) => {
    fallback = null; // a failed chunk load (offline) may succeed later; this verification fails
    throw e;
  });
  return fallback;
}

// --- public API -------------------------------------------------------------------------------

// The exact bytes the server signs (binds pointer + version + content hash; downgrade-resistant).
export function signingMessage(
  packageId: string,
  version: string,
  contentHash: string,
): Uint8Array<ArrayBuffer> {
  const buf = new TextEncoder().encode(`${packageId}\n${version}\n${contentHash}`);
  return new Uint8Array(buf); // normalize to an ArrayBuffer-backed view for WebCrypto typing
}

// Import a raw 32-byte Ed25519 public key (hex) as a verify-only key for this device's verifier.
// Throws on a malformed key (both paths), and on the WebCrypto path if the import itself fails.
export async function importPublicKey(
  publicKeyHex: string,
  subtle: SubtleCrypto | undefined = defaultSubtle(),
): Promise<VerifyKey> {
  const bytes = publicKeyBytes(publicKeyHex);
  if (subtle && (await detectSignatureVerifier(subtle)) === "webcrypto") {
    return subtle.importKey("raw", bytes, { name: "Ed25519" }, false, ["verify"]);
  }
  return Object.freeze({ kind: "noble-ed25519" as const, bytes });
}

// Verify a manifest's signature against an imported public key. False on any malformity.
export async function verifyManifestSignature(
  manifest: PackageManifest,
  publicKey: VerifyKey,
  subtle: SubtleCrypto | undefined = defaultSubtle(),
): Promise<boolean> {
  if (!manifest.signature) return false;
  try {
    const sig = signatureBytes(manifest.signature);
    const msg = signingMessage(manifest.package_id, manifest.version, manifest.content_hash);
    if (isNobleKey(publicKey)) {
      return await (await loadFallback()).nobleVerify(sig, msg, publicKey.bytes);
    }
    if (!subtle) return false;
    return (await subtle.verify({ name: "Ed25519" }, publicKey, sig, msg)) === true;
  } catch {
    return false; // includes a WebCrypto error: never retried with the fallback
  }
}

// A resolver maps a signing_key_id to a pinned public key (or null if unknown/unpinned).
export type KeyResolver = (keyId: string) => Promise<VerifyKey | null>;

// Build a resolver from a pinned map of { key_id -> public_key_hex } (app-bundled keys).
export function pinnedKeyResolver(
  pinned: Record<string, string>,
  subtle: SubtleCrypto | undefined = defaultSubtle(),
): KeyResolver {
  const cache = new Map<string, Promise<VerifyKey>>();
  return async (keyId: string) => {
    const hex = pinned[keyId];
    if (!hex) return null;
    let entry = cache.get(keyId);
    if (!entry) {
      entry = importPublicKey(hex, subtle);
      cache.set(keyId, entry);
    }
    return entry;
  };
}
