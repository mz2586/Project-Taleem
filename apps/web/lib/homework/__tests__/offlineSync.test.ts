// Offline homework submission (OFFLINE_SYNC_SPEC.md `homework.submitted`; HOMEWORK_AND_MARKING_CONTRACT
// §2). Checked, in the node suite (no jsdom): offline Send queues the answer and says only "Saved on
// this phone — will send when online"; a dropped connection queues too; the queue survives a reload;
// one answer per item travels; the sync drain records the server's result (without the child's text)
// and the item then shows it ("Checked by Taleem", "Saved — compare", "Sent to your teacher"); a
// conflict is surfaced with a gentle reason and the writing stays; a permission refusal is held; the
// draft is wiped only after server confirmation and only if unchanged; a wipe removes queued copies.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import { HomeworkItemCard } from "@/components/student/HomeworkItemCard";

import { formatNumber } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import { createOfflineClient, summarizeSyncStatus } from "../../offline";
import type { BatchResult, ItemResult, OfflineClient, SyncDelta } from "../../offline";
import { MemoryStore, type KVStore } from "../../offline/kv";
import { forgetQueuedHomework, wipeConfirmedDrafts } from "../../student/offlineClient";
import { ApiError } from "../../student/types";
import { localDrafts, type DraftStore } from "../drafts";
import {
  CONFIRMED_MESSAGE_MS,
  draftKeyOfDelta,
  homeworkDraftKey,
  homeworkKey,
  homeworkPayload,
  homeworkSyncFor,
  type HomeworkRef,
  type HomeworkSyncView,
} from "../offlineQueue";
import { afterSent, sendHomework, sendOutcomeKey, submitGate, syncMessageKey, type HomeworkItemView } from "../student";
import { flattenSubmitView } from "../wire";

const ref: HomeworkRef = { studentRef: "stu_1", target: { source: "self_paced", objectiveCode: "MATH-G4-FR-01" }, itemRef: "hw-short" };
const assignmentRef: HomeworkRef = { studentRef: "stu_1", target: { source: "assignment", assignmentId: "asg_1" }, itemRef: "hw-long" };

function item(over: Partial<HomeworkItemView> = {}): HomeworkItemView {
  return {
    assignmentId: "",
    itemRef: "hw-short",
    prompt: { text: "Write about a fraction", locale: "en" },
    hints: [],
    maxChars: 200,
    state: "not_started",
    sentText: null,
    feedback: null,
    outcome: null,
    source: "self_paced",
    marking: "self_check",
    reviewedBy: null,
    compare: null,
    canRetry: false,
    attempt: 0,
    ...over,
  };
}

/** The server's nested submit view, as `POST …:submit` and a sync result return it. */
function serverView(over: { state?: string; outcome?: string | null; marking?: string; reviewed_by?: string | null; compare?: unknown; attempt?: number } = {}) {
  const state = over.state ?? "submitted";
  return {
    source: "self_paced",
    assignment_id: null,
    objective_code: "MATH-G4-FR-01",
    item_ref: "hw-short",
    marking: over.marking ?? "self_check",
    state,
    can_retry: false,
    compare: over.compare ?? null,
    submission: {
      submission_id: "sub_1",
      state,
      text: "my answer",
      attempt: over.attempt ?? 1,
      outcome: over.outcome ?? null,
      reviewed_by: over.reviewed_by ?? null,
      can_retry: false,
    },
  };
}

type Answer = (d: SyncDelta) => Omit<ItemResult, "clientEventId" | "version">;

function client(store: KVStore, answer: Answer | Error): { c: OfflineClient; posted: SyncDelta[][] } {
  const posted: SyncDelta[][] = [];
  const c = createOfflineClient({
    store,
    fetchPackage: async () => {
      throw new Error("not used");
    },
    postBatch: async (_cursor, deltas): Promise<BatchResult> => {
      posted.push(deltas);
      if (answer instanceof Error) throw answer;
      return { cursor: 1, results: deltas.map((d) => ({ clientEventId: d.clientEventId, version: 1, ...answer(d) })) };
    },
    currentLearner: () => "stu_1",
    onSettled: async (settled) => wipeConfirmedDrafts(settled),
    nodeEnv: "test",
  });
  return { c, posted };
}

async function queueAnswer(c: OfflineClient, text = "my answer", where: HomeworkRef = ref, serverAttempt = 0) {
  return c.sync.queue.enqueueHomework(homeworkPayload({ ...where, text, serverAttempt, now: 1_700_000_000_000 }));
}

async function syncView(c: OfflineClient, where: HomeworkRef = ref, now = Date.now()): Promise<HomeworkSyncView | null> {
  return homeworkSyncFor(homeworkKey(where), await c.sync.queue.all(), await c.sync.homework.all(), now);
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("offline Send queues the answer", () => {
  const base = { text: "my answer", maxChars: 200, state: "not_started" as const, draftKey: homeworkDraftKey(ref), drafts: localDrafts };

  it("offline: queued, draft kept, the server never called, and the child is told only 'saved on this phone'", async () => {
    let sent = 0;
    const queued: string[] = [];
    const out = await sendHomework({
      ...base,
      online: false,
      send: async () => {
        sent++;
        return undefined;
      },
      queue: async (body) => {
        queued.push(body.text);
      },
    });
    expect(out).toEqual({ kind: "queued", text: "my answer" });
    expect(sent).toBe(0);
    expect(queued).toEqual(["my answer"]);
    expect(localDrafts.read(base.draftKey)).toBe("my answer");
    expect(sendOutcomeKey(out)).toBe("student.homework.result.queued");
    expect(createTranslator("en")(sendOutcomeKey(out))).toBe("Saved on this phone — will send when online.");
  });

  it("a connection that drops during the send queues the answer too", async () => {
    const queued: string[] = [];
    const out = await sendHomework({
      ...base,
      online: true,
      send: async () => {
        throw new ApiError(0, {});
      },
      queue: async (body) => {
        queued.push(body.text);
      },
    });
    expect(out.kind).toBe("queued");
    expect(queued).toEqual(["my answer"]);
  });

  it("an empty answer is never queued; a queue that fails is reported as only kept", async () => {
    const queued: string[] = [];
    const empty = await sendHomework({ ...base, text: "  ", online: false, send: async () => undefined, queue: async (b) => void queued.push(b.text) });
    expect(empty.kind).toBe("invalid");
    const failing = await sendHomework({
      ...base,
      online: false,
      send: async () => undefined,
      queue: async () => {
        throw new Error("quota");
      },
    });
    expect(failing).toEqual({ kind: "offline", kept: true });
    expect(queued).toEqual([]);
  });

  it("without a queue the old behaviour stands: kept, not sent, Send disabled offline", async () => {
    const out = await sendHomework({ ...base, online: false, send: async () => undefined });
    expect(out).toEqual({ kind: "offline", kept: true });
    expect(submitGate({ text: "x", maxChars: 200, state: "not_started", sending: false, online: false })).toMatchObject({
      canSend: false,
      reason: "student.homework.reason.offline",
    });
    expect(submitGate({ text: "x", maxChars: 200, state: "not_started", sending: false, online: false }).note).toBeUndefined();
  });

  it("with a queue, Send stays enabled offline with a note saying where the answer goes", () => {
    expect(submitGate({ text: "x", maxChars: 200, state: "not_started", sending: false, online: false, canQueue: true })).toEqual({
      canSend: true,
      count: 1,
      over: false,
      reason: null,
      note: "student.homework.reason.offlineQueue",
    });
    // A marked answer is still final, an empty one still refused.
    expect(submitGate({ text: "x", maxChars: 200, state: "marked", sending: false, online: false, canQueue: true }).canSend).toBe(false);
    expect(submitGate({ text: "", maxChars: 200, state: "not_started", sending: false, online: false, canQueue: true }).reason).toBe(
      "student.homework.reason.empty",
    );
  });
});

describe("the queued delta", () => {
  it("carries the contract payload, and the attempt the child was making", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "applied" }));
    const d = await queueAnswer(c, "my answer", assignmentRef, 2);
    expect(d.type).toBe("homework.submitted");
    expect(d.entityKey).toBe("student:stu_1|homework:assignment:asg_1|item:hw-long");
    expect(d.payload).toEqual({
      student_ref: "stu_1",
      source: "assignment",
      assignment_id: "asg_1",
      item_ref: "hw-long",
      text: "my answer",
      submission_key: d.clientEventId,
      attempt: 3,
      submitted_at: 1_700_000_000_000,
    });
    expect(draftKeyOfDelta(d)).toBe(homeworkDraftKey(assignmentRef));
  });

  it("one answer per item travels: a newer Send replaces the queued one", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "applied" }));
    await queueAnswer(c, "first");
    await queueAnswer(c, "second");
    await queueAnswer(c, "other item", assignmentRef);
    const texts = (await c.sync.queue.all()).map((d) => d.payload["text"]).sort();
    expect(texts).toEqual(["other item", "second"]);
  });

  it("survives a reload: a new client over the same store still shows 'saved on this phone'", async () => {
    const store = new MemoryStore();
    await queueAnswer(client(store, new Error("offline")).c);
    const reloaded = client(store, new Error("offline")).c;
    expect(await syncView(reloaded)).toMatchObject({ kind: "queued", held: false });
    expect(syncMessageKey(await syncView(reloaded), item())).toBe("student.homework.result.queued");
    const summary = summarizeSyncStatus({ queue: await reloaded.sync.queue.all(), acks: [], studentRef: "stu_1" });
    expect(summary).toMatchObject({ savedOnDevice: 1, waiting: 1, serverConfirmed: 0 });
  });

  it("a failed drain (still offline) keeps it queued", async () => {
    const { c } = client(new MemoryStore(), new Error("Failed to fetch"));
    await queueAnswer(c);
    const summary = await c.sync.drain();
    expect(summary.blocked).toBe("offline");
    expect(await syncView(c)).toMatchObject({ kind: "queued" });
  });
});

describe("after sync: the server's result", () => {
  it("auto-marked: confirmed, 'Checked by Taleem', server-confirmed, no text in the ledger, draft wiped", async () => {
    const { c, posted } = client(new MemoryStore(), () => ({ status: "applied", result: serverView({ state: "marked", outcome: "met", marking: "auto", reviewed_by: "auto" }) }));
    localDrafts.write(homeworkDraftKey(ref), "my answer");
    await queueAnswer(c);
    await c.sync.drain();
    expect(posted[0]?.[0]?.type).toBe("homework.submitted");
    const view = await syncView(c);
    expect(view?.kind).toBe("confirmed");
    expect(syncMessageKey(view, item({ marking: "auto" }))).toBe("student.homework.result.checked");
    const [record] = await c.sync.homework.all();
    expect(JSON.stringify(record)).not.toContain("my answer");
    expect(localDrafts.read(homeworkDraftKey(ref))).toBeNull();
    expect(await c.sync.queue.all()).toEqual([]);
    const summary = summarizeSyncStatus({ queue: [], acks: await c.sync.acks.all(), studentRef: "stu_1" });
    expect(summary.serverConfirmed).toBe(1);
    // The flattened result drives the same view model as an online send.
    const next = afterSent(item({ marking: "auto" }), { kind: "sent", submission: view?.kind === "confirmed" ? view.submission : null, text: "my answer" });
    expect(next).toMatchObject({ state: "marked", outcome: "met", reviewedBy: "auto", attempt: 1 });
  });

  it("self-check: 'Saved — compare' when the server sends a comparison; an assignment says 'sent to your teacher'", async () => {
    const compare = { sample_answer: { en: "Half of the roti" } };
    const { c } = client(new MemoryStore(), () => ({ status: "applied", result: serverView({ compare }) }));
    await queueAnswer(c);
    await c.sync.drain();
    const view = await syncView(c);
    expect(syncMessageKey(view, item())).toBe("student.homework.result.savedCompare");
    expect(syncMessageKey(view, item({ source: "assignment", marking: null }))).toBe("student.homework.result.sent");
  });

  it("a duplicate (the server already had it) is confirmed the same way", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "duplicate", result: serverView() }));
    localDrafts.write(homeworkDraftKey(ref), "my answer");
    await queueAnswer(c);
    await c.sync.drain();
    expect((await syncView(c))?.kind).toBe("confirmed");
    expect(localDrafts.read(homeworkDraftKey(ref))).toBeNull();
  });

  it("a draft the child changed after pressing Send is kept", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "applied", result: serverView() }));
    await queueAnswer(c, "my answer");
    localDrafts.write(homeworkDraftKey(ref), "my answer, and a bit more");
    await c.sync.drain();
    expect(localDrafts.read(homeworkDraftKey(ref))).toBe("my answer, and a bit more");
  });

  it("an old confirmation stops being said on the item (the list shows the state)", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "applied", result: serverView() }));
    await queueAnswer(c);
    await c.sync.drain();
    expect(await syncView(c, ref, Date.now() + CONFIRMED_MESSAGE_MS + 1)).toBeNull();
  });
});

describe("conflicts are surfaced, never dropped", () => {
  const cases: Array<[string, string, Partial<HomeworkItemView>]> = [
    ["NOT_AVAILABLE", "student.homework.sync.gone", {}],
    ["SUBMISSION_MARKED", "student.homework.result.finalChecked", {}],
    ["SUBMISSION_MARKED", "student.homework.result.final", { source: "assignment" }],
    ["SUBMISSION_SUPERSEDED", "student.homework.sync.superseded", {}],
    ["LESSON_ASSIGNED", "student.homework.sync.assigned", {}],
    ["SHARING_REQUIRED", "student.homework.result.sharingOff", { source: "assignment" }],
    ["INVALID", "student.homework.result.invalid", {}],
    ["BUSY", "student.homework.sync.tryAgain", {}],
  ];
  it.each(cases)("%s → a gentle message, the writing kept on the phone", async (reason, key, over) => {
    const { c } = client(new MemoryStore(), () => ({ status: "conflict", reason }));
    localDrafts.write(homeworkDraftKey(ref), "my answer");
    await queueAnswer(c);
    await c.sync.drain();
    const view = await syncView(c);
    expect(view).toMatchObject({ kind: "conflict", reason });
    expect(syncMessageKey(view, item(over))).toBe(key);
    expect(localDrafts.read(homeworkDraftKey(ref))).toBe("my answer");
    const [dead] = await c.sync.queue.all();
    expect(dead).toMatchObject({ syncState: "dead", lastError: `conflict: ${reason}` });
  });

  it("every conflict message names that the writing is still there (en + ur)", () => {
    for (const locale of ["en", "ur"] as const) {
      const t = createTranslator(locale);
      for (const key of ["student.homework.sync.gone", "student.homework.sync.superseded", "student.homework.sync.assigned", "student.homework.sync.tryAgain"] as const) {
        expect(t(key)).not.toBe(key);
        expect(t(key).length).toBeGreaterThan(10);
      }
    }
  });

  it("sending again after a conflict replaces the dead copy and is queued again", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "conflict", reason: "BUSY" }));
    await queueAnswer(c);
    await c.sync.drain();
    await queueAnswer(c, "try again");
    expect(await syncView(c)).toMatchObject({ kind: "queued" });
    expect((await c.sync.queue.all()).length).toBe(1);
  });

  it("a consent refusal holds the answer (no retry loop) and says it waits for a grown-up", async () => {
    const { c, posted } = client(new MemoryStore(), Object.assign(new Error("403"), { status: 403, problem: { code: "CONSENT_REQUIRED" } }));
    await queueAnswer(c);
    await c.sync.drain();
    await c.sync.drain();
    expect(posted.length).toBe(1);
    const view = await syncView(c);
    expect(view).toMatchObject({ kind: "queued", held: true });
    expect(syncMessageKey(view, item())).toBe("student.homework.sync.held");
  });
});

describe("wipes", () => {
  it("forgetting a learner removes their queued answers and results, and only theirs", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "applied", result: serverView() }));
    await queueAnswer(c);
    await c.sync.drain();
    await queueAnswer(c, "pending", assignmentRef);
    await c.sync.queue.enqueueHomework(homeworkPayload({ ...ref, studentRef: "stu_2", text: "sister", serverAttempt: 0, now: 1 }));
    await forgetQueuedHomework(c, "stu_1");
    expect((await c.sync.queue.all()).map((d) => d.payload["student_ref"])).toEqual(["stu_2"]);
    expect(await c.sync.homework.all()).toEqual([]);
    await forgetQueuedHomework(c, undefined);
    expect(await c.sync.queue.all()).toEqual([]);
  });

  it("a server purge clears the learner's homework results too", async () => {
    const { c } = client(new MemoryStore(), () => ({ status: "applied", result: serverView() }));
    await queueAnswer(c);
    await c.sync.drain();
    await c.purgeStudent("stu_1");
    expect(await c.sync.homework.all()).toEqual([]);
  });
});

describe("wire and markup", () => {
  it("flattens the server's nested submit view into one submission", () => {
    expect(flattenSubmitView(serverView({ state: "marked", outcome: "not_yet", marking: "auto", reviewed_by: "auto" }))).toMatchObject({
      submission_id: "sub_1",
      state: "marked",
      outcome: "not_yet",
      marking: "auto",
      reviewed_by: "auto",
      attempt: 1,
    });
    expect(flattenSubmitView({ submission_id: "s", state: "submitted" })).toEqual({ submission_id: "s", state: "submitted" });
    expect(flattenSubmitView(null)).toBeNull();
  });

  const noDrafts: DraftStore = { read: () => null, write: () => true, clear: () => undefined };
  function render(sync: HomeworkSyncView | null, online = true): string {
    return renderToStaticMarkup(
      createElement(HomeworkItemCard, {
        item: item({ state: "submitted", sentText: "my answer", attempt: 1 }),
        position: 1,
        t: createTranslator("en"),
        formatNumber: (n: number) => formatNumber(n, "en"),
        online,
        draftKey: "k",
        drafts: noDrafts,
        send: async () => undefined,
        onSent: () => undefined,
        queue: async () => undefined,
        sync,
      }),
    );
  }

  it("a queued item says 'Saved on this phone — will send when online' in its status line", () => {
    const html = render({ kind: "queued", held: false, clientEventId: "e1" });
    expect(html).toMatch(/role="status"[^>]*data-sync="queued"[^>]*>Saved on this phone — will send when online\./);
  });

  it("a conflicted item shows its gentle reason; offline with a queue, Send is enabled with a note", () => {
    expect(render({ kind: "conflict", clientEventId: "e1", reason: "NOT_AVAILABLE" })).toContain("This homework is no longer available");
    const offline = render(null, false);
    expect(offline).toContain('data-note="offline-queue"');
    expect(/<button[^>]*type="submit"[^>]*>/.exec(offline)?.[0]).not.toContain("disabled");
  });
});
