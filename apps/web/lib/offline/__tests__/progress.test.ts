import { describe, expect, it } from "vitest";

import { MemoryStore } from "../kv";
import { ProgressStore } from "../progress";

describe("offline progress persistence", () => {
  it("records events durably and summarises a lesson", async () => {
    const store = new MemoryStore();
    let t = 1000;
    const progress = new ProgressStore(store, () => t++);

    await progress.record({
      student_ref: "S1",
      lesson_id: "L1",
      objective_code: "O1",
      kind: "lesson_opened",
    });
    await progress.record({
      student_ref: "S1",
      lesson_id: "L1",
      objective_code: "O1",
      kind: "item_attempted",
      item_ref: "p1",
      selected_option: 0,
    });
    await progress.record({
      student_ref: "S1",
      lesson_id: "L1",
      objective_code: "O1",
      kind: "item_attempted",
      item_ref: "p1", // repeat of same item — counted once
      selected_option: 1,
    });

    const summary = await progress.lessonSummary("S1", "L1");
    expect(summary.opened).toBe(true);
    expect(summary.attempted).toBe(1);
    expect(summary.completed).toBe(false);
  });

  it("scopes events by student (no cross-learner leakage)", async () => {
    const store = new MemoryStore();
    const progress = new ProgressStore(store, () => 1);
    await progress.record(
      { student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "lesson_opened" },
      "id-a",
    );
    await progress.record(
      { student_ref: "S2", lesson_id: "L1", objective_code: "O1", kind: "lesson_opened" },
      "id-b",
    );
    expect(await progress.forStudent("S1")).toHaveLength(1);
    expect(await progress.forStudent("S2")).toHaveLength(1);
  });

  it("uses the supplied client_event_id as the record key (idempotent re-record)", async () => {
    const store = new MemoryStore();
    const progress = new ProgressStore(store, () => 1);
    await progress.record(
      { student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "lesson_completed" },
      "fixed-id",
    );
    await progress.record(
      { student_ref: "S1", lesson_id: "L1", objective_code: "O1", kind: "lesson_completed" },
      "fixed-id",
    );
    expect(await progress.all()).toHaveLength(1);
  });
});
