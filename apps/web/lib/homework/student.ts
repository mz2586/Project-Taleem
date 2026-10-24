// Learner homework view model (contract §2). Pure and unit-tested; the page only renders it.
//
// - Each item shows its state by symbol + words (never colour alone): not started, sent, sent back
//   with the teacher's note, or marked (met / not yet) with feedback.
// - Send is enabled only for a non-empty answer within `max_chars`, while not already sending, while
//   online, and while the item is still open (a marked answer is final — the server answers 409).
// - Offline, the text is kept on the phone and NOTHING is sent; the outcome says so. A network
//   failure during the send is treated the same way. Success is claimed only on a server 2xx.

import type { LocalizedText } from "../i18n/content";
import type { MessageKey } from "../i18n/messages";
import { ApiError } from "../student/types";
import type { DraftStore } from "./drafts";
import type {
  HomeworkAssignmentWire,
  LearnerHomeworkWire,
  LearnerSubmissionWire,
  MarkOutcome,
  SubmissionState,
  SubmitBody,
} from "./types";
import { itemState, localized } from "./wire";

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
}

export interface HomeworkAssignmentView {
  assignmentId: string;
  objectiveCode: string;
  title: LocalizedText | null;
  className: string | null;
  dueAt: number;
  items: HomeworkItemView[];
}

/** The contract's caps (200 short, 2000 otherwise); a missing or nonsensical value reads as short. */
function maxCharsOf(value: unknown): number {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : 200;
}

function assignmentView(
  a: HomeworkAssignmentWire,
  preference: readonly string[],
  titlePreference: readonly string[],
): HomeworkAssignmentView {
  return {
    assignmentId: a.assignment_id,
    objectiveCode: a.objective_code,
    title: localized(a.lesson_title, titlePreference),
    className: a.class_name?.trim() || null,
    dueAt: a.due_at,
    items: (a.items ?? []).map((item) => {
      const s = item.submission ?? null;
      const feedback = s?.feedback?.trim() ? s.feedback : null;
      return {
        assignmentId: a.assignment_id,
        itemRef: item.item_ref,
        prompt: localized(item.prompt, preference),
        hints: (item.hints ?? []).filter((h) => typeof h === "string" && h.trim() !== ""),
        maxChars: maxCharsOf(item.max_chars),
        state: itemState(item),
        sentText: s?.text ?? null,
        feedback,
        outcome: s?.outcome === "met" || s?.outcome === "not_yet" ? s.outcome : null,
      };
    }),
  };
}

/**
 * Assignments with at least one written item, soonest due first. `preference` picks the lesson text
 * (prompts keep their authored language); `titlePreference` may put the interface language first.
 */
export function homeworkView(
  wire: LearnerHomeworkWire,
  preference: readonly string[],
  titlePreference: readonly string[] = preference,
): HomeworkAssignmentView[] {
  return (wire.assignments ?? [])
    .map((a) => assignmentView(a, preference, titlePreference))
    .filter((a) => a.items.length > 0)
    .sort((x, y) => x.dueAt - y.dueAt || x.assignmentId.localeCompare(y.assignmentId));
}

// ---- state badge ------------------------------------------------------------------------------------

export interface StateBadgeView {
  state: SubmissionState;
  /** Decorative; always shown beside the words. */
  symbol: string;
  labelKey: MessageKey;
  /** The teacher's words, when there are any to show. */
  note: string | null;
}

export function stateBadge(item: Pick<HomeworkItemView, "state" | "feedback" | "outcome">): StateBadgeView {
  switch (item.state) {
    case "submitted":
      return { state: item.state, symbol: "◐", labelKey: "student.homework.state.sent", note: null };
    case "returned":
      return { state: item.state, symbol: "↩", labelKey: "student.homework.state.returned", note: item.feedback };
    case "marked":
      return item.outcome === "met"
        ? { state: item.state, symbol: "●", labelKey: "student.homework.state.markedMet", note: item.feedback }
        : { state: item.state, symbol: "◑", labelKey: "student.homework.state.markedNotYet", note: item.feedback };
    default:
      return { state: "not_started", symbol: "○", labelKey: "student.homework.state.notStarted", note: null };
  }
}

/** A child may (re)send while not started, sent or returned. Marked is final. */
export function isOpen(state: SubmissionState): boolean {
  return state !== "marked";
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
}

export function submitGate(input: {
  text: string;
  maxChars: number;
  state: SubmissionState;
  sending: boolean;
  online: boolean;
}): SubmitGate {
  const count = charCount(input.text);
  const over = count > input.maxChars;
  let reason: MessageKey | null = null;
  if (!isOpen(input.state)) reason = "student.homework.reason.final";
  else if (input.sending) reason = null;
  else if (!input.online) reason = "student.homework.reason.offline";
  else if (count === 0) reason = "student.homework.reason.empty";
  else if (over) reason = "student.homework.reason.tooLong";
  const canSend = isOpen(input.state) && !input.sending && input.online && count > 0 && !over;
  return { canSend, count, over, reason };
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
  draftKey: string;
  drafts: DraftStore;
  send: (body: SubmitBody) => Promise<LearnerSubmissionWire | undefined>;
}): Promise<SendOutcome> {
  if (!isOpen(input.state)) return { kind: "final" };
  // Keep the writing first, whatever happens next.
  const kept = input.drafts.write(input.draftKey, input.text);
  if (!input.online) return { kind: "offline", kept };
  const body = submitBody(input.text, input.maxChars);
  if (!body) return { kind: "invalid" };
  try {
    const submission = await input.send(body);
    input.drafts.clear(input.draftKey);
    return { kind: "sent", submission: submission && typeof submission === "object" ? submission : null, text: body.text };
  } catch (error) {
    if (!(error instanceof ApiError)) return { kind: "error" };
    if (error.status === 0) return { kind: "offline", kept };
    if (error.status === 401) return { kind: "signed-out" };
    if (error.status === 403 && error.problem.code === "SHARING_REQUIRED") return { kind: "sharing", kept };
    if (error.status === 403) return { kind: "consent" };
    if (error.status === 404) return { kind: "not-found" };
    if (error.status === 409) return { kind: "final" };
    if (error.status === 422) return { kind: "invalid" };
    return { kind: "error" };
  }
}

/** The message for a send outcome (shown in the item's status line). */
export function sendOutcomeKey(outcome: SendOutcome): MessageKey {
  switch (outcome.kind) {
    case "sent":
      return "student.homework.result.sent";
    case "offline":
      return outcome.kept ? "student.homework.result.offlineKept" : "student.homework.result.offlineNotKept";
    case "invalid":
      return "student.homework.result.invalid";
    case "final":
      return "student.homework.result.final";
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

/** The item after a successful send: "sent", with the text the server accepted. */
export function afterSent(item: HomeworkItemView, outcome: Extract<SendOutcome, { kind: "sent" }>): HomeworkItemView {
  const s = outcome.submission;
  const state = s?.state && s.state !== "not_started" ? s.state : "submitted";
  return { ...item, state, sentText: s?.text ?? outcome.text, feedback: state === "submitted" ? null : item.feedback, outcome: null };
}

/** The text the box starts with: a kept draft, else what was last sent (so a resend edits it). */
export function initialText(item: HomeworkItemView, draft: string | null): string {
  if (!isOpen(item.state)) return "";
  if (draft !== null && draft !== "") return draft;
  return item.sentText ?? "";
}
