// Offline progress persistence (Phase 6.2A).
//
// Records the learner's local progress events (opened / attempted / completed) durably on-device.
// 6.2A is LOCAL ONLY — these events are persisted so they survive reload and drive resume; they are
// NOT synced to the server here (background sync + server grading arrive in 6.2B). Each event carries
// a stable `client_event_id` (uuid7) that will double as the sync idempotency key in 6.2B.

import { uuid7 } from "./ids";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { LocalProgressEvent, ProgressEventKind } from "./types";

function key(ev: LocalProgressEvent): string {
  return ev.client_event_id;
}

export class ProgressStore {
  constructor(
    private readonly store: KVStore,
    private readonly now: () => number = Date.now,
  ) {}

  async record(
    input: {
      student_ref: string;
      lesson_id: string;
      objective_code: string;
      kind: ProgressEventKind;
      item_ref?: string;
      selected_option?: number;
    },
    clientEventId: string = uuid7(this.now()),
  ): Promise<LocalProgressEvent> {
    const ev: LocalProgressEvent = {
      client_event_id: clientEventId,
      student_ref: input.student_ref,
      lesson_id: input.lesson_id,
      objective_code: input.objective_code,
      kind: input.kind,
      ...(input.item_ref !== undefined ? { item_ref: input.item_ref } : {}),
      ...(input.selected_option !== undefined ? { selected_option: input.selected_option } : {}),
      created_at: this.now(),
    };
    await this.store.put<LocalProgressEvent>(STORES.progress, key(ev), ev);
    return ev;
  }

  async all(): Promise<LocalProgressEvent[]> {
    return this.store.getAll<LocalProgressEvent>(STORES.progress);
  }

  async forStudent(studentRef: string): Promise<LocalProgressEvent[]> {
    return (await this.all()).filter((e) => e.student_ref === studentRef);
  }

  // A compact per-lesson summary for the offline UI (attempted item count, completion).
  async lessonSummary(
    studentRef: string,
    lessonId: string,
  ): Promise<{ attempted: number; completed: boolean; opened: boolean }> {
    const events = (await this.forStudent(studentRef)).filter((e) => e.lesson_id === lessonId);
    const attemptedRefs = new Set(
      events.filter((e) => e.kind === "item_attempted" && e.item_ref).map((e) => e.item_ref),
    );
    return {
      attempted: attemptedRefs.size,
      completed: events.some((e) => e.kind === "lesson_completed"),
      opened: events.some((e) => e.kind === "lesson_opened"),
    };
  }
}
