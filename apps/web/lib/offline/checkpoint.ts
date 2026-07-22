// Session checkpointing + resume (Phase 6.2A).
//
// The client is the durability layer for an in-flight lesson (server sessions are in-memory). After
// each item, the position is checkpointed locally; on reopen the learner can resume where they left
// off. 6.2A is LOCAL resume only — no durable server-side session replay (that is 6.2B).

import { uuid7 } from "./ids";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { SessionCheckpoint } from "./types";

export class CheckpointStore {
  constructor(
    private readonly store: KVStore,
    private readonly now: () => number = Date.now,
  ) {}

  // Start a fresh checkpoint for a lesson; returns the new session id.
  async start(input: {
    student_ref: string;
    lesson_id: string;
    objective_code: string;
  }): Promise<SessionCheckpoint> {
    const cp: SessionCheckpoint = {
      session_id: uuid7(this.now()),
      student_ref: input.student_ref,
      lesson_id: input.lesson_id,
      objective_code: input.objective_code,
      item_index: 0,
      completed_item_refs: [],
      updated_at: this.now(),
    };
    await this.save(cp);
    return cp;
  }

  async save(cp: SessionCheckpoint): Promise<void> {
    await this.store.put<SessionCheckpoint>(STORES.checkpoints, cp.session_id, {
      ...cp,
      updated_at: this.now(),
    });
  }

  // Advance the checkpoint after completing an item.
  async advance(cp: SessionCheckpoint, itemRef: string): Promise<SessionCheckpoint> {
    const completed = cp.completed_item_refs.includes(itemRef)
      ? cp.completed_item_refs
      : [...cp.completed_item_refs, itemRef];
    const next: SessionCheckpoint = {
      ...cp,
      item_index: cp.item_index + 1,
      completed_item_refs: completed,
      updated_at: this.now(),
    };
    await this.save(next);
    return next;
  }

  async get(sessionId: string): Promise<SessionCheckpoint | undefined> {
    return this.store.get<SessionCheckpoint>(STORES.checkpoints, sessionId);
  }

  // The most recent resumable checkpoint for a learner + lesson (for the "resume?" prompt).
  async latestForLesson(
    studentRef: string,
    lessonId: string,
  ): Promise<SessionCheckpoint | undefined> {
    const all = await this.store.getAll<SessionCheckpoint>(STORES.checkpoints);
    return all
      .filter((c) => c.student_ref === studentRef && c.lesson_id === lessonId)
      .sort((a, b) => b.updated_at - a.updated_at)[0];
  }

  async clear(sessionId: string): Promise<void> {
    await this.store.delete(STORES.checkpoints, sessionId);
  }
}
