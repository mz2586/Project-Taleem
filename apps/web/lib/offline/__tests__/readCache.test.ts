import { describe, expect, it } from "vitest";

import { MemoryStore } from "../kv";
import { ReadCache } from "../readCache";

describe("offline dashboard read cache", () => {
  it("stores and returns a labelled snapshot", async () => {
    const store = new MemoryStore();
    const reads = new ReadCache(store, () => 5000);
    await reads.put("S1", "/v1/learning/students/S1/today", { mastery_summary: { total: 3 } });
    const cached = await reads.get<{ mastery_summary: { total: number } }>(
      "S1",
      "/v1/learning/students/S1/today",
    );
    expect(cached?.body.mastery_summary.total).toBe(3);
    expect(cached?.fetched_at).toBe(5000); // "as of" timestamp for honest offline UI
  });

  it("clears a learner's cached reads without touching another learner", async () => {
    const store = new MemoryStore();
    const reads = new ReadCache(store, () => 1);
    await reads.put("S1", "/today", { a: 1 });
    await reads.put("S2", "/today", { a: 2 });
    await reads.clearStudent("S1");
    expect(await reads.get("S1", "/today")).toBeUndefined();
    expect(await reads.get("S2", "/today")).toBeDefined();
  });
});
