// Sync client / drain worker (Phase 6.2B; failure handling hardened against GLOBAL_PRODUCT_SCOPE §E).
//
// Drains the durable queue to POST /v1/sync/batch, in deterministic (clientSeq, clientEventId)
// order. The one invariant: a delta leaves the device ONLY when the server acknowledges it.
//
// Per-item results:
//   applied / duplicate / ignored  -> acknowledged: recorded in the ack ledger, then released
//   conflict                       -> rejected: dead-lettered WITH its reason, retained on device
//   no result for a sent item      -> kept for retry (a server that drops an item never loses it)
//
// Whole-batch failures (classified from the thrown error's HTTP status, duck-typed so this module
// stays independent of the API client):
//   network (status 0 / no status) -> kept, retried on the next trigger, never dead-lettered
//   401                            -> ONE session refresh via the injected hook, then one retry;
//                                     if still 401, the queue is kept intact and the drain stops
//   403                            -> the batch is HELD (consent withdrawn / learner suspended /
//                                     not this learner): kept, not retried until a session change
//   422 on a multi-item batch      -> isolated: items re-sent one at a time, so a single poison
//                                     delta is dead-lettered and the rest still sync
//   422 on a single item           -> that item is dead-lettered with the server's reason
//   5xx / anything else            -> kept, retried later, never dead-lettered
//
// Correctness of re-sending rests on server idempotency (clientEventId + durable evidence_id).

import type { SyncDiagnosticsStore } from "./diagnostics";
import type { SyncQueue } from "./syncQueue";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import { ownerOf } from "./syncQueue";
import type { AckLedger } from "./syncStatus";
import type { AckRecord, BatchResult, DrainSummary, ItemResult, QueuedDelta, SyncBlock, SyncDelta } from "./types";

const CURSOR_KEY = "sync_cursor";
const DEFAULT_BATCH = 50;

// Server problem codes that refuse the LEARNER, not just one batch (services/core-api sync gate).
export const LEARNER_LEVEL_REFUSALS: ReadonlySet<string> = new Set([
  "CONSENT_REQUIRED",
  "LEARNER_INACTIVE",
]);

export interface SyncClientDeps {
  queue: SyncQueue;
  store: KVStore;
  diagnostics?: SyncDiagnosticsStore;
  // Records server acknowledgements for the saved / synchronized / server-confirmed status model.
  acks?: AckLedger;
  // POST a batch to the server. Throws on failure; an error with a numeric `status` (and optional
  // `problem.code`) is classified as described above, anything else is treated as offline.
  postBatch: (cursor: number, deltas: SyncDelta[]) => Promise<BatchResult>;
  batchSize?: number;
  // 6.2C-1: honor a server-delivered de-enrolment/consent-withdrawal purge (student_refs to clear).
  onPurge?: (studentRefs: string[]) => Promise<void>;
  // Force one session refresh after a 401. Resolves true if a (possibly new) session is usable.
  // Wired to the session store's single-flight `refresh()` — never a second refresh per drain.
  refreshSession?: () => Promise<boolean>;
  // The learner whose token will carry the batch. When provided, only that learner's deltas (plus
  // device-level ones) are sent; null means no learner is signed in, so nothing is sent.
  currentLearner?: () => string | null;
  // Told about every answered item (applied / duplicate / ignored / conflict) BEFORE its queue copy
  // is released, so a caller can keep what the server said (e.g. a homework result) and act on it
  // (wipe a draft only once the server confirmed it). A failing hook never breaks the drain.
  onSettled?: (settled: Array<{ delta: QueuedDelta; result: ItemResult }>) => Promise<void>;
  now?: () => number;
}

type Failure =
  | { kind: "offline"; message: string }
  | { kind: "unauthorized"; message: string }
  | { kind: "forbidden"; message: string; code: string }
  | { kind: "invalid"; message: string; code: string }
  | { kind: "server"; message: string };

// Classify a thrown postBatch error. Pure + exported for tests.
export function classifyFailure(err: unknown): Failure {
  const message = err instanceof Error ? err.message : String(err);
  const e = err as { status?: unknown; problem?: { code?: unknown } } | null;
  const status = typeof e?.status === "number" ? e.status : 0;
  const code = typeof e?.problem?.code === "string" ? e.problem.code : `HTTP_${status}`;
  if (status === 0) return { kind: "offline", message };
  if (status === 401) return { kind: "unauthorized", message };
  if (status === 403) return { kind: "forbidden", message, code };
  if (status === 400 || status === 409 || status === 413 || status === 422) {
    return { kind: "invalid", message, code };
  }
  return { kind: "server", message };
}

type PostOutcome = { ok: true; result: BatchResult } | { ok: false; failure: Failure };

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

  private async post(batch: QueuedDelta[], allowRefresh: { left: number }): Promise<PostOutcome> {
    const cursor = await this.cursor();
    const deltas = batch.map((b) => this.toDelta(b));
    try {
      return { ok: true, result: await this.deps.postBatch(cursor, deltas) };
    } catch (err) {
      const failure = classifyFailure(err);
      if (failure.kind === "unauthorized" && allowRefresh.left > 0 && this.deps.refreshSession) {
        allowRefresh.left--; // one refresh per drain: refresh tokens rotate, never spin on them
        const ok = await this.deps.refreshSession().catch(() => false);
        if (ok) {
          try {
            return { ok: true, result: await this.deps.postBatch(await this.cursor(), deltas) };
          } catch (retryErr) {
            return { ok: false, failure: classifyFailure(retryErr) };
          }
        }
      }
      return { ok: false, failure };
    }
  }

  // Drain the queue until empty or a failure stops us. Returns a summary. Re-entrancy-guarded.
  async drain(): Promise<DrainSummary> {
    const summary: DrainSummary = {
      sent: 0,
      applied: 0,
      duplicate: 0,
      ignored: 0,
      conflict: 0,
      remaining: 0,
      cursor: await this.cursor(),
      held: 0,
      blocked: null,
      blockedCode: null,
    };
    const owner = this.deps.currentLearner ? this.deps.currentLearner() : undefined;
    if (this.draining) {
      summary.remaining = await this.deps.queue.pendingCount(owner ?? undefined);
      return summary;
    }
    this.draining = true;
    try {
      if (owner === null) {
        // Nobody (or a non-learner) is signed in: their token cannot carry a child's work. Keep it.
        return await this.finish(summary, undefined, { reason: "auth", code: "NO_LEARNER_SESSION" });
      }
      const size = this.deps.batchSize ?? DEFAULT_BATCH;
      const refresh = { left: 1 };
      // Items sent in THIS drain: an item the server keeps dropping is not re-sent in a loop.
      const attempted = new Set<string>();
      for (;;) {
        const batch = (await this.deps.queue.pending(undefined, owner)).filter(
          (d) => !attempted.has(d.clientEventId),
        ).slice(0, size);
        if (batch.length === 0) break;
        for (const d of batch) attempted.add(d.clientEventId);

        const outcome = await this.post(batch, refresh);
        if (!outcome.ok) {
          const stop = await this.handleFailure(batch, outcome.failure, summary, refresh);
          if (stop) return await this.finish(summary, owner, stop);
          continue;
        }
        await this.settle(batch, outcome.result, summary);
      }
      return await this.finish(summary, owner, null);
    } finally {
      this.draining = false;
    }
  }

  // Apply a successful batch response.
  private async settle(batch: QueuedDelta[], result: BatchResult, summary: DrainSummary): Promise<void> {
    // Persist the server cursor (advisory; correctness is idempotency, not the cursor).
    await this.deps.store.put<number>(STORES.syncMeta, CURSOR_KEY, result.cursor);
    summary.cursor = result.cursor;
    summary.sent += batch.length;

    // 6.2C-1: honor a server-delivered purge (de-enrolment / consent withdrawal), if any.
    if (result.purge && result.purge.length > 0 && this.deps.onPurge) {
      await this.deps.onPurge(result.purge);
    }

    const sent = new Map(batch.map((d) => [d.clientEventId, d] as const));
    const now = (this.deps.now ?? Date.now)();
    const acked: AckRecord[] = [];
    const answered = new Set<string>();
    const settled: Array<{ delta: QueuedDelta; result: ItemResult }> = [];
    for (const r of result.results) {
      const d = sent.get(r.clientEventId);
      if (!d || answered.has(r.clientEventId)) continue; // not ours / repeated — ignore safely
      answered.add(r.clientEventId);
      settled.push({ delta: d, result: r });
    }
    if (settled.length > 0 && this.deps.onSettled) {
      try {
        await this.deps.onSettled(settled);
      } catch {
        // The server's answer still settles the queue; only the caller's bookkeeping missed it.
      }
    }
    for (const { delta: d, result: r } of settled) {
      if (r.status === "conflict") {
        summary.conflict++;
        // Kept on the device with the server's reason (never silently deleted).
        await this.deps.queue.deadLetter(
          r.clientEventId,
          r.reason ? `conflict: ${r.reason}` : "server reported conflict",
        );
        continue;
      }
      if (r.status === "applied") summary.applied++;
      else if (r.status === "duplicate") summary.duplicate++;
      else summary.ignored++;
      acked.push({
        clientEventId: d.clientEventId,
        type: d.type,
        studentRef: ownerOf(d),
        status: r.status,
        ackedAt: now,
      });
    }
    // Ledger first, then release: a crash between the two leaves the item queued (re-sent and
    // answered `duplicate`), never acknowledged-but-missing.
    await this.deps.acks?.record(acked);
    for (const a of acked) await this.deps.queue.remove(a.clientEventId);

    // A sent item the server did not answer stays queued for a later drain (never dropped).
    for (const id of sent.keys()) {
      if (!answered.has(id)) await this.deps.queue.markRetry(id, "no result from server");
    }

    await this.deps.diagnostics?.recordDrain({
      applied: summary.applied,
      duplicate: summary.duplicate,
      ignored: summary.ignored,
      conflict: summary.conflict,
    });
  }

  // Returns the block that stops the drain, or null to continue with the next page.
  private async handleFailure(
    batch: QueuedDelta[],
    failure: Failure,
    summary: DrainSummary,
    refresh: { left: number },
  ): Promise<{ reason: SyncBlock; code: string | null } | null> {
    const ids = batch.map((d) => d.clientEventId);
    switch (failure.kind) {
      case "offline":
      case "server": {
        for (const id of ids) await this.deps.queue.markRetry(id, failure.message);
        await this.deps.diagnostics?.recordDrain({ failed: batch.length }, failure.message);
        return { reason: failure.kind, code: null };
      }
      case "unauthorized": {
        // Refresh already tried (or unavailable). Leave the queue exactly as it was.
        await this.deps.diagnostics?.recordDrain({}, "unauthorized");
        return { reason: "auth", code: "UNAUTHORIZED" };
      }
      case "forbidden": {
        // A learner-level refusal (consent withdrawn, learner suspended) applies to ALL of that
        // learner's queued work, so hold it all now — later pages must not each provoke a 403.
        if (LEARNER_LEVEL_REFUSALS.has(failure.code)) {
          const owner = batch.map(ownerOf).find((o): o is string => o !== null);
          if (owner) {
            for (const d of await this.deps.queue.pending(undefined, owner)) {
              if (!ids.includes(d.clientEventId)) ids.push(d.clientEventId);
            }
          }
        }
        await this.deps.queue.hold(ids, failure.code);
        summary.held = (summary.held ?? 0) + ids.length;
        await this.deps.diagnostics?.recordDrain({}, failure.code);
        return { reason: "permission", code: failure.code };
      }
      case "invalid": {
        if (batch.length === 1) {
          const only = ids[0] as string;
          summary.conflict++;
          await this.deps.queue.deadLetter(only, `rejected: ${failure.code}`);
          await this.deps.diagnostics?.recordDrain({ deadLettered: 1 }, failure.code);
          return null;
        }
        // Isolate the poison delta: re-send one at a time within this drain.
        for (const d of batch) {
          const one = await this.post([d], refresh);
          if (one.ok) {
            await this.settle([d], one.result, summary);
            continue;
          }
          const stop = await this.handleFailure([d], one.failure, summary, refresh);
          if (stop) return stop;
        }
        return null;
      }
    }
  }

  private async finish(
    summary: DrainSummary,
    owner: string | undefined,
    block: { reason: SyncBlock; code: string | null } | null,
  ): Promise<DrainSummary> {
    summary.blocked = block?.reason ?? null;
    summary.blockedCode = block?.code ?? null;
    summary.remaining = await this.deps.queue.pendingCount(owner);
    await this.deps.acks?.setBlock(block);
    return summary;
  }
}

// Exponential backoff with full jitter (ms) for scheduling retries. Pure + testable.
export function backoffMs(attempt: number, baseMs = 1000, capMs = 60_000, rand = Math.random): number {
  const exp = Math.min(capMs, baseMs * 2 ** Math.max(0, attempt));
  return Math.floor(rand() * exp); // full jitter — avoids reconnect storms
}
