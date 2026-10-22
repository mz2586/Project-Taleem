// Offline guarantees (GLOBAL_PRODUCT_SCOPE §E) — the failure paths of the drain.
//
// Each test names the guarantee it proves; OFFLINE_TEST_PLAN.md "Guarantee traceability" maps them.
// The fake server mirrors the real one: idempotent by clientEventId AND by the durable evidence_id,
// with per-item statuses, and it can be told to fail a request with an HTTP status + problem code.
import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { FaultyStore } from "../chaos";
import { IdbStore, MemoryStore, STORES } from "../kv";
import type { KVStore } from "../kv";
import { classifyFailure, SyncClient } from "../syncClient";
import { SyncQueue } from "../syncQueue";
import { AckLedger, summarizeSyncStatus } from "../syncStatus";
import type { BatchResult, ItemResult, SyncDelta } from "../types";

class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly problem: { code?: string } = {},
  ) {
    super(problem.code ?? `HTTP ${status}`);
  }
}

// A server with a durable evidence ledger keyed by evidence_id (like the real evidence table).
function durableServer() {
  const events = new Set<string>();
  const evidence = new Map<string, number>(); // evidence_id -> times recorded (must stay 1)
  let cursor = 0;
  const calls: SyncDelta[][] = [];
  let failNext: HttpError[] = [];
  const answer = (d: SyncDelta): ItemResult => {
    const evId = String(d.payload["evidence_id"] ?? d.clientEventId);
    if (events.has(d.clientEventId) || evidence.has(evId)) {
      return { clientEventId: d.clientEventId, status: "duplicate", version: cursor };
    }
    events.add(d.clientEventId);
    evidence.set(evId, 1);
    cursor++;
    return { clientEventId: d.clientEventId, status: "applied", version: cursor };
  };
  const post = vi.fn(async (_c: number, deltas: SyncDelta[]): Promise<BatchResult> => {
    calls.push(deltas);
    const err = failNext.shift();
    if (err) throw err;
    return { cursor, results: deltas.map(answer) };
  });
  return {
    post,
    calls,
    evidence,
    failWith: (...errs: HttpError[]) => {
      failNext = errs;
    },
  };
}

async function seed(q: SyncQueue, ids: string[], student = "S1", seqStart = 1): Promise<void> {
  let seq = seqStart;
  for (const id of ids) {
    await q.enqueue({
      clientEventId: id,
      type: "attempt.submitted",
      entityKey: `student:${student}|item:${id}`,
      payload: { evidence_id: `ev-${id}`, student_ref: student, item_ref: id, option: 0 },
      clientSeq: seq++,
    });
  }
}

function setup(store: KVStore = new MemoryStore()) {
  const queue = new SyncQueue(store, () => 1);
  const acks = new AckLedger(store);
  const server = durableServer();
  return { store, queue, acks, server };
}

describe("error classification", () => {
  it("maps HTTP statuses to the drain's failure kinds", () => {
    expect(classifyFailure(new Error("fetch failed")).kind).toBe("offline");
    expect(classifyFailure(new HttpError(0)).kind).toBe("offline");
    expect(classifyFailure(new HttpError(401)).kind).toBe("unauthorized");
    expect(classifyFailure(new HttpError(403, { code: "CONSENT_REQUIRED" }))).toMatchObject({
      kind: "forbidden",
      code: "CONSENT_REQUIRED",
    });
    expect(classifyFailure(new HttpError(422)).kind).toBe("invalid");
    expect(classifyFailure(new HttpError(503)).kind).toBe("server");
  });
});

describe("G-AUTH: a 401 mid-drain refreshes once, retries, and never drops deltas", () => {
  it("refreshes the session once and retries the same batch successfully", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "b"]);
    server.failWith(new HttpError(401));
    const refreshSession = vi.fn(async () => true);
    const client = new SyncClient({ queue, store, acks, postBatch: server.post, refreshSession });

    const s = await client.drain();
    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(s.applied).toBe(2);
    expect(s.blocked).toBeNull();
    expect(await queue.pendingCount()).toBe(0);
    // The retry carried the SAME deltas (same idempotency keys), not a re-minted copy.
    expect(server.calls[1]?.map((d) => d.clientEventId)).toEqual(["a", "b"]);
  });

  it("keeps the queue byte-for-byte intact when the 401 survives the refresh", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "b", "c"]);
    const before = await queue.all();
    server.failWith(new HttpError(401), new HttpError(401));
    const refreshSession = vi.fn(async () => true);
    const client = new SyncClient({ queue, store, acks, postBatch: server.post, refreshSession, batchSize: 2 });

    const s = await client.drain();
    expect(refreshSession).toHaveBeenCalledTimes(1); // one refresh per drain — rotation-safe
    expect(s.blocked).toBe("auth");
    expect(await queue.all()).toEqual(before); // no attempts++, no state change, nothing dropped
    expect(await acks.lastBlock()).toEqual({ reason: "auth", code: "UNAUTHORIZED" });
  });

  it("keeps the queue when the refresh itself fails (session revoked)", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a"]);
    server.failWith(new HttpError(401));
    const client = new SyncClient({
      queue,
      store,
      acks,
      postBatch: server.post,
      refreshSession: async () => false,
    });
    const s = await client.drain();
    expect(s.blocked).toBe("auth");
    expect(server.calls).toHaveLength(1); // no retry without a usable session
    expect(await queue.pendingCount()).toBe(1);
  });

  it("sends nothing when no learner is signed in (guardian or signed-out device)", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a"]);
    const client = new SyncClient({ queue, store, acks, postBatch: server.post, currentLearner: () => null });
    const s = await client.drain();
    expect(server.post).not.toHaveBeenCalled();
    expect(s.blocked).toBe("auth");
    expect(await queue.pendingCount()).toBe(1);
  });
});

describe("G-PERM: a 403 (consent withdrawn / learner suspended) holds deltas, no hot loop", () => {
  it("holds ALL of the learner's deltas, retains them, and surfaces blocked-by-permission", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "b", "c", "d", "e"]);
    server.failWith(new HttpError(403, { code: "CONSENT_REQUIRED" }));
    const client = new SyncClient({ queue, store, acks, postBatch: server.post, batchSize: 2 });

    const s = await client.drain();
    expect(s.blocked).toBe("permission");
    expect(s.blockedCode).toBe("CONSENT_REQUIRED");
    expect(s.held).toBe(5); // the whole learner, not just the first page
    expect(server.calls).toHaveLength(1);
    const held = await queue.held();
    expect(held.map((d) => d.clientEventId).sort()).toEqual(["a", "b", "c", "d", "e"]);
    expect(held.every((d) => d.heldReason === "CONSENT_REQUIRED")).toBe(true);

    // Not retried in a loop: further drains send nothing while held.
    for (let i = 0; i < 5; i++) await client.drain();
    expect(server.calls).toHaveLength(1);

    const summary = summarizeSyncStatus({
      queue: await queue.all(),
      acks: await acks.all(),
      lastBlock: await acks.lastBlock(),
    });
    expect(summary).toMatchObject({ held: 5, savedOnDevice: 5, waiting: 0, blocked: "permission" });
    expect(summary.blockedCode).toBe("CONSENT_REQUIRED");
  });

  it("a non-learner-level 403 holds only the refused batch", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "b", "c"]);
    server.failWith(new HttpError(403, { code: "FORBIDDEN" }));
    const client = new SyncClient({ queue, store, acks, postBatch: server.post, batchSize: 1 });
    await client.drain();
    expect((await queue.held()).map((d) => d.clientEventId)).toEqual(["a"]);
  });

  it("held deltas sync exactly once after release (consent re-granted, new session)", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "b"]);
    server.failWith(new HttpError(403, { code: "LEARNER_INACTIVE" }));
    const client = new SyncClient({ queue, store, acks, postBatch: server.post });
    await client.drain();
    expect((await queue.held()).length).toBe(2);

    expect(await queue.releaseHeld("S1")).toBe(2);
    const s = await client.drain();
    expect(s.applied).toBe(2);
    expect(await queue.all()).toEqual([]);
    expect([...server.evidence.values()]).toEqual([1, 1]);
  });
});

describe("G-IDEM: crash between server ack and local delete is idempotent by evidence_id", () => {
  beforeEach(async () => {
    const s = new IdbStore(indexedDB);
    for (const name of Object.values(STORES)) await s.clear(name);
  });

  it("re-sends after restart, the server answers duplicate, evidence is recorded once", async () => {
    const server = durableServer();
    // Run 1: the server applies the batch, then the tab dies before the local delete commits.
    const crashing = new FaultyStore(new IdbStore(indexedDB), { failOn: ["delete"], maxFailures: 1 });
    const q1 = new SyncQueue(crashing, () => 1);
    await seed(q1, ["a"]);
    const c1 = new SyncClient({ queue: q1, store: crashing, acks: new AckLedger(crashing), postBatch: server.post });
    await expect(c1.drain()).rejects.toThrow(/injected fault/);
    expect(server.evidence.get("ev-a")).toBe(1);

    // Run 2 (browser restart): a fresh store over the same IndexedDB still holds the delta.
    const store2 = new IdbStore(indexedDB);
    const q2 = new SyncQueue(store2, () => 1);
    expect(await q2.pendingCount()).toBe(1);
    const c2 = new SyncClient({ queue: q2, store: store2, acks: new AckLedger(store2), postBatch: server.post });
    const s = await c2.drain();
    expect(s.duplicate).toBe(1);
    expect(s.applied).toBe(0);
    expect(await q2.pendingCount()).toBe(0);
    expect(server.evidence.get("ev-a")).toBe(1); // exactly once — never double-counted
  });

  it("a re-queued attempt with a NEW clientEventId but the same evidence_id is a duplicate", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a"]);
    const client = new SyncClient({ queue, store, acks, postBatch: server.post });
    await client.drain();
    await queue.enqueue({
      clientEventId: "a-requeued",
      type: "attempt.submitted",
      entityKey: "student:S1|item:a",
      payload: { evidence_id: "ev-a", student_ref: "S1", item_ref: "a", option: 0 },
    });
    const s = await client.drain();
    expect(s.duplicate).toBe(1);
    expect(server.evidence.get("ev-a")).toBe(1);
  });

  it("a delta stranded in the legacy 'sending' state after a crash is still drained", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a"]);
    await queue.markSending(["a"]);
    const s = await new SyncClient({ queue, store, acks, postBatch: server.post }).drain();
    expect(s.applied).toBe(1);
  });
});

describe("G-PARTIAL: partial batch failure keeps exactly the unaccepted items, with reasons", () => {
  it("removes accepted items, dead-letters rejected ones with a reason, keeps unanswered ones", async () => {
    const { store, queue, acks } = setup();
    await seed(queue, ["ok1", "bad", "ok2", "lost"]);
    const post = async (_c: number, deltas: SyncDelta[]): Promise<BatchResult> => ({
      cursor: 2,
      results: deltas
        .filter((d) => d.clientEventId !== "lost") // the server dropped one item
        .map((d) => ({
          clientEventId: d.clientEventId,
          status: d.clientEventId === "bad" ? ("conflict" as const) : ("applied" as const),
          version: 1,
        })),
    });
    const client = new SyncClient({ queue, store, acks, postBatch: post });
    const s = await client.drain();

    expect(s.applied).toBe(2);
    expect(s.conflict).toBe(1);
    const left = new Map((await queue.all()).map((d) => [d.clientEventId, d] as const));
    expect([...left.keys()].sort()).toEqual(["bad", "lost"]);
    expect(left.get("bad")?.syncState).toBe("dead");
    expect(left.get("bad")?.lastError).toBe("server reported conflict");
    expect(left.get("lost")?.syncState).toBe("failed"); // retried next drain, not looped now
    expect(s.remaining).toBe(1);
  });

  it("isolates a poison delta behind a whole-batch 422 so the rest still sync", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "poison", "b"]);
    const post = vi.fn(async (c: number, deltas: SyncDelta[]): Promise<BatchResult> => {
      if (deltas.some((d) => d.clientEventId === "poison")) {
        throw new HttpError(422, { code: "UNKNOWN_DELTA_TYPE" });
      }
      return server.post(c, deltas);
    });
    const client = new SyncClient({ queue, store, acks, postBatch: post });
    const s = await client.drain();

    expect(s.applied).toBe(2);
    const left = await queue.all();
    expect(left.map((d) => d.clientEventId)).toEqual(["poison"]);
    expect(left[0]?.syncState).toBe("dead");
    expect(left[0]?.lastError).toBe("rejected: UNKNOWN_DELTA_TYPE");
  });
});

describe("G-DURABLE: transient failures never dead-letter acknowledged-by-user work", () => {
  it("50 offline drains and a 5xx outage leave every delta pending, then all sync once", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a", "b"]);
    let mode: "offline" | "5xx" | "up" = "offline";
    const post = async (c: number, d: SyncDelta[]): Promise<BatchResult> => {
      if (mode === "offline") throw new Error("Failed to fetch");
      if (mode === "5xx") throw new HttpError(503);
      return server.post(c, d);
    };
    const client = new SyncClient({ queue, store, acks, postBatch: post });
    for (let i = 0; i < 50; i++) expect((await client.drain()).blocked).toBe("offline");
    mode = "5xx";
    for (let i = 0; i < 20; i++) expect((await client.drain()).blocked).toBe("server");
    expect(await queue.deadLetters()).toEqual([]);
    expect(await queue.pendingCount()).toBe(2);

    mode = "up";
    const s = await client.drain();
    expect(s.applied).toBe(2);
    expect(s.blocked).toBeNull();
    expect(await acks.lastBlock()).toBeNull();
  });

  it("on a shared device only the signed-in learner's deltas are sent", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a1"], "A", 1);
    await seed(queue, ["b1"], "B", 2);
    const client = new SyncClient({ queue, store, acks, postBatch: server.post, currentLearner: () => "B" });
    const s = await client.drain();
    expect(server.calls.flat().map((d) => d.clientEventId)).toEqual(["b1"]);
    expect(s.applied).toBe(1);
    expect((await queue.all()).map((d) => d.clientEventId)).toEqual(["a1"]); // A's work kept
  });

  it("records acknowledgements in the ledger before releasing the queue copy", async () => {
    const { store, queue, acks, server } = setup();
    await seed(queue, ["a"]);
    await new SyncClient({ queue, store, acks, postBatch: server.post, now: () => 42 }).drain();
    expect(await acks.all()).toEqual([
      { clientEventId: "a", type: "attempt.submitted", studentRef: "S1", status: "applied", ackedAt: 42 },
    ]);
  });
});
