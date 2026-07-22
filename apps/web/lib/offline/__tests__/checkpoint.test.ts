import { describe, expect, it } from "vitest";

import { CheckpointStore } from "../checkpoint";
import { MemoryStore } from "../kv";

describe("session checkpointing + resume", () => {
  it("starts, advances, and resumes at the last position", async () => {
    const store = new MemoryStore();
    let t = 1;
    const cps = new CheckpointStore(store, () => t++);

    const cp0 = await cps.start({ student_ref: "S1", lesson_id: "L1", objective_code: "O1" });
    expect(cp0.item_index).toBe(0);

    const cp1 = await cps.advance(cp0, "p1");
    const cp2 = await cps.advance(cp1, "p2");
    expect(cp2.item_index).toBe(2);
    expect(cp2.completed_item_refs).toEqual(["p1", "p2"]);

    // Resume: reload from storage and continue where we left off.
    const resumed = await cps.get(cp0.session_id);
    expect(resumed?.item_index).toBe(2);
    expect(resumed?.completed_item_refs).toEqual(["p1", "p2"]);
  });

  it("does not double-count re-advancing the same item", async () => {
    const store = new MemoryStore();
    const cps = new CheckpointStore(store, () => 1);
    const cp = await cps.start({ student_ref: "S1", lesson_id: "L1", objective_code: "O1" });
    const a = await cps.advance(cp, "p1");
    const b = await cps.advance(a, "p1");
    expect(b.completed_item_refs).toEqual(["p1"]);
  });

  it("finds the latest resumable checkpoint for a learner + lesson", async () => {
    const store = new MemoryStore();
    let t = 1;
    const cps = new CheckpointStore(store, () => t++);
    const first = await cps.start({ student_ref: "S1", lesson_id: "L1", objective_code: "O1" });
    await cps.advance(first, "p1");
    const second = await cps.start({ student_ref: "S1", lesson_id: "L1", objective_code: "O1" });

    const latest = await cps.latestForLesson("S1", "L1");
    expect(latest?.session_id).toBe(second.session_id);
  });

  it("clears a checkpoint on completion", async () => {
    const store = new MemoryStore();
    const cps = new CheckpointStore(store, () => 1);
    const cp = await cps.start({ student_ref: "S1", lesson_id: "L1", objective_code: "O1" });
    await cps.clear(cp.session_id);
    expect(await cps.get(cp.session_id)).toBeUndefined();
  });
});
