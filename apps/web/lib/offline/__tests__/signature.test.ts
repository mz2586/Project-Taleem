import { describe, expect, it } from "vitest";

import {
  hexToBytes,
  importPublicKey,
  pinnedKeyResolver,
  signingMessage,
  verifyManifestSignature,
} from "../signature";
import type { PackageManifest } from "../types";

// Locked cross-language interop vector: this public key + signature were produced by the backend's
// pure-stdlib Ed25519 (services/core-api .../platform/ed25519.py, seed = bytes(range(32))). If the
// client verifier ever stops accepting server signatures, this test fails.
const VECTOR = {
  keyId: "dev-ed25519-1",
  publicKeyHex: "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8",
  packageId: "pkg/math-g4-intro-fractions",
  version: "1a2b3c4d5e6f",
  contentHash: "deadbeef",
  signatureHex:
    "416f96e195fdd7f9bdb85229b8ad2c5b25d4dec068119fcba6d1006eaecb9671" +
    "841d4cf2f17a3f691f92b539ccf4ea147b076380b73194d486a7cf76ad6fae06",
};

function vectorManifest(overrides: Partial<PackageManifest> = {}): PackageManifest {
  return {
    package_id: VECTOR.packageId,
    lesson_id: "L-frac",
    objective_code: "MATH-G4-FR-01",
    version: VECTOR.version,
    content_hash: VECTOR.contentHash,
    assets: [],
    total_bytes: 10,
    created_at_ms: 0,
    signature: VECTOR.signatureHex,
    signing_key_id: VECTOR.keyId,
    ...overrides,
  };
}

describe("signature verification", () => {
  it("hexToBytes round-trips a known signing message", () => {
    const msg = signingMessage(VECTOR.packageId, VECTOR.version, VECTOR.contentHash);
    expect(new TextDecoder().decode(msg)).toBe(
      `${VECTOR.packageId}\n${VECTOR.version}\n${VECTOR.contentHash}`,
    );
    expect(hexToBytes("00ff10").length).toBe(3);
  });

  it("verifies a signature produced by the backend (Python↔WebCrypto interop)", async () => {
    const key = await importPublicKey(VECTOR.publicKeyHex);
    expect(await verifyManifestSignature(vectorManifest(), key)).toBe(true);
  });

  it("rejects a tampered content_hash, version, or package_id (downgrade guard)", async () => {
    const key = await importPublicKey(VECTOR.publicKeyHex);
    expect(await verifyManifestSignature(vectorManifest({ content_hash: "deadbee0" }), key)).toBe(false);
    expect(await verifyManifestSignature(vectorManifest({ version: "ffffffffffff" }), key)).toBe(false);
    expect(await verifyManifestSignature(vectorManifest({ package_id: "pkg/other" }), key)).toBe(false);
  });

  it("rejects an absent signature", async () => {
    const key = await importPublicKey(VECTOR.publicKeyHex);
    expect(await verifyManifestSignature(vectorManifest({ signature: "" }), key)).toBe(false);
  });

  it("verifies a freshly generated WebCrypto keypair too", async () => {
    const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, [
      "sign",
      "verify",
    ])) as CryptoKeyPair;
    const msg = signingMessage("pkg/x", "v1", "hash");
    const sig = new Uint8Array(await crypto.subtle.sign({ name: "Ed25519" }, pair.privateKey, msg));
    const manifest = vectorManifest({
      package_id: "pkg/x",
      version: "v1",
      content_hash: "hash",
      signature: Array.from(sig)
        .map((b) => b.toString(16).padStart(2, "0"))
        .join(""),
    });
    expect(await verifyManifestSignature(manifest, pair.publicKey)).toBe(true);
  });

  it("pinnedKeyResolver resolves a pinned key and returns null for an unknown id", async () => {
    const resolve = pinnedKeyResolver({ [VECTOR.keyId]: VECTOR.publicKeyHex });
    expect(await resolve(VECTOR.keyId)).not.toBeNull();
    expect(await resolve("unknown")).toBeNull();
  });
});
