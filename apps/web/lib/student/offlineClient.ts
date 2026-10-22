// Browser offline client (Phase 6.2B) — wires the offline-lite library to the student API.
// A lazily-built singleton so the durable queue, sync client, and stores are shared app-wide.
// Call only in the browser (uses IndexedDB); safe to reference under SSR but build it in an effect.
//
// Session wiring (read-only use of lib/session's public API):
//   - before each batch the token is freshened via `sessionStore.valid()`;
//   - a 401 mid-drain triggers ONE `sessionStore.refresh()` (single-flight, rotation-safe) and a
//     retry; the queue is never touched by an auth failure;
//   - only the signed-in LEARNER's deltas are sent (a guardian token, or a sibling's token on a
//     shared device, never carries another child's work);
//   - when a learner session is adopted, that learner's permission-HELD deltas are released for one
//     more attempt (consent re-granted / learner reinstated) — bounded by session changes, never a
//     hot loop.

import { createOfflineClient } from "../offline";
import type { OfflineClient } from "../offline";
import { sessionStore } from "../session/store";
import type { StoredSession } from "../session/store";
import { offlineApi, syncApi } from "./api";

let singleton: OfflineClient | null = null;

// The learner a session can sync for (null = no learner signed in). Exported for tests.
export function learnerOf(session: StoredSession | null): string | null {
  return session && session.role === "student" ? session.subject : null;
}

export function getOfflineClient(): OfflineClient {
  if (!singleton) {
    const client = createOfflineClient({
      fetchPackage: (lessonId: string) => offlineApi.fetchPackage(lessonId),
      postBatch: async (cursor, deltas) => {
        await sessionStore.valid();
        return syncApi.batch(cursor, deltas);
      },
      refreshSession: async () => (await sessionStore.refresh()) !== null,
      currentLearner: () => learnerOf(sessionStore.peek()),
    });
    let lastLearner = learnerOf(sessionStore.peek());
    sessionStore.subscribe((session) => {
      const learner = learnerOf(session);
      if (learner && learner !== lastLearner) void client.sync.queue.releaseHeld(learner);
      lastLearner = learner;
    });
    singleton = client;
  }
  return singleton;
}
