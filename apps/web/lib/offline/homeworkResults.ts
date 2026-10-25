// What the server said about each homework answer sent from this phone through offline sync
// (OFFLINE_SYNC_SPEC.md `homework.submitted`). One record per item (the latest answer sent), so the
// Homework screen can show the server's result — "Checked by Taleem", "Saved, compare", "Sent to
// your teacher", or a gentle conflict message — after the queue copy is gone, and across reloads.
//
// No child text is kept here: the server's submission view is stored WITHOUT `submission.text`
// (the answer itself is on the server once confirmed; a conflicted answer stays in the draft).
// Bounded, per learner, and forgotten with the learner (purge, sign-out, consent withdrawal).

import type { KVStore } from "./kv";
import { STORES } from "./kv";
import { ownerOf } from "./syncQueue";
import type { ItemResult, QueuedDelta, SyncStatus } from "./types";

const KEY = "homework_results";
export const HOMEWORK_RESULTS_LIMIT = 200;

export interface HomeworkResultRecord {
  entityKey: string;
  clientEventId: string;
  studentRef: string | null;
  status: SyncStatus;
  /** Set on a conflict: the server's reason (SUBMISSION_MARKED, NOT_AVAILABLE, …). */
  reason: string | null;
  /** The server's submit view (the online submit's shape), text removed. Null on a conflict. */
  result: Record<string, unknown> | null;
  at: number;
}

/** The server view without the child's words. */
export function withoutText(result: Record<string, unknown> | undefined): Record<string, unknown> | null {
  if (!result || typeof result !== "object") return null;
  const submission = result["submission"];
  if (submission && typeof submission === "object") {
    const rest: Record<string, unknown> = { ...(submission as Record<string, unknown>) };
    delete rest["text"];
    return { ...result, submission: rest };
  }
  return { ...result };
}

export class HomeworkResultLedger {
  constructor(
    private readonly store: KVStore,
    private readonly limit: number = HOMEWORK_RESULTS_LIMIT,
  ) {}

  async all(): Promise<HomeworkResultRecord[]> {
    return (await this.store.get<HomeworkResultRecord[]>(STORES.syncMeta, KEY)) ?? [];
  }

  /** Record the server's answers for homework deltas (newest wins per item). */
  async record(settled: ReadonlyArray<{ delta: QueuedDelta; result: ItemResult }>, now: number): Promise<void> {
    const mine = settled.filter((s) => s.delta.type === "homework.submitted");
    if (mine.length === 0) return;
    const byEntity = new Map((await this.all()).map((r) => [r.entityKey, r] as const));
    for (const { delta, result } of mine) {
      byEntity.delete(delta.entityKey);
      byEntity.set(delta.entityKey, {
        entityKey: delta.entityKey,
        clientEventId: delta.clientEventId,
        studentRef: ownerOf(delta),
        status: result.status,
        reason: result.status === "conflict" ? (result.reason ?? "CONFLICT") : null,
        result: result.status === "conflict" ? null : withoutText(result.result),
        at: now,
      });
    }
    const merged = Array.from(byEntity.values());
    await this.store.put(STORES.syncMeta, KEY, merged.slice(Math.max(0, merged.length - this.limit)));
  }

  async forget(studentRef: string): Promise<void> {
    const kept = (await this.all()).filter((r) => r.studentRef !== studentRef);
    await this.store.put(STORES.syncMeta, KEY, kept);
  }
}
