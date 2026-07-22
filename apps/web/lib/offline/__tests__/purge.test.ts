import { describe, expect, it } from "vitest";

import { CheckpointStore } from "../checkpoint";
import { SyncDiagnosticsStore } from "../diagnostics";
import { MemoryStore } from "../kv";
import { ProgressStore } from "../progress";
import { PurgeService } from "../purge";
import { ReadCache } from "../readCache";
import { SyncClient } from "../syncClient";
import { SyncQueue } from "../syncQueue";
import type { BatchResult, SyncDelta } from "../types";

async function seedStudent(store: MemoryStore, ref: string): Promise<void> {
  const now = () => 1;
  await new ReadCache(store, now).put(ref, "/today", { total: 1 });
  await new ProgressStore(store, now).record(
    { student_ref: ref, lesson_id: "L1", objective_code: "O1", kind: "item_attempted", item_ref: "i1", selected_option: 0 },
    `ev-${ref}`,
  );
  await new CheckpointStore(store, now).start({ student_ref: ref, lesson_id: "L1", objective_code: "O1" });
  await new SyncQueue(store, now).enqueueAttempt({
    student_ref: ref,
    objective_code: "O1",
    item_ref: "i1",
    option: 0,
    evidence_id: `q-${ref}`,
  });
}

describe("cache purge / de-enrolment", () => {
  it("clears all C2 stores for a learner, scoped (no cross-learner effect)", async () => {
    const store = new MemoryStore();
    await seedStudent(store, "S1");
    await seedStudent(store, "S2");

    const purge = new PurgeService(store);
    const result = await purge.purgeStudent("S1");
    expect(result).toEqual({ readCache: 1, progress: 1, checkpoints: 1, queued: 1 });

    // S1 is gone from every C2 store; S2 untouched.
    expect(await new ReadCache(store).get("S1", "/today")).toBeUndefined();
    expect(await new ReadCache(store).get("S2", "/today")).toBeDefined();
    expect((await new ProgressStore(store).forStudent("S1")).length).toBe(0);
    expect((await new ProgressStore(store).forStudent("S2")).length).toBe(1);
    expect(await new SyncQueue(store).pendingCount()).toBe(1); // only S2's queued delta remains
  });

  it("can keep un-synced queued deltas when asked (policy option)", async () => {
    const store = new MemoryStore();
    await seedStudent(store, "S1");
    const purge = new PurgeService(store);
    const result = await purge.purgeStudent("S1", { includeUnsynced: false });
    expect(result.queued).toBe(0); // the pending (un-synced) delta was kept
    expect(await new SyncQueue(store).pendingCount()).toBe(1);
    // but the read cache / progress / checkpoints were still cleared
    expect(result.readCache).toBe(1);
  });

  it("records a purge in diagnostics", async () => {
    const store = new MemoryStore();
    await seedStudent(store, "S1");
    const diag = new SyncDiagnosticsStore(store, () => 1);
    await new PurgeService(store, diag).purgeStudent("S1");
    expect((await diag.get()).purges).toBe(1);
  });

  it("the sync client honors a server-delivered purge signal", async () => {
    const store = new MemoryStore();
    await seedStudent(store, "S1");
    const queue = new SyncQueue(store, () => 1);
    // one unrelated delta to force a drain round-trip
    await queue.enqueue({ clientEventId: "x", type: "preference.set", entityKey: "S9|p", payload: {}, clientSeq: 99 });

    const purge = new PurgeService(store);
    const post = async (_c: number, d: SyncDelta[]): Promise<BatchResult> => ({
      cursor: 1,
      results: d.map((i) => ({ clientEventId: i.clientEventId, status: "applied" as const, version: 1 })),
      purge: ["S1"],
    });
    const client = new SyncClient({
      queue,
      store,
      postBatch: post,
      onPurge: async (refs) => {
        for (const r of refs) await purge.purgeStudent(r);
      },
    });
    await client.drain();
    expect((await new ProgressStore(store).forStudent("S1")).length).toBe(0); // purged on sync
  });
});
