// Session reconciliation + automatic resume after reconnect (Phase 6.2B).
//
// After an offline session, some answered items may have progress recorded locally but no queued
// sync delta (e.g. the enqueue was interrupted by a crash between the progress write and the queue
// write). Reconciliation replays the local record of truth (progress events for a session's
// checkpoint) into the durable queue, idempotently — each attempt keeps a STABLE evidence_id so a
// re-queued attempt the server already saw is a DUPLICATE, never a double-count. Then it drains.

import type { CheckpointStore } from "./checkpoint";
import { uuid7 } from "./ids";
import type { ProgressStore } from "./progress";
import type { SyncQueue } from "./syncQueue";
import type { DrainSummary, LocalProgressEvent } from "./types";

// A stable, deterministic evidence_id for a progress attempt event, so re-queuing is idempotent.
function evidenceIdFor(ev: LocalProgressEvent): string {
  // Reuse the event's own stable client_event_id (a uuid7) as the evidence id — deterministic and
  // unique per attempt, so the server dedupes a re-queued attempt on its evidence_id.
  return ev.client_event_id;
}

export interface ReconcileDeps {
  progress: ProgressStore;
  checkpoints: CheckpointStore;
  queue: SyncQueue;
  drain: () => Promise<DrainSummary>;
}

// Ensure every locally-recorded offline attempt for a learner is represented in the sync queue,
// then drain. Returns the drain summary + how many attempts were (re)enqueued.
export async function reconcileAndResume(
  studentRef: string,
  deps: ReconcileDeps,
): Promise<{ enqueued: number; drain: DrainSummary }> {
  const events = await deps.progress.forStudent(studentRef);
  const attempts = events.filter((e) => e.kind === "item_attempted" && e.selected_option !== undefined);

  const queued = new Set((await deps.queue.all()).map((q) => String(q.payload["evidence_id"])));

  let enqueued = 0;
  for (const ev of attempts) {
    const evidenceId = evidenceIdFor(ev);
    if (queued.has(evidenceId)) continue; // already queued or in-flight — idempotent skip
    await deps.queue.enqueueAttempt({
      student_ref: ev.student_ref,
      objective_code: ev.objective_code,
      item_ref: ev.item_ref ?? "",
      option: ev.selected_option ?? 0,
      evidence_id: evidenceId,
      session_id: ev.lesson_id, // the offline session's lesson is its correlation key
      context: "practice",
    });
    enqueued++;
  }

  const drain = await deps.drain();
  return { enqueued, drain };
}

// A convenience: mint a fresh evidence id (for callers enqueueing a brand-new attempt directly).
export function newEvidenceId(nowMs: number = Date.now()): string {
  return uuid7(nowMs);
}
