// Remembering an open unit-check sitting across a reload (PROGRESSION_AND_EXAMINATION_CONTRACT §2:
// a sitting is resumable for 24 hours). Only the sitting's id and expiry are kept, in session
// storage — never an answer, a score or a key. Storage can be missing or throw (private mode, a full
// quota, a sandboxed preview); every access is guarded and the check still works without it (the
// server may also report the open sitting itself on the path).

export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface StoredSitting {
  sittingId: string;
  /** Epoch seconds; null when the server gave none. */
  expiresAt: number | null;
}

export const SITTING_STORAGE_PREFIX = "taleem.unitCheck.v1";

export function sittingStorageKey(studentRef: string, unitKey: string): string {
  return `${SITTING_STORAGE_PREFIX}:${studentRef}:${unitKey}`;
}

/** The browser's session storage, or null where there is none (server render, blocked storage). */
export function browserSessionStore(): KeyValueStore | null {
  try {
    if (typeof window === "undefined") return null;
    return window.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export function rememberSitting(store: KeyValueStore | null, studentRef: string, unitKey: string, value: StoredSitting): boolean {
  if (!store) return false;
  try {
    store.setItem(sittingStorageKey(studentRef, unitKey), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function forgetSitting(store: KeyValueStore | null, studentRef: string, unitKey: string): void {
  if (!store) return;
  try {
    store.removeItem(sittingStorageKey(studentRef, unitKey));
  } catch {
    /* nothing to clean up */
  }
}

export function readStoredSitting(store: KeyValueStore | null, studentRef: string, unitKey: string): StoredSitting | null {
  if (!store) return null;
  try {
    const raw = store.getItem(sittingStorageKey(studentRef, unitKey));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSitting>;
    if (typeof parsed.sittingId !== "string" || !parsed.sittingId) return null;
    return { sittingId: parsed.sittingId, expiresAt: typeof parsed.expiresAt === "number" ? parsed.expiresAt : null };
  } catch {
    return null;
  }
}

export type ResumePlan = { kind: "start" } | { kind: "resume"; sittingId: string } | { kind: "expired" };

/**
 * What to do on opening the check screen: resume a remembered (or server-reported) open sitting that
 * has not run out, say plainly that an old one ran out (kept as "not finished", never failed), or
 * offer a fresh start.
 */
export function resumePlan(stored: StoredSitting | null, serverOpenSittingId: string | null, nowSeconds: number): ResumePlan {
  if (stored) {
    if (stored.expiresAt !== null && stored.expiresAt <= nowSeconds) return { kind: "expired" };
    return { kind: "resume", sittingId: stored.sittingId };
  }
  if (serverOpenSittingId) return { kind: "resume", sittingId: serverOpenSittingId };
  return { kind: "start" };
}
