// Durable sync queue (Phase 6.2B).
//
// The outbound queue of SyncDeltas, persisted in IndexedDB (`evidence_queue` store) so it survives
// reload/crash. Deltas are ordered by (clientSeq, clientEventId) for deterministic draining; each
// carries a client-generated `clientEventId` (uuid7) that is the server idempotency key. Attempts
// additionally carry a client `evidence_id` — the DURABLE idempotency key on the server.

import { uuid7 } from "./ids";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { AttemptPayload, QueuedDelta, SyncDelta } from "./types";

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

  async all(): Promise<QueuedDelta[]> {
    return this.store.getAll<QueuedDelta>(STORES.evidenceQueue);
  }

  // Deltas eligible to send (pending or previously-failed), ordered deterministically.
  async pending(limit?: number): Promise<QueuedDelta[]> {
    const ready = (await this.all())
      .filter((d) => d.syncState === "pending" || d.syncState === "failed")
      .sort((a, b) => a.clientSeq - b.clientSeq || (a.clientEventId < b.clientEventId ? -1 : 1));
    return limit !== undefined ? ready.slice(0, limit) : ready;
  }

  async pendingCount(): Promise<number> {
    return (await this.pending()).length;
  }

  async deadLetters(): Promise<QueuedDelta[]> {
    return (await this.all()).filter((d) => d.syncState === "dead");
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

  // A transient failure: increment attempts, keep for retry, dead-letter past the cap.
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

  // A non-retryable rejection (conflict): dead-letter immediately so it never blocks the queue.
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
