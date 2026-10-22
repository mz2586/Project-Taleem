// Offline package signing keys — where the client's trusted Ed25519 public keys come from.
//
// Strongest first:
//   1. NEXT_PUBLIC_OFFLINE_SIGNING_KEYS — {key_id: public_key_hex} bundled into the app at build
//      time. This is real pinning and the preferred configuration for every deployment.
//   2. Keys this device trusted before (trust on first use, kept in the `prefs` store).
//   3. GET /v1/offline/signing-keys, only for a key_id this device has never seen.
// A server answer that gives a DIFFERENT key for a key_id already trusted is refused: that key_id
// is dropped (unless the build pinned it), so its packages fail verification rather than silently
// trusting the new key. (2)+(3) are weaker than (1) — the first fetch is trusted — so a production
// build without (1) is flagged: a console warning and `signingKeysPinned: false` in diagnostics.

import type { KVStore } from "./kv";
import { STORES } from "./kv";
import { importPublicKey } from "./signature";
import type { KeyResolver } from "./signature";
import type { SigningKey } from "./types";

export interface KeyMerge {
  keys: Record<string, string>;
  /** key_ids the server tried to change: refused. */
  conflicts: string[];
  /** What to remember on this device afterwards. */
  remember: Record<string, string>;
}

export function mergeSigningKeys(input: {
  configured: Record<string, string>;
  remembered: Record<string, string>;
  fetched: readonly SigningKey[];
}): KeyMerge {
  const keys: Record<string, string> = { ...input.remembered, ...input.configured };
  const remember: Record<string, string> = { ...input.remembered };
  const conflicts: string[] = [];
  for (const k of input.fetched) {
    if (k.algorithm && k.algorithm !== "Ed25519") continue;
    const hex = k.public_key_hex.toLowerCase();
    const known = keys[k.key_id];
    if (known === undefined) {
      keys[k.key_id] = hex;
      remember[k.key_id] = hex;
    } else if (known.toLowerCase() !== hex) {
      conflicts.push(k.key_id);
    }
  }
  for (const id of conflicts) if (!(id in input.configured)) delete keys[id];
  return { keys, conflicts, remember };
}

/** Parse NEXT_PUBLIC_OFFLINE_SIGNING_KEYS defensively ({} when absent or malformed). */
export function configuredSigningKeys(raw: string | undefined = process.env.NEXT_PUBLIC_OFFLINE_SIGNING_KEYS): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter((e): e is [string, string] => typeof e[1] === "string"),
    );
  } catch {
    return {};
  }
}

export interface KeyPinningDiagnostic {
  code: "OFFLINE_SIGNING_KEYS_NOT_PINNED";
  message: string;
}

/** A production build with no build-time keys relies on trust-on-first-use: flag it. */
export function keyPinningDiagnostic(input: {
  configured: Record<string, string>;
  nodeEnv: string | undefined;
}): KeyPinningDiagnostic | null {
  if (input.nodeEnv !== "production" || Object.keys(input.configured).length > 0) return null;
  return {
    code: "OFFLINE_SIGNING_KEYS_NOT_PINNED",
    message:
      "Offline package signing keys are not pinned (NEXT_PUBLIC_OFFLINE_SIGNING_KEYS is unset). " +
      "Packages are still verified, but the first key seen from the server is trusted on first use.",
  };
}

const KEYS_PREF = "offline_signing_keys";

/**
 * A KeyResolver over configured + remembered + fetched keys. Fetches at most once per resolver
 * (per page load) and only when asked for a key_id it does not already trust.
 */
export function trustedKeyResolver(deps: {
  store: KVStore;
  configured: Record<string, string>;
  fetchKeys?: () => Promise<{ keys: SigningKey[] }>;
  subtle?: SubtleCrypto;
}): KeyResolver {
  let fetched: Promise<SigningKey[]> | null = null;
  const imported = new Map<string, Promise<CryptoKey>>();

  async function current(keyId: string): Promise<Record<string, string>> {
    const remembered = (await deps.store.get<Record<string, string>>(STORES.prefs, KEYS_PREF)) ?? {};
    const known = { ...remembered, ...deps.configured };
    let fresh: SigningKey[] = [];
    if (!(keyId in known) && deps.fetchKeys) {
      fetched ??= deps.fetchKeys().then(
        (r) => r.keys,
        () => [], // offline or unavailable: verify with what this device already trusts
      );
      fresh = await fetched;
    }
    const merged = mergeSigningKeys({ configured: deps.configured, remembered, fetched: fresh });
    if (fresh.length > 0) await deps.store.put(STORES.prefs, KEYS_PREF, merged.remember);
    return merged.keys;
  }

  return async (keyId: string) => {
    if (!keyId) return null;
    const hex = (await current(keyId))[keyId];
    if (!hex) return null;
    const cacheKey = `${keyId}:${hex}`;
    let entry = imported.get(cacheKey);
    if (!entry) {
      entry = importPublicKey(hex, deps.subtle);
      imported.set(cacheKey, entry);
    }
    try {
      return await entry;
    } catch {
      imported.delete(cacheKey);
      return null;
    }
  };
}
