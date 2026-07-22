// Offline browser simulation: exercises the real IndexedDB code path via fake-indexeddb, so the
// storage + download + resume flow is validated with browser storage semantics (no real browser).
import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it } from "vitest";

import { CheckpointStore } from "../checkpoint";
import { IdbStore, STORES } from "../kv";
import { DownloadManager } from "../packages";
import { contentHash } from "../sha256";
import type { OfflineContent, OfflinePackage } from "../types";

// Clear every store between tests (deleteDatabase would block on still-open connections).
async function resetIndexedDb(): Promise<void> {
  const store = new IdbStore(indexedDB);
  for (const s of Object.values(STORES)) {
    await store.clear(s);
  }
}

function content(): OfflineContent {
  return {
    lesson_id: "L-frac",
    objective_code: "MATH-G4-FR-01",
    title: { ur: "کسر", en: "Fractions" },
    explanation: { ur: "حصہ", en: "A fraction is an equal part." },
    worked_example_steps: ["one"],
    practice_items: [
      { item_ref: "p1", objective_code: "MATH-G4-FR-01", prompt: { en: "?" }, options: ["a"], hints: [] },
    ],
    homework_items: [],
    assessment_formative: [],
    summative_mentor_mediated: true,
  };
}

async function pkg(): Promise<OfflinePackage> {
  const c = content();
  const hash = await contentHash(c);
  return {
    manifest: {
      package_id: "pkg/L-frac",
      lesson_id: "L-frac",
      objective_code: "MATH-G4-FR-01",
      version: hash.slice(0, 12),
      content_hash: hash,
      assets: [{ ref: "L-frac/content.json", kind: "content", sha256: hash, bytes: 50 }],
      total_bytes: 50,
      created_at_ms: 0,
    },
    content: c,
  };
}

describe("IndexedDB store (offline browser simulation)", () => {
  beforeEach(async () => {
    await resetIndexedDb();
  });

  it("round-trips values across object stores", async () => {
    const store = new IdbStore(indexedDB);
    await store.put(STORES.prefs, "locale", { value: "ur" });
    expect(await store.get(STORES.prefs, "locale")).toEqual({ value: "ur" });
    await store.put(STORES.prefs, "theme", { value: "light" });
    expect(await store.getAll(STORES.prefs)).toHaveLength(2);
    await store.delete(STORES.prefs, "locale");
    expect(await store.get(STORES.prefs, "locale")).toBeUndefined();
    await store.clear(STORES.prefs);
    expect(await store.getAll(STORES.prefs)).toHaveLength(0);
  });

  it("installs a package and renders it fully offline (persisted in IndexedDB)", async () => {
    const store = new IdbStore(indexedDB);
    const p = await pkg();
    const mgr = new DownloadManager({ store, fetchPackage: async () => p, now: () => 1 });
    await mgr.download("L-frac");

    // Simulate a fresh open (new IdbStore instance over the same database) — data persists.
    const reopened = new IdbStore(indexedDB);
    const mgr2 = new DownloadManager({ store: reopened, fetchPackage: async () => p, now: () => 2 });
    const lesson = await mgr2.getLesson("L-frac");
    expect(lesson?.lesson_id).toBe("L-frac");
    expect(await mgr2.isCurrent(p.manifest)).toBe(true);
  });

  it("persists a checkpoint and resumes it after reopening the database", async () => {
    let t = 1;
    const store = new IdbStore(indexedDB);
    const cps = new CheckpointStore(store, () => t++);
    const cp = await cps.start({ student_ref: "S1", lesson_id: "L-frac", objective_code: "O1" });
    await cps.advance(cp, "p1");

    const reopened = new CheckpointStore(new IdbStore(indexedDB), () => t++);
    const latest = await reopened.latestForLesson("S1", "L-frac");
    expect(latest?.item_index).toBe(1);
    expect(latest?.completed_item_refs).toEqual(["p1"]);
  });
});
