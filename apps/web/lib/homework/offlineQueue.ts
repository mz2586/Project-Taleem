// Offline homework: Send with no connection queues the answer for offline sync
// (OFFLINE_SYNC_SPEC.md `homework.submitted`; HOMEWORK_AND_MARKING_CONTRACT §2). Pure helpers
// between the homework view model and the durable sync queue; unit-tested without a browser.
//
// The life of an offline answer, as the child sees it on the item:
//   queued      "Saved on this phone — will send when online" (the queue copy is in IndexedDB, so it
//               survives a reload; the existing sync badge counts it as saved on this device)
//   held        the server refused the learner for permission (consent): kept, not retried in a loop
//   confirmed   the server applied it (or already had it): the server's own result is shown —
//               "Checked by Taleem", "Saved — compare", "Sent to your teacher" — and the draft is
//               wiped (only now, and only if the child has not changed it since)
//   conflict    the server refused this answer (marked and final, lesson no longer available, a newer
//               answer already saved, …): a gentle message, and the writing stays on the phone
//
// Nothing here claims "sent" before the server said so.

import type { MessageKey } from "../i18n/messages";
import type { HomeworkResultRecord } from "../offline/homeworkResults";
import { uuid7 } from "../offline/ids";
import { homeworkEntityKey } from "../offline/syncQueue";
import type { HomeworkPayload, QueuedDelta } from "../offline/types";
import type { SubmitTarget } from "./api";
import { draftKey } from "./drafts";
import type { LearnerSubmissionWire } from "./types";
import { flattenSubmitView } from "./wire";

export interface HomeworkRef {
  studentRef: string;
  target: SubmitTarget;
  itemRef: string;
}

function payloadTarget(target: SubmitTarget): Pick<HomeworkPayload, "source" | "assignment_id" | "objective_code"> {
  return target.source === "assignment"
    ? { source: "assignment", assignment_id: target.assignmentId }
    : { source: "self_paced", objective_code: target.objectiveCode };
}

/** The queue / result-ledger key of one homework item. */
export function homeworkKey(ref: HomeworkRef): string {
  return homeworkEntityKey({ student_ref: ref.studentRef, item_ref: ref.itemRef, ...payloadTarget(ref.target) });
}

/** The draft key the page uses for this item (an assignment id, else `self-paced:<objective>`). */
export function homeworkDraftKey(ref: HomeworkRef): string {
  const where = ref.target.source === "assignment" ? ref.target.assignmentId : `self-paced:${ref.target.objectiveCode}`;
  return draftKey(ref.studentRef, where, ref.itemRef);
}

/**
 * The delta payload for an answer sent offline. `serverAttempt` is the attempt the server last
 * showed for this item (0 when never sent), so the server can tell an older answer from a newer one.
 */
export function homeworkPayload(input: HomeworkRef & { text: string; serverAttempt: number; now: number }): HomeworkPayload {
  return {
    student_ref: input.studentRef,
    ...payloadTarget(input.target),
    item_ref: input.itemRef,
    text: input.text,
    submission_key: uuid7(input.now),
    attempt: Math.max(0, Math.floor(input.serverAttempt)) + 1,
    submitted_at: input.now,
  };
}

/** The draft key of a queued homework delta (for wiping it once the server confirmed it). */
export function draftKeyOfDelta(d: Pick<QueuedDelta, "payload">): string | null {
  const p = d.payload;
  const studentRef = typeof p["student_ref"] === "string" ? p["student_ref"] : null;
  const itemRef = typeof p["item_ref"] === "string" ? p["item_ref"] : null;
  if (!studentRef || !itemRef) return null;
  if (p["source"] === "assignment" && typeof p["assignment_id"] === "string") {
    return homeworkDraftKey({ studentRef, itemRef, target: { source: "assignment", assignmentId: p["assignment_id"] } });
  }
  if (p["source"] === "self_paced" && typeof p["objective_code"] === "string") {
    return homeworkDraftKey({ studentRef, itemRef, target: { source: "self_paced", objectiveCode: p["objective_code"] } });
  }
  return null;
}

/** Wipe the draft only when the server confirmed exactly the text the child still has there. */
export function shouldWipeDraft(draft: string | null, sentText: unknown): boolean {
  return draft !== null && typeof sentText === "string" && draft.trim() === sentText.trim();
}

export type HomeworkSyncView =
  | { kind: "queued"; held: boolean; clientEventId: string }
  | { kind: "confirmed"; clientEventId: string; submission: LearnerSubmissionWire | null; at: number }
  | { kind: "conflict"; clientEventId: string; reason: string };

function reasonFromError(lastError: string | undefined): string {
  const m = /^conflict: (.+)$/.exec(lastError ?? "");
  return m?.[1] ?? "CONFLICT";
}

/** How long a confirmed sync result is still worth saying on the item (the list shows it after). */
export const CONFIRMED_MESSAGE_MS = 24 * 60 * 60 * 1000;

/**
 * Where this item's offline answer stands. A live queue copy wins (a newer Send is, again, only
 * saved on this phone); a dead-lettered copy is a conflict with the server's reason; otherwise the
 * ledger says what the server answered (a confirmation only while recent). Null: nothing to say.
 */
export function homeworkSyncFor(
  entityKey: string,
  queue: readonly QueuedDelta[],
  results: readonly HomeworkResultRecord[],
  now: number = Date.now(),
): HomeworkSyncView | null {
  const q = queue.find((d) => d.type === "homework.submitted" && d.entityKey === entityKey);
  const r = results.find((x) => x.entityKey === entityKey);
  if (q && q.syncState !== "dead") return { kind: "queued", held: q.syncState === "held", clientEventId: q.clientEventId };
  if (q) {
    const reason = r && r.clientEventId === q.clientEventId && r.reason ? r.reason : reasonFromError(q.lastError);
    return { kind: "conflict", clientEventId: q.clientEventId, reason };
  }
  if (!r) return null;
  if (r.status === "conflict") return { kind: "conflict", clientEventId: r.clientEventId, reason: r.reason ?? "CONFLICT" };
  if (now - r.at > CONFIRMED_MESSAGE_MS) return null;
  return { kind: "confirmed", clientEventId: r.clientEventId, submission: flattenSubmitView(r.result), at: r.at };
}

/** A gentle, specific message for a sync conflict. The writing is always still on the phone. */
export function conflictKey(reason: string, involvesTeacher: boolean): MessageKey {
  switch (reason) {
    case "SUBMISSION_MARKED":
      return involvesTeacher ? "student.homework.result.final" : "student.homework.result.finalChecked";
    case "SHARING_REQUIRED":
      return "student.homework.result.sharingOff";
    case "SUBMISSION_SUPERSEDED":
      return "student.homework.sync.superseded";
    case "LESSON_ASSIGNED":
      return "student.homework.sync.assigned";
    case "NOT_AVAILABLE":
      return "student.homework.sync.gone";
    case "INVALID":
      return "student.homework.result.invalid";
    default:
      return "student.homework.sync.tryAgain";
  }
}
