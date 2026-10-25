// Learner homework view model (contract §2 and §6, the AI-led path). Pure and unit-tested; the page
// only renders it.
//
// - §6: homework is first the learner's own lesson practice (`source: "self_paced"`: no teacher, no
//   due date). A teacher's assignment (`source: "assignment"`) is the optional extra, and only those
//   items use teacher wording. The two are shown as separate groups.
// - §6: an auto-marked item comes back `marked` with `reviewed_by: "auto"` and reads "Checked by
//   Taleem". A self-check item is never called marked: it is "saved", and only after it was sent may
//   the child compare it with the author's sample answer or guidance.
//
// - Each item shows its state by symbol + words (never colour alone): not started, sent, sent back
//   with the teacher's note, or marked (met / not yet) with feedback.
// - Send is enabled only for a non-empty answer within `max_chars`, while not already sending, while
//   online, and while the item is still open (a marked answer is final — the server answers 409).
// - Offline, Send QUEUES the answer for offline sync when the page provides a queue (the outcome
//   says "Saved on this phone — will send when online"); without one the text is only kept. A network
//   failure during the send is treated the same way. "Sent" / "Checked" is claimed only on a server
//   answer: an online 2xx, or a sync result (lib/homework/offlineQueue.ts).

import type { LocalizedText } from "../i18n/content";
import type { MessageKey } from "../i18n/messages";
import { ApiError } from "../student/types";
import type { DraftStore } from "./drafts";
import { conflictKey, type HomeworkSyncView } from "./offlineQueue";
import type {
  HomeworkAssignmentWire,
  HomeworkItemWire,
  HomeworkMarking,
  HomeworkSource,
  LearnerHomeworkWire,
  LearnerSubmissionWire,
  MarkOutcome,
  SubmissionState,
  SubmitBody,
} from "./types";
import { compareText, itemMarking, itemSource, itemState, localized, type CompareText } from "./wire";

/** Who marked a `marked` item: Taleem's exact-answer rule, or a person (a class teacher). */
export type ReviewedBy = "auto" | "teacher";

export interface HomeworkItemView {
  assignmentId: string;
  itemRef: string;
  prompt: LocalizedText | null;
  hints: string[];
  maxChars: number;
  state: SubmissionState;
  /** What was last sent (shown read-only once marked; the starting text while it is still open). */
  sentText: string | null;
  feedback: string | null;
  outcome: MarkOutcome | null;
  /** §6: the learner's own lesson practice, or a teacher's assignment. */
  source: HomeworkSource;
  /** §6: null when the server did not say (never assumed to be "auto"). */
  marking: HomeworkMarking | null;
  /** Set only on a `marked` item. */
  reviewedBy: ReviewedBy | null;
  /** §6: self-check comparison text; shown only once the answer was sent (see `compareView`). */
  compare: CompareText | null;
  /** §6: the server allows another try after an auto-marked `not_yet` (never after `met`). */
  canRetry: boolean;
  /** The server's attempt count for this item (0 / absent = never submitted); offline sync sends it + 1. */
  attempt?: number;
}

export interface HomeworkAssignmentView {
  assignmentId: string;
  objectiveCode: string;
  title: LocalizedText | null;
  className: string | null;
  /** Assignments only; self-paced practice has no due date. */
  dueAt: number | null;
  source: HomeworkSource;
  items: HomeworkItemView[];
}

/** The contract's caps (200 short, 2000 otherwise); a missing or nonsensical value reads as short. */
function maxCharsOf(value: unknown): number {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : 200;
}

/** `marked` by Taleem's rule (`reviewed_by: "auto"`, or an auto item with no reviewer named) or a person. */
function reviewedByOf(
  state: SubmissionState,
  reviewedBy: string | null | undefined,
  marking: HomeworkMarking | null,
): ReviewedBy | null {
  if (state !== "marked") return null;
  if (reviewedBy === "auto") return "auto";
  if (typeof reviewedBy === "string" && reviewedBy.trim() !== "") return "teacher";
  return marking === "auto" ? "auto" : "teacher";
}

function outcomeOf(value: unknown): MarkOutcome | null {
  return value === "met" || value === "not_yet" ? value : null;
}

/** Only an explicit `can_retry: true` opens a marked item again, and never a `met` (that stays final). */
function canRetryOf(raw: unknown, state: SubmissionState, outcome: MarkOutcome | null): boolean {
  return raw === true && !(state === "marked" && outcome === "met");
}

function itemView(
  a: HomeworkAssignmentWire,
  item: HomeworkItemWire,
  preference: readonly string[],
): HomeworkItemView {
  const s = item.submission ?? null;
  const state = itemState(item);
  const marking = itemMarking(item);
  const outcome = outcomeOf(s?.outcome);
  return {
    assignmentId: a.assignment_id,
    itemRef: item.item_ref,
    prompt: localized(item.prompt, preference),
    hints: (item.hints ?? []).filter((h) => typeof h === "string" && h.trim() !== ""),
    maxChars: maxCharsOf(item.max_chars),
    state,
    sentText: s?.text ?? null,
    feedback: s?.feedback?.trim() ? s.feedback : null,
    outcome,
    source: itemSource(item, a),
    marking,
    reviewedBy: reviewedByOf(state, s?.reviewed_by, marking),
    compare: compareText(s?.compare ?? item.compare, preference),
    canRetry: canRetryOf(s?.can_retry ?? item.can_retry, state, outcome),
    attempt: attemptOf(s?.attempt, s ? 1 : 0),
  };
}

function attemptOf(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : fallback;
}

/** One wire entry → one view per source present (an entry's items may in principle be mixed). */
function assignmentViews(
  a: HomeworkAssignmentWire,
  preference: readonly string[],
  titlePreference: readonly string[],
): HomeworkAssignmentView[] {
  const items = (a.items ?? []).map((item) => itemView(a, item, preference));
  const base = {
    assignmentId: a.assignment_id,
    objectiveCode: a.objective_code,
    title: localized(a.lesson_title, titlePreference),
    className: a.class_name?.trim() || null,
  };
  const dueAt = typeof a.due_at === "number" && a.due_at > 0 ? a.due_at : null;
  return (["assignment", "self_paced"] as const).map((source) => ({
    ...base,
    // A due date belongs to a teacher's assignment only (§6).
    dueAt: source === "assignment" ? dueAt : null,
    source,
    items: items.filter((i) => i.source === source),
  }));
}

/**
 * Entries with at least one written item: assignments soonest due first, then self-paced practice in
 * the server's order. `preference` picks the lesson text (prompts keep their authored language);
 * `titlePreference` may put the interface language first.
 */
export function homeworkView(
  wire: LearnerHomeworkWire,
  preference: readonly string[],
  titlePreference: readonly string[] = preference,
): HomeworkAssignmentView[] {
  return (wire.assignments ?? [])
    .flatMap((a) => assignmentViews(a, preference, titlePreference))
    .filter((a) => a.items.length > 0)
    .sort((x, y) => {
      if (x.dueAt === null || y.dueAt === null) return (x.dueAt === null ? 1 : 0) - (y.dueAt === null ? 1 : 0);
      return x.dueAt - y.dueAt || x.assignmentId.localeCompare(y.assignmentId);
    });
}

export interface HomeworkGroupView {
  source: HomeworkSource;
  headingKey: MessageKey;
  introKey: MessageKey;
  entries: HomeworkAssignmentView[];
}

/**
 * §6: "From your lessons" (self-paced) first — it is the primary path — then "From your class"
 * (assignments). A group with nothing in it is left out.
 */
export function homeworkGroups(entries: readonly HomeworkAssignmentView[]): HomeworkGroupView[] {
  const groups: HomeworkGroupView[] = [
    {
      source: "self_paced",
      headingKey: "student.homework.groups.lessons",
      introKey: "student.homework.groups.lessonsIntro",
      entries: entries.filter((e) => e.source === "self_paced"),
    },
    {
      source: "assignment",
      headingKey: "student.homework.groups.classes",
      introKey: "student.homework.groups.classesIntro",
      entries: entries.filter((e) => e.source === "assignment"),
    },
  ];
  return groups.filter((g) => g.entries.length > 0);
}

/** Replace one item (by entry, source and ref) in the list after a send. */
export function replaceItem(list: readonly HomeworkAssignmentView[], next: HomeworkItemView): HomeworkAssignmentView[] {
  return list.map((a) =>
    a.assignmentId !== next.assignmentId || a.source !== next.source
      ? a
      : { ...a, items: a.items.map((i) => (i.itemRef === next.itemRef ? next : i)) },
  );
}

// ---- state badge ------------------------------------------------------------------------------------

export interface StateBadgeView {
  state: SubmissionState;
  /** Decorative; always shown beside the words. */
  symbol: string;
  labelKey: MessageKey;
  /** The marker's words, when there are any to show. */
  note: string | null;
  /** The heading over `note`: Taleem's check, or a teacher. */
  noteKey: MessageKey;
}

type BadgeInput = Pick<HomeworkItemView, "state" | "feedback" | "outcome"> &
  Partial<Pick<HomeworkItemView, "source" | "reviewedBy">>;

export function stateBadge(item: BadgeInput): StateBadgeView {
  const teacherNote: MessageKey = "student.homework.teacherNote";
  switch (item.state) {
    case "submitted":
      // Self-paced: nobody is waiting to read it, so it is "saved", never "sent to your teacher".
      return item.source === "self_paced"
        ? { state: item.state, symbol: "◐", labelKey: "student.homework.state.saved", note: null, noteKey: teacherNote }
        : { state: item.state, symbol: "◐", labelKey: "student.homework.state.sent", note: null, noteKey: teacherNote };
    case "returned":
      return { state: item.state, symbol: "↩", labelKey: "student.homework.state.returned", note: item.feedback, noteKey: teacherNote };
    case "marked": {
      const met = item.outcome === "met";
      if (item.reviewedBy === "auto") {
        return {
          state: item.state,
          symbol: met ? "✓" : "◑",
          labelKey: met ? "student.homework.state.checkedMet" : "student.homework.state.checkedNotYet",
          note: item.feedback,
          noteKey: "student.homework.taleemNote",
        };
      }
      return met
        ? { state: item.state, symbol: "●", labelKey: "student.homework.state.markedMet", note: item.feedback, noteKey: teacherNote }
        : { state: item.state, symbol: "◑", labelKey: "student.homework.state.markedNotYet", note: item.feedback, noteKey: teacherNote };
    }
    default:
      return { state: "not_started", symbol: "○", labelKey: "student.homework.state.notStarted", note: null, noteKey: teacherNote };
  }
}

/** Teacher wording is used only for a teacher's assignment, or where a teacher actually marked it. */
export function involvesTeacher(item: Partial<Pick<HomeworkItemView, "source" | "reviewedBy">>): boolean {
  if (item.reviewedBy === "auto") return false;
  if (item.reviewedBy === "teacher") return true;
  return item.source !== "self_paced";
}

/** §6: the comparison block — only for a self-check answer that has been sent, and only if authored. */
export function compareView(item: Pick<HomeworkItemView, "state" | "marking" | "compare">): CompareText | null {
  if (item.marking !== "self_check") return null;
  if (item.state !== "submitted" && item.state !== "returned") return null;
  return item.compare;
}

export interface ItemCopy {
  send: MessageKey;
  sendAgain: MessageKey;
  resendNote: MessageKey;
  final: MessageKey;
}

/** §6: the button and note wording for one item, by where it came from and how it is marked. */
export function itemCopy(item: Partial<Pick<HomeworkItemView, "source" | "marking" | "reviewedBy">>): ItemCopy {
  if (item.source === "self_paced") {
    const auto = item.marking === "auto";
    return {
      send: auto ? "student.homework.checkAnswer" : "student.homework.saveAnswer",
      sendAgain: auto ? "student.homework.checkAgain" : "student.homework.saveAgain",
      resendNote: "student.homework.resendNoteSelf",
      final: involvesTeacher(item) ? "student.homework.reason.final" : "student.homework.reason.finalChecked",
    };
  }
  return {
    send: "student.homework.send",
    sendAgain: "student.homework.sendAgain",
    resendNote: "student.homework.resendNote",
    final: involvesTeacher(item) ? "student.homework.reason.final" : "student.homework.reason.finalChecked",
  };
}

/**
 * A child may (re)send while not started, sent or returned. Marked is final — unless the server says
 * `can_retry` (§6: after Taleem's check said "not yet").
 */
export function isOpen(state: SubmissionState, canRetry = false): boolean {
  return state !== "marked" || canRetry;
}

// ---- the answer box -------------------------------------------------------------------------------

/** Characters as the server counts them: code points of the trimmed text. */
export function charCount(text: string): number {
  return Array.from(text.trim()).length;
}

export interface SubmitGate {
  canSend: boolean;
  count: number;
  over: boolean;
  /** Why Send is disabled, shown beside it (null while it is enabled or a send is in flight). */
  reason: MessageKey | null;
  /** A note beside an enabled Send (offline with a queue: "it will be saved on this phone"). */
  note?: MessageKey;
}

export function submitGate(input: {
  text: string;
  maxChars: number;
  state: SubmissionState;
  sending: boolean;
  online: boolean;
  canRetry?: boolean;
  /** The "final" reason to show (teacher-marked vs checked by Taleem); defaults to the teacher's. */
  finalReason?: MessageKey;
  /** Offline Send can queue the answer for offline sync (the page wired a queue). */
  canQueue?: boolean;
}): SubmitGate {
  const count = charCount(input.text);
  const over = count > input.maxChars;
  const reachable = input.online || input.canQueue === true;
  let reason: MessageKey | null = null;
  if (!isOpen(input.state, input.canRetry)) reason = input.finalReason ?? "student.homework.reason.final";
  else if (input.sending) reason = null;
  else if (!reachable) reason = "student.homework.reason.offline";
  else if (count === 0) reason = "student.homework.reason.empty";
  else if (over) reason = "student.homework.reason.tooLong";
  const canSend = isOpen(input.state, input.canRetry) && !input.sending && reachable && count > 0 && !over;
  const gate: SubmitGate = { canSend, count, over, reason };
  if (canSend && !input.online) gate.note = "student.homework.reason.offlineQueue";
  return gate;
}

/** The request body, or null when the text cannot be sent. */
export function submitBody(text: string, maxChars: number): SubmitBody | null {
  const trimmed = text.trim();
  const count = Array.from(trimmed).length;
  if (count === 0 || count > maxChars) return null;
  return { text: trimmed };
}

// ---- sending -----------------------------------------------------------------------------------------

export type SendOutcome =
  | { kind: "sent"; submission: LearnerSubmissionWire | null; text: string }
  /** Not sent: no connection. The text is (or could not be) kept on the phone. */
  | { kind: "offline"; kept: boolean }
  /** No connection: the answer is queued on this phone and will be sent by offline sync. */
  | { kind: "queued"; text: string }
  | { kind: "invalid" }
  | { kind: "final" }
  | { kind: "not-found" }
  | { kind: "consent" }
  /** The guardian stopped sharing progress with teachers: the work stays on this phone. */
  | { kind: "sharing"; kept: boolean }
  | { kind: "signed-out" }
  | { kind: "error" };

export async function sendHomework(input: {
  online: boolean;
  text: string;
  maxChars: number;
  state: SubmissionState;
  canRetry?: boolean;
  draftKey: string;
  drafts: DraftStore;
  send: (body: SubmitBody) => Promise<LearnerSubmissionWire | undefined>;
  /** Queue the answer for offline sync (no connection). Absent: offline only keeps the text. */
  queue?: (body: SubmitBody) => Promise<void>;
}): Promise<SendOutcome> {
  if (!isOpen(input.state, input.canRetry)) return { kind: "final" };
  // Keep the writing first, whatever happens next. The draft stays until the server confirms it.
  const kept = input.drafts.write(input.draftKey, input.text);
  const body = submitBody(input.text, input.maxChars);
  const enqueue = async (): Promise<SendOutcome> => {
    if (!input.queue || !body) return { kind: "offline", kept };
    try {
      await input.queue(body);
      return { kind: "queued", text: body.text };
    } catch {
      return { kind: "offline", kept }; // the phone could not queue it: say only what is true
    }
  };
  if (!input.online) return body || !input.queue ? enqueue() : { kind: "invalid" };
  if (!body) return { kind: "invalid" };
  try {
    const submission = await input.send(body);
    input.drafts.clear(input.draftKey);
    return { kind: "sent", submission: submission && typeof submission === "object" ? submission : null, text: body.text };
  } catch (error) {
    if (!(error instanceof ApiError)) return { kind: "error" };
    if (error.status === 0) return enqueue(); // the connection dropped: queue it like offline
    if (error.status === 401) return { kind: "signed-out" };
    if (error.status === 403 && error.problem.code === "SHARING_REQUIRED") return { kind: "sharing", kept };
    if (error.status === 403) return { kind: "consent" };
    if (error.status === 404) return { kind: "not-found" };
    if (error.status === 409) return { kind: "final" };
    if (error.status === 422) return { kind: "invalid" };
    return { kind: "error" };
  }
}

/**
 * The message for a send outcome (shown in the item's status line). `after` is the item as it now
 * stands (for a success: `afterSent`; otherwise the item itself) — it decides the §6 wording.
 */
export function sendOutcomeKey(outcome: SendOutcome, after?: HomeworkItemView): MessageKey {
  switch (outcome.kind) {
    case "sent":
      if (after?.state === "marked" && after.reviewedBy === "auto") return "student.homework.result.checked";
      if (after?.state === "marked") return "student.homework.result.marked";
      if (after?.source === "self_paced") {
        return compareView(after) ? "student.homework.result.savedCompare" : "student.homework.result.saved";
      }
      return "student.homework.result.sent";
    case "offline":
      return outcome.kept ? "student.homework.result.offlineKept" : "student.homework.result.offlineNotKept";
    case "queued":
      return "student.homework.result.queued";
    case "invalid":
      return "student.homework.result.invalid";
    case "final":
      return after && !involvesTeacher(after) ? "student.homework.result.finalChecked" : "student.homework.result.final";
    case "not-found":
      return "student.homework.result.notFound";
    case "consent":
      return "auth.errors.consentNeeded";
    case "sharing":
      return "student.homework.result.sharingOff";
    case "signed-out":
      return "common.signedOut";
    default:
      return "student.homework.result.error";
  }
}

/**
 * The item after a successful send, as the server answered it: "submitted" (saved / sent), or — for
 * an auto-marked item (§6) — "marked" with its outcome, Taleem's feedback and `reviewed_by: "auto"`.
 * A self-check answer picks up its comparison text here. Only a server answer can say "marked".
 */
export function afterSent(
  item: HomeworkItemView,
  outcome: Extract<SendOutcome, { kind: "sent" }>,
  preference: readonly string[] = ["ur", "en"],
): HomeworkItemView {
  const s = outcome.submission;
  const raw = s?.state;
  const state: SubmissionState = raw === "submitted" || raw === "returned" || raw === "marked" ? raw : "submitted";
  const result = state === "marked" ? outcomeOf(s?.outcome) : null;
  // "marked" without a real outcome is not a mark we can show honestly.
  const finalState: SubmissionState = state === "marked" && result === null ? "submitted" : state;
  const marking = (s?.marking === "auto" || s?.marking === "self_check" || s?.marking === "teacher" ? s.marking : null) ?? item.marking;
  const feedback = s?.feedback?.trim() ? s.feedback : null;
  return {
    ...item,
    state: finalState,
    sentText: s?.text ?? outcome.text,
    feedback: finalState === "submitted" ? null : (feedback ?? (finalState === "returned" ? item.feedback : null)),
    outcome: finalState === "marked" ? result : null,
    marking,
    reviewedBy: reviewedByOf(finalState, s?.reviewed_by, marking),
    compare: compareText(s?.compare, preference) ?? item.compare,
    canRetry: canRetryOf(s?.can_retry, finalState, finalState === "marked" ? result : null),
    attempt: attemptOf(s?.attempt, (item.attempt ?? 0) + 1),
  };
}

/**
 * The status line for an answer that went through offline sync (null: nothing to say). A queued
 * answer is only "saved on this phone"; a confirmed one shows the server's own result; a conflict
 * a gentle reason (the writing is still on the phone).
 */
export function syncMessageKey(sync: HomeworkSyncView | null, item: HomeworkItemView): MessageKey | null {
  if (!sync) return null;
  switch (sync.kind) {
    case "queued":
      return sync.held ? "student.homework.sync.held" : "student.homework.result.queued";
    case "confirmed": {
      const sent = { kind: "sent" as const, submission: sync.submission, text: item.sentText ?? "" };
      return sendOutcomeKey(sent, afterSent(item, sent));
    }
    case "conflict":
      return conflictKey(sync.reason, involvesTeacher(item));
  }
}

/** The Send label: a first try (or a fresh try after "not yet") reads as the first action. */
export function sendLabelKey(item: Pick<HomeworkItemView, "state" | "canRetry">, copy: ItemCopy): MessageKey {
  return item.state === "not_started" || (item.state === "marked" && item.canRetry) ? copy.send : copy.sendAgain;
}

/** The text the box starts with: a kept draft, else what was last sent (so a resend edits it). */
export function initialText(item: HomeworkItemView, draft: string | null): string {
  if (!isOpen(item.state, item.canRetry)) return "";
  if (draft !== null && draft !== "") return draft;
  return item.sentText ?? "";
}
