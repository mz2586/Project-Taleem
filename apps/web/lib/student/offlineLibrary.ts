// The offline lesson library — what /student/offline lists, and how a lesson gets onto the phone.
// The view model is pure and tested; the service composes the app's ONE download manager.
//
// Verification is not optional. Every install goes through lib/offline's DownloadManager, which
// fails closed: an unsigned package, one whose key cannot be resolved, or one that does not verify
// is refused and nothing is written. The keys come from lib/offline/keys.ts (build-time
// NEXT_PUBLIC_OFFLINE_SIGNING_KEYS, else trust-on-first-use that refuses a changed key). The library
// is handed the shared client's manager (lib/student/offlineClient.ts), so there is a single
// download configuration in the app.

import type { MessageKey } from "../i18n/messages";
import { IntegrityError, QuotaExceededError, SignatureError } from "../offline/packages";
import type { DownloadManager } from "../offline/packages";
import type { OfflineContent, PackageManifest, StoredPackage } from "../offline/types";
import { pickLocalized } from "../i18n/content";
import { INSTRUCTION_LOCALE_PREFERENCE } from "./journey";
import { ApiError } from "./types";

// ---- signing keys: see lib/offline/keys.ts (re-exported for existing callers) ---------------------

export { configuredSigningKeys, mergeSigningKeys } from "../offline/keys";
export type { KeyMerge } from "../offline/keys";

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

export interface LibraryDeps {
  /** The app's download manager (signature-verifying; see lib/offline createDownloadManager). */
  downloads: DownloadManager;
  listPackages: () => Promise<{ packages: PackageManifest[] }>;
}

export function createLibrary(deps: LibraryDeps) {
  return {
    list: () => deps.listPackages().then((r) => r.packages),
    installed: (): Promise<StoredPackage[]> => deps.downloads.installedPackages(),
    async titles(lessonIds: string[]): Promise<Record<string, OfflineContent["title"]>> {
      const out: Record<string, OfflineContent["title"]> = {};
      for (const id of lessonIds) {
        const c = await deps.downloads.peekLesson(id);
        if (c) out[id] = c.title;
      }
      return out;
    },
    /** Download, verify the signature and content hash, then install. Throws without installing. */
    install: (lessonId: string, onProgress?: (fraction: number) => void): Promise<StoredPackage> =>
      deps.downloads.download(lessonId, onProgress),
    remove: (lessonId: string) => deps.downloads.remove(lessonId),
  };
}

export type OfflineLibrary = ReturnType<typeof createLibrary>;
