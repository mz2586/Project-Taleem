// Durable sync queue (Phase 6.2B).
//
// The outbound queue of SyncDeltas, persisted in IndexedDB (`evidence_queue` store) so it survives
// reload/crash. Deltas are ordered by (clientSeq, clientEventId) for deterministic draining; each
// carries a client-generated `clientEventId` (uuid7) that is the server idempotency key. Attempts
// additionally carry a client `evidence_id` — the DURABLE idempotency key on the server.
//
// Nothing leaves this store except on a server acknowledgement (applied / duplicate / ignored).
// Every other outcome keeps the delta: transient failures are retried, permission refusals are
// HELD, and server-rejected deltas are dead-lettered WITH their reason — never silently deleted.

import { uuid7 } from "./ids";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { AttemptPayload, HomeworkPayload, QueuedDelta, SyncDelta } from "./types";

const SEQ_KEY = "client_seq";
const DEFAULT_MAX_ATTEMPTS = 8;

export class SyncQueue {
  constructor(
    private readonly store: KVStore,
    private readonly now: () => number = Date.now,
    private readonly maxAttempts: number = DEFAULT_MAX_ATTEMPTS,
  ) {}

  // Monotonic Lamport-style client sequence, persisted so it never regresses across reloads.
  async nextSeq(): Promise<number> {
    const current = (await this.store.get<number>(STORES.syncMeta, SEQ_KEY)) ?? 0;
    const next = current + 1;
    await this.store.put<number>(STORES.syncMeta, SEQ_KEY, next);
    return next;
  }

  async enqueue(
    delta: Omit<SyncDelta, "clientSeq"> & { clientSeq?: number },
  ): Promise<QueuedDelta> {
    const clientSeq = delta.clientSeq ?? (await this.nextSeq());
    const record: QueuedDelta = {
      clientEventId: delta.clientEventId,
      type: delta.type,
      entityKey: delta.entityKey,
      payload: delta.payload,
      clientSeq,
      syncState: "pending",
      attempts: 0,
      createdAt: this.now(),
    };
    await this.store.put<QueuedDelta>(STORES.evidenceQueue, record.clientEventId, record);
    return record;
  }

  // Enqueue an offline attempt for server-side grading. The evidence_id is the durable idem key.
  async enqueueAttempt(payload: AttemptPayload): Promise<QueuedDelta> {
    return this.enqueue({
      clientEventId: uuid7(this.now()),
      type: "attempt.submitted",
      entityKey: `student:${payload.student_ref}|item:${payload.item_ref}`,
      payload: payload as unknown as Record<string, unknown>,
    });
  }

  // Enqueue a homework answer sent while offline. One answer per item travels: a newer Send for the
  // same item replaces the older queued one (the server keeps one row per item anyway, and the
  // newest text is what the child meant). The submission_key doubles as the clientEventId.
  async enqueueHomework(payload: HomeworkPayload): Promise<QueuedDelta> {
    const entityKey = homeworkEntityKey(payload);
    for (const d of await this.all()) {
      if (d.type === "homework.submitted" && d.entityKey === entityKey) {
        await this.store.delete(STORES.evidenceQueue, d.clientEventId);
      }
    }
    return this.enqueue({
      clientEventId: payload.submission_key,
      type: "homework.submitted",
      entityKey,
      payload: payload as unknown as Record<string, unknown>,
    });
  }

  // Remove every queued homework answer of one learner (sign-out / consent withdrawal on this
  // phone: the child's words must not outlive the permission they were written under).
  async removeHomework(studentRef: string): Promise<number> {
    let removed = 0;
    for (const d of await this.all()) {
      if (d.type === "homework.submitted" && ownerOf(d) === studentRef) {
        await this.store.delete(STORES.evidenceQueue, d.clientEventId);
        removed++;
      }
    }
    return removed;
  }

  async all(): Promise<QueuedDelta[]> {
    return this.store.getAll<QueuedDelta>(STORES.evidenceQueue);
  }

  async get(id: string): Promise<QueuedDelta | undefined> {
    return this.store.get<QueuedDelta>(STORES.evidenceQueue, id);
  }

  // Deltas eligible to send (pending, previously-failed, or a "sending" marker stranded by a
  // crash), ordered deterministically. `owner` restricts to one learner's deltas: on a shared
  // device only the signed-in learner's work may be sent under their token. Held and dead deltas
  // are never eligible, so neither can cause a retry loop.
  async pending(limit?: number, owner?: string): Promise<QueuedDelta[]> {
    const ready = (await this.all())
      .filter(
        (d) => d.syncState === "pending" || d.syncState === "failed" || d.syncState === "sending",
      )
      .filter((d) => {
        if (owner === undefined) return true;
        const o = ownerOf(d);
        return o === owner || o === null; // device-level deltas travel with any learner's session
      })
      .sort((a, b) => a.clientSeq - b.clientSeq || (a.clientEventId < b.clientEventId ? -1 : 1));
    return limit !== undefined ? ready.slice(0, limit) : ready;
  }

  async pendingCount(owner?: string): Promise<number> {
    return (await this.pending(undefined, owner)).length;
  }

  async deadLetters(): Promise<QueuedDelta[]> {
    return (await this.all()).filter((d) => d.syncState === "dead");
  }

  async held(): Promise<QueuedDelta[]> {
    return (await this.all()).filter((d) => d.syncState === "held");
  }

  async markSending(ids: string[]): Promise<void> {
    for (const id of ids) {
      const d = await this.store.get<QueuedDelta>(STORES.evidenceQueue, id);
      if (d) await this.store.put<QueuedDelta>(STORES.evidenceQueue, id, { ...d, syncState: "sending" });
    }
  }

  // A settled delta (applied/duplicate/ignored) is removed from the queue.
  async remove(id: string): Promise<void> {
    await this.store.delete(STORES.evidenceQueue, id);
  }

  // A failure attributable to THIS delta's content (e.g. a 422 isolated to it): attempts++, keep
  // for retry, dead-letter past the cap. Not used for network/auth/permission failures.
  async markFailed(id: string, error: string): Promise<QueuedDelta | undefined> {
    const d = await this.store.get<QueuedDelta>(STORES.evidenceQueue, id);
    if (!d) return undefined;
    const attempts = d.attempts + 1;
    const next: QueuedDelta = {
      ...d,
      attempts,
      lastError: error,
      syncState: attempts >= this.maxAttempts ? "dead" : "failed",
    };
    await this.store.put<QueuedDelta>(STORES.evidenceQueue, id, next);
    return next;
  }

  // A transient failure (offline, 5xx, a server that dropped an item): attempts++ for diagnostics,
  // but NEVER dead-lettered — a week without signal must not turn a child's work into a dead letter.
  async markRetry(id: string, error: string): Promise<void> {
    const d = await this.store.get<QueuedDelta>(STORES.evidenceQueue, id);
    if (!d) return;
    await this.store.put<QueuedDelta>(STORES.evidenceQueue, id, {
      ...d,
      attempts: d.attempts + 1,
      lastError: error,
      syncState: "failed",
    });
  }

  // A permission refusal (403): retain the delta intact and stop offering it to the drain, so a
  // withdrawn consent never causes a hot retry loop and never deletes the child's work.
  async hold(ids: string[], reason: string): Promise<void> {
    for (const id of ids) {
      const d = await this.store.get<QueuedDelta>(STORES.evidenceQueue, id);
      if (d && d.syncState !== "dead") {
        await this.store.put<QueuedDelta>(STORES.evidenceQueue, id, {
          ...d,
          syncState: "held",
          heldReason: reason,
          lastError: reason,
        });
      }
    }
  }

  // Make held deltas eligible again (a new session; consent re-granted), optionally for one
  // learner. Returns how many were released. Called on a session change, so never a hot loop.
  async releaseHeld(owner?: string): Promise<number> {
    let released = 0;
    for (const d of await this.held()) {
      if (owner !== undefined && ownerOf(d) !== owner) continue;
      const next: QueuedDelta = { ...d, syncState: "pending" };
      delete next.heldReason;
      await this.store.put<QueuedDelta>(STORES.evidenceQueue, d.clientEventId, next);
      released++;
    }
    return released;
  }

  // A non-retryable rejection (conflict): dead-letter immediately so it never blocks the queue.
  // The record — and its reason — stays on the device for support; it is never deleted here.
  async deadLetter(id: string, error: string): Promise<void> {
    const d = await this.store.get<QueuedDelta>(STORES.evidenceQueue, id);
    if (d) {
      await this.store.put<QueuedDelta>(STORES.evidenceQueue, id, {
        ...d,
        syncState: "dead",
        lastError: error,
      });
    }
  }
}

// The learner a delta belongs to: the attempt payload's student_ref, else the `student:<ref>|…`
// entity key. Null when neither is present (a device-level delta).
export function ownerOf(d: Pick<SyncDelta, "payload" | "entityKey">): string | null {
  const ref = d.payload["student_ref"];
  if (typeof ref === "string" && ref) return ref;
  const m = /^student:([^|]+)(\||$)/.exec(d.entityKey);
  return m?.[1] ?? null;
}

// The queue/ledger key of one homework item: the learner, where it came from, and the item.
export function homeworkEntityKey(
  p: Pick<HomeworkPayload, "student_ref" | "source" | "assignment_id" | "objective_code" | "item_ref">,
): string {
  const target = p.source === "assignment" ? `assignment:${p.assignment_id ?? ""}` : `self_paced:${p.objective_code ?? ""}`;
  return `student:${p.student_ref}|homework:${target}|item:${p.item_ref}`;
}
