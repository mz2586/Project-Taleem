// Sync client / drain worker (Phase 6.2B).
//
// Drains the durable queue to POST /v1/sync/batch, in deterministic (clientSeq, clientEventId)
// order, handling each ItemResult idempotently:
//   applied / duplicate / ignored  -> settled, removed from the queue (safe to re-send = duplicate)
//   conflict                       -> dead-lettered (non-retryable; never blocks the queue)
//   network failure                -> kept, attempts++ , retried later (bounded, then dead-lettered)
// No background sync, no offline auth here — this is the pure drain, driven by injected deps so it
// is fully testable. Correctness rests on server idempotency (evidence_id / clientEventId).

import type { SyncDiagnosticsStore } from "./diagnostics";
import type { SyncQueue } from "./syncQueue";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { BatchResult, DrainSummary, QueuedDelta, SyncDelta } from "./types";

const CURSOR_KEY = "sync_cursor";
const DEFAULT_BATCH = 50;

export interface SyncClientDeps {
  queue: SyncQueue;
  store: KVStore;
  diagnostics?: SyncDiagnosticsStore;
  // POST a batch to the server. Throws on network failure (offline) — caller keeps the queue.
  postBatch: (cursor: number, deltas: SyncDelta[]) => Promise<BatchResult>;
  batchSize?: number;
}

export class SyncClient {
  private draining = false;

  constructor(private readonly deps: SyncClientDeps) {}

  async cursor(): Promise<number> {
    return (await this.deps.store.get<number>(STORES.syncMeta, CURSOR_KEY)) ?? 0;
  }

  private toDelta(q: QueuedDelta): SyncDelta {
    return {
      clientEventId: q.clientEventId,
      type: q.type,
      entityKey: q.entityKey,
      payload: q.payload,
      clientSeq: q.clientSeq,
    };
  }

  // Drain the queue until empty or the network fails. Returns a summary. Re-entrancy-guarded.
  async drain(): Promise<DrainSummary> {
    const summary: DrainSummary = {
      sent: 0,
      applied: 0,
      duplicate: 0,
      ignored: 0,
      conflict: 0,
      remaining: 0,
      cursor: await this.cursor(),
    };
    if (this.draining) {
      summary.remaining = await this.deps.queue.pendingCount();
      return summary;
    }
    this.draining = true;
    try {
      const size = this.deps.batchSize ?? DEFAULT_BATCH;
      // Loop pages until the queue drains or a network error stops us.
      for (;;) {
        const batch = await this.deps.queue.pending(size);
        if (batch.length === 0) break;

        const cursor = await this.cursor();
        let result: BatchResult;
        try {
          result = await this.deps.postBatch(cursor, batch.map((b) => this.toDelta(b)));
        } catch (err) {
          // Network failure: keep everything, bump attempts, stop (retry on next trigger).
          for (const d of batch) await this.deps.queue.markFailed(d.clientEventId, String(err));
          await this.deps.diagnostics?.recordDrain(
            { failed: batch.length },
            err instanceof Error ? err.message : String(err),
          );
          summary.remaining = await this.deps.queue.pendingCount();
          return summary;
        }

        // Persist the server cursor (advisory; correctness is idempotency, not the cursor).
        await this.deps.store.put<number>(STORES.syncMeta, CURSOR_KEY, result.cursor);
        summary.cursor = result.cursor;
        summary.sent += batch.length;

        for (const r of result.results) {
          if (r.status === "applied") {
            summary.applied++;
            await this.deps.queue.remove(r.clientEventId);
          } else if (r.status === "duplicate") {
            summary.duplicate++;
            await this.deps.queue.remove(r.clientEventId);
          } else if (r.status === "ignored") {
            summary.ignored++;
            await this.deps.queue.remove(r.clientEventId);
          } else {
            // conflict — non-retryable (malformed / summative / unknown). Dead-letter it.
            summary.conflict++;
            await this.deps.queue.deadLetter(r.clientEventId, "server reported conflict");
          }
        }

        await this.deps.diagnostics?.recordDrain({
          applied: summary.applied,
          duplicate: summary.duplicate,
          ignored: summary.ignored,
          conflict: summary.conflict,
        });

        // If the server returned fewer results than sent (shouldn't happen), avoid an infinite loop.
        if (result.results.length === 0) break;
      }
      summary.remaining = await this.deps.queue.pendingCount();
      return summary;
    } finally {
      this.draining = false;
    }
  }
}

// Exponential backoff with full jitter (ms) for scheduling retries. Pure + testable.
export function backoffMs(attempt: number, baseMs = 1000, capMs = 60_000, rand = Math.random): number {
  const exp = Math.min(capMs, baseMs * 2 ** Math.max(0, attempt));
  return Math.floor(rand() * exp); // full jitter — avoids reconnect storms
}
