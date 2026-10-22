// The offline lesson library — what /student/offline lists, and how a lesson gets onto the phone.
// The view model is pure and tested; the service below composes lib/offline's DownloadManager.
//
// Verification is not optional here. The app-wide offline client (lib/student/offlineClient.ts) was
// built with no pinned keys and `requireSignature` off, which means an unsigned package — or a
// signed one whose key the client cannot resolve — installs unverified (the 6.2A compatibility
// path). The library therefore builds its OWN DownloadManager over the same IndexedDB store with
// `requireSignature: true` and a key resolver, so a package that does not verify is refused and
// nothing is written. The server signs every package (Ed25519, TALEEM_OFFLINE_SIGNING_SEED).
//
// Where the public keys come from, strongest first:
//   1. NEXT_PUBLIC_OFFLINE_SIGNING_KEYS — keys bundled into the app at build time ({key_id: hex}).
//   2. Keys this device saw before (trust on first use, stored in the `prefs` store). A later
//      answer from the server that gives a DIFFERENT key for a known key_id is refused: that key_id
//      is dropped, so its packages fail verification instead of silently trusting the new key.
//   3. GET /v1/offline/signing-keys, for a key_id never seen before.
// (2) and (3) are weaker than real pinning — the first fetch is trusted — and that is called out in
// the report; setting (1) in a deployment closes it.

import type { MessageKey } from "../i18n/messages";
import type { KVStore } from "../offline/kv";
import { STORES } from "../offline/kv";
import { DownloadManager, IntegrityError, QuotaExceededError, SignatureError } from "../offline/packages";
import { pinnedKeyResolver } from "../offline/signature";
import type { OfflineContent, OfflinePackage, PackageManifest, SigningKey, StorageEstimate, StoredPackage } from "../offline/types";
import { pickLocalized } from "../i18n/content";
import { INSTRUCTION_LOCALE_PREFERENCE } from "./journey";
import { ApiError } from "./types";

// ---- signing keys (trust on first use, configured keys win) -------------------------------------

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
  // A key_id with a conflicting answer is not trusted at all, unless the build pinned it.
  for (const id of conflicts) if (!(id in input.configured)) delete keys[id];
  return { keys, conflicts, remember };
}

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

// ---- download failures ---------------------------------------------------------------------------

export type DownloadFailure = "signature" | "integrity" | "storage" | "offline" | "gone" | "error";

export function classifyDownloadError(error: unknown): DownloadFailure {
  if (error instanceof SignatureError) return "signature";
  if (error instanceof IntegrityError) return "integrity";
  if (error instanceof QuotaExceededError) return "storage";
  if (error instanceof ApiError) {
    if (error.status === 0) return "offline";
    if (error.status === 404) return "gone";
  }
  return "error";
}

export const DOWNLOAD_FAILURE_COPY: Record<DownloadFailure, MessageKey> = {
  signature: "student.offline.failed.signature",
  integrity: "student.offline.failed.integrity",
  storage: "student.offline.failed.storage",
  offline: "student.offline.failed.offline",
  gone: "student.offline.failed.gone",
  error: "student.offline.failed.error",
};

// ---- the library view model ------------------------------------------------------------------------

export type DownloadState =
  | { kind: "idle" }
  | { kind: "downloading"; fraction: number }
  | { kind: "failed"; reason: DownloadFailure };

export type EntryStatus =
  | { kind: "available" }
  | { kind: "downloading"; fraction: number }
  | { kind: "installed"; updateAvailable: boolean }
  | { kind: "failed"; reason: DownloadFailure; installed: boolean };

export interface LibraryEntry {
  lessonId: string;
  objectiveCode: string;
  /** The lesson title, when the content is on the device; null before download. */
  title: { text: string; locale: string } | null;
  bytes: number;
  status: EntryStatus;
}

export type LibraryModel =
  | { kind: "loading" }
  /** Nothing is published and nothing is on the phone — today's reality. */
  | { kind: "nothing-published" }
  | {
      kind: "list";
      entries: LibraryEntry[];
      /** The server list could not be read (offline): only what is on the phone is shown. */
      listUnavailable: boolean;
      installedBytes: number;
    };

export type ListRequest =
  | { status: "pending" }
  | { status: "ok"; manifests: PackageManifest[] }
  | { status: "error"; error: unknown };

export function libraryModel(input: {
  list: ListRequest;
  installed: StoredPackage[] | null;
  titles: Record<string, OfflineContent["title"]>;
  downloads: Record<string, DownloadState>;
}): LibraryModel {
  if (input.list.status === "pending" || input.installed === null) return { kind: "loading" };
  const installed = new Map(input.installed.filter((p) => p.state === "ready").map((p) => [p.lesson_id, p]));
  const manifests = input.list.status === "ok" ? input.list.manifests : [];

  const entries: LibraryEntry[] = [];
  const seen = new Set<string>();
  const add = (lessonId: string, objectiveCode: string, bytes: number, manifest: PackageManifest | null) => {
    seen.add(lessonId);
    const rec = installed.get(lessonId);
    const dl = input.downloads[lessonId] ?? { kind: "idle" };
    let status: EntryStatus;
    if (dl.kind === "downloading") status = { kind: "downloading", fraction: dl.fraction };
    else if (dl.kind === "failed") status = { kind: "failed", reason: dl.reason, installed: !!rec };
    else if (rec) status = { kind: "installed", updateAvailable: !!manifest && manifest.content_hash !== rec.content_hash };
    else status = { kind: "available" };
    const title = input.titles[lessonId];
    entries.push({
      lessonId,
      objectiveCode,
      title: title ? pickLocalized(title, INSTRUCTION_LOCALE_PREFERENCE) : null,
      bytes,
      status,
    });
  };
  for (const m of manifests) add(m.lesson_id, m.objective_code, m.total_bytes, m);
  // Installed lessons the server no longer lists (or the list is unreachable) stay playable.
  for (const rec of installed.values()) {
    if (!seen.has(rec.lesson_id)) add(rec.lesson_id, rec.lesson_id, rec.total_bytes, null);
  }

  if (entries.length === 0 && input.list.status === "ok") return { kind: "nothing-published" };
  return {
    kind: "list",
    entries,
    listUnavailable: input.list.status === "error",
    installedBytes: [...installed.values()].reduce((sum, p) => sum + p.total_bytes, 0),
  };
}

/** "1.2 MB" in the interface locale. */
export function formatBytes(bytes: number, locale: string): string {
  const units = ["byte", "kilobyte", "megabyte", "gigabyte"] as const;
  let value = Math.max(0, bytes);
  let i = 0;
  while (value >= 1000 && i < units.length - 1) {
    value /= 1000;
    i++;
  }
  try {
    return new Intl.NumberFormat(`${locale}-u-nu-latn`, {
      style: "unit",
      unit: units[i],
      unitDisplay: "short",
      maximumFractionDigits: i === 0 ? 0 : 1,
    }).format(value);
  } catch {
    return `${Math.round(value)} ${["B", "kB", "MB", "GB"][i]}`;
  }
}

// ---- the service -------------------------------------------------------------------------------------

const KEYS_PREF = "offline_signing_keys";

export interface LibraryDeps {
  store: KVStore;
  listPackages: () => Promise<{ packages: PackageManifest[] }>;
  fetchPackage: (lessonId: string) => Promise<OfflinePackage>;
  signingKeys: () => Promise<{ keys: SigningKey[] }>;
  configuredKeys?: Record<string, string>;
  estimate?: () => Promise<StorageEstimate>;
  now?: () => number;
}

export function createLibrary(deps: LibraryDeps) {
  const now = deps.now ?? Date.now;

  async function resolver() {
    const remembered = (await deps.store.get<Record<string, string>>(STORES.prefs, KEYS_PREF)) ?? {};
    let fetched: SigningKey[] = [];
    try {
      fetched = (await deps.signingKeys()).keys;
    } catch {
      // Offline or unavailable: verify with what this device already trusts.
    }
    const merged = mergeSigningKeys({ configured: deps.configuredKeys ?? {}, remembered, fetched });
    await deps.store.put(STORES.prefs, KEYS_PREF, merged.remember);
    return pinnedKeyResolver(merged.keys);
  }

  async function manager(): Promise<DownloadManager> {
    return new DownloadManager({
      store: deps.store,
      fetchPackage: deps.fetchPackage,
      now,
      requireSignature: true,
      resolveKey: await resolver(),
      ...(deps.estimate ? { estimate: deps.estimate } : {}),
    });
  }

  // A manager for reads/removal only (no network, no keys needed).
  const local = new DownloadManager({ store: deps.store, fetchPackage: deps.fetchPackage, now });

  return {
    list: () => deps.listPackages().then((r) => r.packages),
    installed: () => local.installedPackages(),
    async titles(lessonIds: string[]): Promise<Record<string, OfflineContent["title"]>> {
      const out: Record<string, OfflineContent["title"]> = {};
      for (const id of lessonIds) {
        const c = await deps.store.get<OfflineContent>(STORES.content, id);
        if (c) out[id] = c.title;
      }
      return out;
    },
    /** Download, verify the signature and content hash, then install. Throws without installing. */
    async install(lessonId: string, onProgress?: (fraction: number) => void): Promise<StoredPackage> {
      return (await manager()).download(lessonId, onProgress);
    },
    remove: (lessonId: string) => local.remove(lessonId),
  };
}

export type OfflineLibrary = ReturnType<typeof createLibrary>;
