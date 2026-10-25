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
//
// Homework sent offline (`homework.submitted`, lib/homework/offlineQueue.ts):
//   - a homework draft is wiped only once the server confirmed that answer (`applied` /
//     `duplicate`), and only if the draft still holds exactly the text that was sent;
//   - whenever a learner's drafts are wiped (sign-out, consent withdrawal, the learner gate's
//     refusal — lib/homework/drafts.ts `clearHomeworkDrafts`), their queued homework answers and
//     results go too: the child's words never outlive the permission they were written under.

import { draftKeyOfDelta, shouldWipeDraft } from "../homework/offlineQueue";
import { localDrafts, onHomeworkDraftsCleared } from "../homework/drafts";
import { createOfflineClient, ownerOf } from "../offline";
import type { ItemResult, OfflineClient, QueuedDelta } from "../offline";
import { sessionStore, withSession } from "../session/store";
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
      fetchPackage: (lessonId: string) => withSession(() => offlineApi.fetchPackage(lessonId)),
      // Every install is signature-verified (lib/offline/packages.ts fails closed). Keys: the
      // build-time NEXT_PUBLIC_OFFLINE_SIGNING_KEYS, else trust-on-first-use from this endpoint.
      fetchSigningKeys: () => withSession(() => offlineApi.signingKeys()),
      postBatch: async (cursor, deltas) => {
        await sessionStore.valid();
        return syncApi.batch(cursor, deltas);
      },
      refreshSession: async () => (await sessionStore.refresh()) !== null,
      currentLearner: () => learnerOf(sessionStore.peek()),
      onSettled: async (settled) => wipeConfirmedDrafts(settled),
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

/** After a sync: wipe the draft of each homework answer the server confirmed (unchanged drafts only). */
export function wipeConfirmedDrafts(settled: ReadonlyArray<{ delta: QueuedDelta; result: ItemResult }>): void {
  for (const { delta, result } of settled) {
    if (delta.type !== "homework.submitted") continue;
    if (result.status !== "applied" && result.status !== "duplicate") continue;
    const key = draftKeyOfDelta(delta);
    if (key && shouldWipeDraft(localDrafts.read(key), delta.payload["text"])) localDrafts.clear(key);
  }
}

/** Remove queued homework answers (one learner's, or everyone's) and their results from this phone. */
export async function forgetQueuedHomework(client: OfflineClient, studentRef: string | undefined): Promise<void> {
  if (studentRef) {
    await client.sync.forgetHomework(studentRef);
    return;
  }
  const owners = new Set<string>();
  for (const d of await client.sync.queue.all()) {
    const owner = d.type === "homework.submitted" ? ownerOf(d) : null;
    if (owner) owners.add(owner);
  }
  for (const r of await client.sync.homework.all()) if (r.studentRef) owners.add(r.studentRef);
  for (const owner of owners) await client.sync.forgetHomework(owner);
}

// Registered when this module loads (every learner screen and the guardian API load it), so a wipe
// reaches the queued copies in IndexedDB. Without IndexedDB nothing can have been queued.
onHomeworkDraftsCleared((studentRef) => {
  if (typeof indexedDB === "undefined") return;
  void forgetQueuedHomework(getOfflineClient(), studentRef).catch(() => undefined);
});
