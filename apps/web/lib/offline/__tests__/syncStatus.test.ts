// The per-item status model: saved on this device / synchronized / server-confirmed (pure).
import { describe, expect, it } from "vitest";

import { MemoryStore } from "../kv";
import {
  AckLedger,
  ackedItemStatus,
  isDurableAck,
  itemStatus,
  queuedItemStatus,
  summarizeSyncStatus,
} from "../syncStatus";
import type { AckRecord, QueuedDelta } from "../types";

function queued(id: string, state: QueuedDelta["syncState"], extra: Partial<QueuedDelta> = {}): QueuedDelta {
  return {
    clientEventId: id,
    type: "attempt.submitted",
    entityKey: `student:S1|item:${id}`,
    payload: { student_ref: "S1", evidence_id: `ev-${id}` },
    clientSeq: 1,
    syncState: state,
    attempts: 0,
    createdAt: 0,
    ...extra,
  };
}

function ack(id: string, type: AckRecord["type"], status: AckRecord["status"], studentRef = "S1"): AckRecord {
  return { clientEventId: id, type, status, studentRef, ackedAt: 1 };
}

describe("item status", () => {
  it("anything still in the queue is saved on this device, with the blocker named", () => {
    expect(queuedItemStatus(queued("a", "pending"))).toEqual({
      clientEventId: "a",
      state: "saved_on_device",
      blocked: null,
      reason: null,
    });
    expect(queuedItemStatus(queued("b", "failed", { lastError: "offline" })).blocked).toBeNull();
    expect(queuedItemStatus(queued("c", "held", { heldReason: "CONSENT_REQUIRED" }))).toMatchObject({
      state: "saved_on_device",
      blocked: "permission",
      reason: "CONSENT_REQUIRED",
    });
    expect(queuedItemStatus(queued("d", "dead", { lastError: "server reported conflict" }))).toMatchObject({
      blocked: "rejected",
      reason: "server reported conflict",
    });
  });

  it("only a durable evidence ack is server-confirmed", () => {
    expect(isDurableAck("attempt.submitted", "applied")).toBe(true);
    expect(isDurableAck("attempt.submitted", "duplicate")).toBe(true); // already recorded durably
    expect(isDurableAck("attempt.submitted", "ignored")).toBe(false); // e.g. summative: not recorded
    expect(isDurableAck("progress.updated", "applied")).toBe(false); // process-local server policy
    expect(ackedItemStatus(ack("a", "attempt.submitted", "applied")).state).toBe("server_confirmed");
    expect(ackedItemStatus(ack("b", "preference.set", "applied")).state).toBe("synchronized");
  });

  it("prefers the live queue copy over the ledger (a re-queued id is only saved again)", () => {
    const q = [queued("a", "pending")];
    const acks = [ack("a", "attempt.submitted", "applied"), ack("z", "attempt.submitted", "duplicate")];
    expect(itemStatus("a", q, acks)?.state).toBe("saved_on_device");
    expect(itemStatus("z", q, acks)?.state).toBe("server_confirmed");
    expect(itemStatus("missing", q, acks)).toBeNull();
  });
});

describe("summary", () => {
  it("counts the three states and the blockers", () => {
    const s = summarizeSyncStatus({
      queue: [queued("a", "pending"), queued("b", "held", { heldReason: "LEARNER_INACTIVE" }), queued("c", "dead")],
      acks: [ack("d", "attempt.submitted", "applied"), ack("e", "lesson.completed", "applied")],
    });
    expect(s).toEqual({
      savedOnDevice: 3,
      waiting: 1,
      held: 1,
      rejected: 1,
      synchronized: 1,
      serverConfirmed: 1,
      blocked: "permission", // held work always surfaces, even with no recorded drain block
      blockedCode: "LEARNER_INACTIVE",
    });
  });

  it("drops a stale offline/auth block once nothing is waiting", () => {
    const s = summarizeSyncStatus({ queue: [], acks: [], lastBlock: { reason: "offline", code: null } });
    expect(s.blocked).toBeNull();
    const t = summarizeSyncStatus({
      queue: [queued("a", "failed")],
      acks: [],
      lastBlock: { reason: "auth", code: "UNAUTHORIZED" },
    });
    expect(t).toMatchObject({ blocked: "auth", blockedCode: "UNAUTHORIZED", waiting: 1 });
  });

  it("scopes to the signed-in learner on a shared device", () => {
    const other = queued("x", "pending", { payload: { student_ref: "S2" }, entityKey: "student:S2|item:x" });
    const s = summarizeSyncStatus({
      queue: [queued("a", "pending"), other],
      acks: [ack("y", "attempt.submitted", "applied", "S2")],
      studentRef: "S1",
    });
    expect(s.savedOnDevice).toBe(1);
    expect(s.serverConfirmed).toBe(0);
  });
});

describe("ack ledger", () => {
  it("is bounded, keeps the newest, de-duplicates ids, and forgets a purged learner", async () => {
    const ledger = new AckLedger(new MemoryStore(), 3);
    await ledger.record([ack("a", "attempt.submitted", "applied"), ack("b", "attempt.submitted", "applied")]);
    await ledger.record([ack("c", "attempt.submitted", "applied", "S2"), ack("d", "attempt.submitted", "applied")]);
    await ledger.record([ack("b", "attempt.submitted", "duplicate")]);
    const ids = (await ledger.all()).map((r) => r.clientEventId);
    expect(ids).toEqual(["c", "d", "b"]);
    await ledger.forget("S2");
    expect((await ledger.all()).map((r) => r.clientEventId)).toEqual(["d", "b"]);
  });

  it("persists and clears the last drain block", async () => {
    const ledger = new AckLedger(new MemoryStore());
    expect(await ledger.lastBlock()).toBeNull();
    await ledger.setBlock({ reason: "permission", code: "CONSENT_REQUIRED" });
    expect(await ledger.lastBlock()).toEqual({ reason: "permission", code: "CONSENT_REQUIRED" });
    await ledger.setBlock(null);
    expect(await ledger.lastBlock()).toBeNull();
  });
});
