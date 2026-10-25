// What a child has typed for a homework item, kept on this phone until the server has it.
//
// The phone keeps the TEXT, so a child who loses the connection mid-answer does not lose their
// writing. Pressing Send with no connection queues the answer for offline sync (lib/homework/
// offlineQueue.ts); the draft stays until the server confirms it (online 2xx, or a sync result
// `applied` / `duplicate`) — a conflict keeps it. It is per learner and per item, lives in
// localStorage. Unavailable storage (private mode, quota, SSR) means "nothing kept" — never a
// crash, and never a claim that anything was saved or sent.
//
// `clearHomeworkDrafts` is THE wipe point for a learner's homework text on this phone (sign-out,
// consent withdrawal, the learner gate's refusal). Listeners registered with
// `onHomeworkDraftsCleared` run with it, so the queued copies in IndexedDB go too.

export interface DraftStore {
  read(key: string): string | null;
  write(key: string, text: string): boolean;
  clear(key: string): void;
}

const PREFIX = "taleem.homework.draft.v1";

export function draftKey(studentRef: string, assignmentId: string, itemRef: string): string {
  return `${PREFIX}:${studentRef}:${assignmentId}:${itemRef}`;
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const localDrafts: DraftStore = {
  read(key) {
    try {
      return storage()?.getItem(key) ?? null;
    } catch {
      return null;
    }
  },
  /** True only when the text really is on the phone now. An empty text removes the draft. */
  write(key, text) {
    const s = storage();
    if (!s) return false;
    try {
      if (text === "") s.removeItem(key);
      else s.setItem(key, text);
      return true;
    } catch {
      return false;
    }
  },
  clear(key) {
    try {
      storage()?.removeItem(key);
    } catch {
      /* storage unavailable: nothing to clear */
    }
  },
};

type ClearListener = (studentRef: string | undefined) => void;
const clearListeners = new Set<ClearListener>();

/** Run `listener` whenever drafts are cleared (for one learner, or `undefined` = everyone). */
export function onHomeworkDraftsCleared(listener: ClearListener): () => void {
  clearListeners.add(listener);
  return () => clearListeners.delete(listener);
}

/** Remove every kept homework draft for one learner (or for everyone on this phone). */
export function clearHomeworkDrafts(studentRef?: string): void {
  for (const listener of clearListeners) {
    try {
      listener(studentRef);
    } catch {
      /* a listener must never stop the wipe */
    }
  }
  const s = storage();
  if (!s) return;
  const prefix = studentRef ? `${PREFIX}:${studentRef}:` : `${PREFIX}:`;
  try {
    const keys: string[] = [];
    for (let i = 0; i < s.length; i++) {
      const key = s.key(i);
      if (key?.startsWith(prefix)) keys.push(key);
    }
    for (const key of keys) s.removeItem(key);
  } catch {
    /* storage unavailable */
  }
}
