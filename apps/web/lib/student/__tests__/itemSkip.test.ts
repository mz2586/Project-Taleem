// "Skip this one" for an item this phone cannot render (a match/sort with an unusable left_count):
// online it moves to the next item (or re-plans after the last), offline it advances the player and
// the checkpoint — and in both cases no answer is sent or queued.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ItemInteraction } from "@/components/student/ItemInteraction";

import { formatNumber } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import { CheckpointStore } from "../../offline/checkpoint";
import { MemoryStore } from "../../offline/kv";
import { ProgressStore } from "../../offline/progress";
import { SyncQueue } from "../../offline/syncQueue";
import type { OfflineContent, OfflineItem } from "../../offline/types";
import { initialPlayerState, playerReducer, skipItem, type PlayerState } from "../lessonPlayer";
import { createOfflineRunner, initialOfflineState, offlineItem, offlineReducer } from "../offlinePlayer";

const broken = (ref: string): OfflineItem => ({ item_ref: ref, objective_code: "OBJ", prompt: { ur: "جوڑیں" }, options: ["a", "b"], hints: [], kind: "match" });
const choose = (ref: string): OfflineItem => ({ item_ref: ref, objective_code: "OBJ", prompt: { ur: "چنیں" }, options: ["x", "y"], hints: [] });

function content(items: OfflineItem[]): OfflineContent {
  return { lesson_id: "L", objective_code: "OBJ", title: {}, explanation: {}, worked_example_steps: [], practice_items: items, homework_items: [], assessment_formative: [], summative_mentor_mediated: true };
}

function render(onSkip?: () => void, options = ["a", "b"]): string {
  const t = createTranslator("ur");
  return renderToStaticMarkup(
    createElement(ItemInteraction, {
      item: { item_ref: "m1", kind: "match", options },
      t,
      formatNumber: (n: number) => formatNumber(n, "ur"),
      submitLabel: "x",
      onSubmit: () => undefined,
      ...(onSkip ? { onSkip } : {}),
    }),
  );
}

describe("skip button", () => {
  it("is offered for an unrenderable item when the page can skip", () => {
    const html = render(() => undefined);
    expect(html).toContain('role="alert"');
    expect(html).toMatch(/<button[^>]*aria-label="اسے چھوڑ دیں"/);
  });

  it("is absent without onSkip, and never shown for a renderable item", () => {
    expect(render()).not.toContain("اسے چھوڑ دیں");
    const ok = renderToStaticMarkup(
      createElement(ItemInteraction, {
        item: { item_ref: "m1", kind: "match", options: ["a", "b"], left_count: 1 },
        t: createTranslator("ur"),
        formatNumber: String,
        submitLabel: "x",
        onSubmit: () => undefined,
        onSkip: () => undefined,
      }),
    );
    expect(ok).not.toContain("اسے چھوڑ دیں");
  });
});

describe("online skip", () => {
  function asking(itemIndex: number): PlayerState {
    const teach = { utterances: [], items: [broken("m1"), choose("c2")].map((i) => ({ item_ref: i.item_ref, prompt: i.prompt, options: i.options })) };
    return { ...playerReducer(initialPlayerState, { type: "taught", objective: "OBJ", teach }), itemIndex };
  }

  it("moves to the next item, or re-plans after the last, without an answer", () => {
    const s = asking(0);
    expect(s.phase).toBe("asking");
    expect(skipItem(s)).toBe("nextItem");
    const next = playerReducer(s, { type: "nextItem" });
    expect(next).toMatchObject({ itemIndex: 1, phase: "asking", answer: null });
    expect(skipItem(asking(1))).toBe("plan");
  });
});

describe("offline skip", () => {
  it("advances the player; the last skipped item ends the lesson with nothing saved", () => {
    let s = offlineReducer(initialOfflineState, { type: "load", content: content([broken("m1"), choose("c2")]) });
    expect(s.player.phase).toBe("asking");
    s = offlineReducer(s, { type: "skipped" });
    expect(offlineItem(s)?.item_ref).toBe("c2");
    expect(s).toMatchObject({ savedCount: 0, justSaved: false, done: false });
    const end = offlineReducer(offlineReducer(initialOfflineState, { type: "load", content: content([broken("m1")]) }), { type: "skipped" });
    expect(end).toMatchObject({ done: true, savedCount: 0 });
  });

  it("moves only the checkpoint: no progress event, no queued attempt", async () => {
    const store = new MemoryStore();
    const progress = new ProgressStore(store, () => 1);
    const checkpoints = new CheckpointStore(store, () => 1);
    const queue = new SyncQueue(store, () => 1);
    const c = content([broken("m1"), choose("c2")]);
    const runner = createOfflineRunner({ getLesson: async () => c, progress, checkpoints, queue }, "stu_syn");
    const opened = (await runner.open("L"))!;
    const before = (await progress.forStudent("stu_syn")).length;
    const cp = await runner.skip({ checkpoint: opened.checkpoint, item: c.practice_items[0]! });
    expect(cp.item_index).toBe(1);
    expect(await queue.all()).toHaveLength(0);
    expect(await progress.forStudent("stu_syn")).toHaveLength(before);
    expect((await runner.open("L"))?.resumeAt).toBe(1);
  });
});
