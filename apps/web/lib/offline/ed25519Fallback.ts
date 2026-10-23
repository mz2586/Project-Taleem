// Fallback Ed25519 verifier — loaded ONLY (dynamic import from signature.ts) on devices whose
// WebCrypto has no Ed25519, e.g. Android WebViews before Chromium 137. Never used to re-check a
// signature WebCrypto rejected.
//
// @noble/ed25519 (pinned exactly in package.json; audited, zero dependencies, MIT). `verifyAsync`
// hashes with WebCrypto SHA-512 (`crypto.subtle.digest`, available everywhere WebCrypto is), so no
// second dependency. `zip215: false` selects the library's strict RFC 8032 / FIPS 186-5 branch:
// canonical A and R encodings, S < L, small-order public keys rejected, cofactored equation.
// signature.ts applies the same encoding checks to both paths before calling this.

import { verifyAsync } from "@noble/ed25519";

export async function nobleVerify(signature: Uint8Array, message: Uint8Array, publicKey: Uint8Array): Promise<boolean> {
  try {
    return (await verifyAsync(signature, message, publicKey, { zip215: false })) === true;
  } catch {
    return false;
  }
}
