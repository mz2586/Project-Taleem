// Install -> play -> queue -> resume, over the real IndexedDB code path (fake-indexeddb), with a
// synthetic signed package. Ends with the queue draining and the sync summary moving the answers
// from "saved on this phone" to "server confirmed".
import "fake-indexeddb/auto";

import { beforeEach, describe, expect, it } from "vitest";

import { createOfflineClient, summarizeSyncStatus } from "../../offline";
import { IdbStore, STORES } from "../../offline/kv";
import type { BatchResult, SyncDelta } from "../../offline/types";
import { createLibrary } from "../offlineLibrary";
import {
  canShowHint,
  contentLocale,
  createOfflineRunner,
  initialOfflineState,
  offlineItem,
  offlineReducer,
  playableItems,
  toTeachView,
  type OfflinePlayerState,
} from "../offlinePlayer";
import { SYNTHETIC_STUDENT, signedFixture, syntheticContent } from "./offlineFixtures";

async function resetIndexedDb(): Promise<void> {
  const store = new IdbStore(indexedDB);
  for (const s of Object.values(STORES)) await store.clear(s);
}

describe("offline reducer (reuses the lesson player)", () => {
  const content = syntheticContent();
  const loaded = offlineReducer(initialOfflineState, { type: "load", content });

  it("adapts the package: title, explanation and worked steps, then practice + formative items", () => {
    const teach = toTeachView(content);
    expect(teach.utterances.map((u) => u.text)).toEqual([
      "کسر کا تعارف",
      "کسر ایک برابر حصہ ہے۔",
      "Cut a roti into 4 equal parts.",
      "One part is 1/4.",
    ]);
    expect(teach.items.map((i) => [i.item_ref, i.hint_count])).toEqual([
      ["p1", 2],
      ["p2", 0],
      ["f1", 1],
    ]);
    expect(playableItems(content)).toHaveLength(3);
    expect(contentLocale(content)).toBe("ur");
  });

  it("presents one step at a time, then asks", () => {
    expect(loaded.player.phase).toBe("presenting");
    let s = offlineReducer(loaded, { type: "nextStep" });
    expect(s.player.step).toBe(1);
    s = offlineReducer(offlineReducer(offlineReducer(s, { type: "nextStep" }), { type: "nextStep" }), { type: "ready" });
    expect(s.player.phase).toBe("asking");
    expect(offlineItem(s)?.item_ref).toBe("p1");
  });

  function asking(): OfflinePlayerState {
    // Through the presentation the normal way: 3x next, then ready.
    let s = loaded;
    for (let i = 0; i < 3; i++) s = offlineReducer(s, { type: "nextStep" });
    return offlineReducer(s, { type: "ready" });
  }

  it("reveals the package's authored hints one rung at a time", () => {
    let s = asking();
    expect(canShowHint(s)).toBe(true);
    s = offlineReducer(s, { type: "hint" });
    expect(s.player.hints).toEqual(["Two equal parts."]);
    s = offlineReducer(s, { type: "hint" });
    expect(s.player.hints).toEqual(["Two equal parts.", "Look at the bottom number."]);
    expect(canShowHint(s)).toBe(false);
    expect(offlineReducer(s, { type: "hint" })).toBe(s);
  });

  it("an answer is saved and moves on — never graded on the phone", () => {
    let s = offlineReducer(asking(), { type: "hint" });
    s = offlineReducer(s, { type: "saved" });
    expect(s).toMatchObject({ savedCount: 1, justSaved: true, done: false });
    expect(s.player.itemIndex).toBe(1);
    expect(s.player.hints).toEqual([]);
    expect(s.player.answer).toBeNull();
    s = offlineReducer(offlineReducer(s, { type: "saved" }), { type: "saved" });
    expect(s).toMatchObject({ savedCount: 3, done: true });
  });

  it("resumes at the next unanswered item, skipping the presentation", () => {
    const s = offlineReducer(initialOfflineState, { type: "load", content, resumeAt: 2 });
    expect(s.player.phase).toBe("asking");
    expect(offlineItem(s)?.item_ref).toBe("f1");
    expect(offlineReducer(initialOfflineState, { type: "load", content, resumeAt: 3 }).done).toBe(true);
  });

  it("a lesson with no items ends after its steps", () => {
    const empty = { ...content, practice_items: [], assessment_formative: [] };
    let s = offlineReducer(initialOfflineState, { type: "load", content: empty });
    for (let i = 0; i < 3; i++) s = offlineReducer(s, { type: "nextStep" });
    expect(offlineReducer(s, { type: "ready" }).done).toBe(true);
  });

  it("the package carries no answer key", () => {
    expect(JSON.stringify(content)).not.toContain("correct_option");
  });
});

describe("install -> play -> queue -> resume (fake-indexeddb)", () => {
  beforeEach(async () => {
    await resetIndexedDb();
  });

  async function world() {
    const fx = await signedFixture();
    const store = new IdbStore(indexedDB);
    const sent: SyncDelta[] = [];
    let online = false;
    const client = createOfflineClient({
      store,
      fetchPackage: async () => fx.pkg,
      postBatch: async (cursor, deltas): Promise<BatchResult> => {
        if (!online) throw Object.assign(new Error("offline"), { status: 0 });
        sent.push(...deltas);
        return { cursor: cursor + deltas.length, results: deltas.map((d, i) => ({ clientEventId: d.clientEventId, status: "applied", version: i + 1 })) };
      },
      currentLearner: () => SYNTHETIC_STUDENT,
    });
    const library = createLibrary({
      store,
      listPackages: async () => ({ packages: [fx.pkg.manifest] }),
      fetchPackage: async () => fx.pkg,
      signingKeys: async () => ({ keys: [fx.key] }),
    });
    const runner = () =>
      createOfflineRunner(
        { getLesson: (id) => client.downloads.getLesson(id), progress: client.progress, checkpoints: client.checkpoints, queue: client.sync.queue },
        SYNTHETIC_STUDENT,
      );
    return { client, library, runner, sent, setOnline: (v: boolean) => (online = v) };
  }

  it("returns null for a lesson that is not installed", async () => {
    const { runner } = await world();
    expect(await runner().open("L-syn-frac")).toBeNull();
  });

  it("plays offline, queues each answer durably, resumes after a reload, then confirms on sync", async () => {
    const w = await world();
    await w.library.install("L-syn-frac");

    // Session 1 (offline): answer two items, then "close the app".
    const first = await w.runner().open("L-syn-frac");
    expect(first?.resumeAt).toBe(0);
    let cp = first!.checkpoint;
    const items = playableItems(first!.content);
    cp = await w.runner().answer({ checkpoint: cp, item: items[0]!, option: 0, hintsUsed: 1 });
    cp = await w.runner().answer({ checkpoint: cp, item: items[1]!, option: 1, hintsUsed: 0 });

    const queue = await w.client.sync.queue.all();
    expect(queue).toHaveLength(2);
    const p0 = queue.find((d) => d.payload["item_ref"] === "p1")!;
    expect(p0).toMatchObject({ type: "attempt.submitted", syncState: "pending" });
    expect(p0.payload).toMatchObject({
      student_ref: SYNTHETIC_STUDENT,
      objective_code: "SYN-G4-FR-01",
      item_ref: "p1",
      option: 0,
      hints_used: 1,
      session_id: "L-syn-frac",
      context: "practice",
    });
    // The evidence id is the local progress event's id — the same one reconcile would re-queue.
    const events = await w.client.progress.forStudent(SYNTHETIC_STUDENT);
    const attempt = events.find((e) => e.kind === "item_attempted" && e.item_ref === "p1")!;
    expect(p0.payload["evidence_id"]).toBe(attempt.client_event_id);

    // Offline drain keeps everything on the phone.
    await w.client.sync.drain();
    let summary = summarizeSyncStatus({ queue: await w.client.sync.queue.all(), acks: await w.client.sync.acks.all(), studentRef: SYNTHETIC_STUDENT });
    expect(summary).toMatchObject({ savedOnDevice: 2, serverConfirmed: 0 });

    // Session 2 (after a reload): resumes at the third item.
    const second = await w.runner().open("L-syn-frac");
    expect(second?.resumeAt).toBe(2);
    expect(second!.checkpoint.completed_item_refs).toEqual(["p1", "p2"]);
    const state = offlineReducer(initialOfflineState, { type: "load", content: second!.content, resumeAt: second!.resumeAt });
    expect(offlineItem(state)?.item_ref).toBe("f1");
    cp = await w.runner().answer({ checkpoint: second!.checkpoint, item: offlineItem(state)!, option: 0, hintsUsed: 0 });
    await w.runner().complete(cp);
    expect(await w.client.checkpoints.latestForLesson(SYNTHETIC_STUDENT, "L-syn-frac")).toBeUndefined();

    // Reconcile is idempotent: nothing new is queued for answers already in the queue.
    w.setOnline(false);
    expect((await w.client.sync.reconcile(SYNTHETIC_STUDENT)).enqueued).toBe(0);

    // Back online: the drain sends all three; the badge's model calls them server confirmed.
    w.setOnline(true);
    await w.client.sync.drain();
    expect(w.sent.map((d) => d.payload["item_ref"]).sort()).toEqual(["f1", "p1", "p2"]);
    summary = summarizeSyncStatus({ queue: await w.client.sync.queue.all(), acks: await w.client.sync.acks.all(), studentRef: SYNTHETIC_STUDENT });
    expect(summary).toMatchObject({ savedOnDevice: 0, serverConfirmed: 3 });
  });

  it("start again keeps already-saved answers queued", async () => {
    const w = await world();
    await w.library.install("L-syn-frac");
    const opened = await w.runner().open("L-syn-frac");
    const cp = await w.runner().answer({ checkpoint: opened!.checkpoint, item: playableItems(opened!.content)[0]!, option: 1, hintsUsed: 0 });
    const fresh = await w.runner().restart(cp);
    expect(fresh.item_index).toBe(0);
    expect(await w.client.sync.queue.all()).toHaveLength(1);
    expect((await w.runner().open("L-syn-frac"))?.resumeAt).toBe(0);
  });
});
