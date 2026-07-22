// Ed25519 package signature verification (Phase 6.2C-1) — client side.
//
// Verifies that an offline package manifest was signed by a pinned server key, using WebCrypto
// (`crypto.subtle` with { name: "Ed25519" }). The signed message is the canonicalization-free
// `signing_payload` the backend produces (offline_package.py): `${package_id}\n${version}\n${content_hash}`.
// The client holds ONLY the public key; the private seed never leaves the server. No child data.

import type { PackageManifest } from "./types";

export function hexToBytes(hex: string): Uint8Array<ArrayBuffer> {
  if (hex.length % 2 !== 0) throw new Error("odd-length hex");
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

// The exact bytes the server signs (binds pointer + version + content hash; downgrade-resistant).
export function signingMessage(
  packageId: string,
  version: string,
  contentHash: string,
): Uint8Array<ArrayBuffer> {
  const buf = new TextEncoder().encode(`${packageId}\n${version}\n${contentHash}`);
  return new Uint8Array(buf); // normalize to an ArrayBuffer-backed view for WebCrypto typing
}

// Import a raw 32-byte Ed25519 public key (hex) as a verify-only CryptoKey.
export async function importPublicKey(
  publicKeyHex: string,
  subtle: SubtleCrypto = globalThis.crypto.subtle,
): Promise<CryptoKey> {
  return subtle.importKey("raw", hexToBytes(publicKeyHex), { name: "Ed25519" }, false, ["verify"]);
}

// Verify a manifest's signature against an imported public key. False on any malformity.
export async function verifyManifestSignature(
  manifest: PackageManifest,
  publicKey: CryptoKey,
  subtle: SubtleCrypto = globalThis.crypto.subtle,
): Promise<boolean> {
  if (!manifest.signature) return false;
  try {
    const sig = hexToBytes(manifest.signature);
    const msg = signingMessage(manifest.package_id, manifest.version, manifest.content_hash);
    return await subtle.verify({ name: "Ed25519" }, publicKey, sig, msg);
  } catch {
    return false;
  }
}

// A resolver maps a signing_key_id to a pinned public CryptoKey (or null if unknown/unpinned).
export type KeyResolver = (keyId: string) => Promise<CryptoKey | null>;

// Build a resolver from a pinned map of { key_id -> public_key_hex } (app-bundled keys).
export function pinnedKeyResolver(
  pinned: Record<string, string>,
  subtle: SubtleCrypto = globalThis.crypto.subtle,
): KeyResolver {
  const cache = new Map<string, Promise<CryptoKey>>();
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
