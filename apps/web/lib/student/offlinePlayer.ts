// The offline lesson player — plays an INSTALLED package with no network. Pure reducer + a small
// persistence runner; both tested (the runner against fake-indexeddb).
//
// What the package format provides, and what that forces (lib/offline/types.ts OfflineContent):
// - title, explanation (locale maps), worked_example_steps, practice_items and assessment_formative
//   (prompt locale map, options, authored hints). NO answer key: `correct_option` never reaches the
//   device (6.2A). So the offline player never says right or wrong. An answer is SAVED ON THIS PHONE
//   and graded by the server when it syncs ("your teacher checks it when you are online"); the sync
//   badge then moves it from saved-on-phone to saved-by-Taleem.
// - Because the child cannot learn the outcome, there is no retry loop: one answer per item, then
//   the next item. Authored hints are revealed one rung at a time and reported as `hints_used`.
// - Summative items are not in the package (mentor-mediated); homework items are not played here.
//
// The presenting/asking/hint mechanics reuse lib/student/lessonPlayer.ts unchanged: the package is
// adapted to a TeachView and the same reducer handles steps, readiness, hints and moving to the next
// item. Only "saved" (instead of a graded answer) and "done" are offline-specific.
//
// Durability: every answer is (1) a local progress event, (2) a queued `attempt.submitted` delta
// whose `evidence_id` is that event's id — the shape /v1/sync/batch grades, and the same id
// `reconcileAndResume` uses, so a re-queue is a server DUPLICATE, never a double count — and (3) a
// checkpoint advance, so a reload resumes at the next item.

import { pickLocalized } from "../i18n/content";
import type { CheckpointStore } from "../offline/checkpoint";
import type { ProgressStore } from "../offline/progress";
import type { SyncQueue } from "../offline/syncQueue";
import type { OfflineContent, OfflineItem, SessionCheckpoint } from "../offline/types";
import { INSTRUCTION_LOCALE_PREFERENCE } from "./journey";
import {
  currentItem,
  initialPlayerState,
  playerReducer,
  presentationSteps,
  type PlayerAction,
  type PlayerState,
} from "./lessonPlayer";
import type { ItemView, TeachView } from "./types";

// ---- adapting a package to the lesson player -------------------------------------------------------

/** The items played offline, in order: practice, then the formative check. */
export function playableItems(content: OfflineContent): OfflineItem[] {
  return [...(content.practice_items ?? []), ...(content.assessment_formative ?? [])];
}

/** The package as the lesson player's TeachView: title, explanation, then each worked step. */
export function toTeachView(content: OfflineContent): TeachView {
  const title = pickLocalized(content.title, INSTRUCTION_LOCALE_PREFERENCE);
  const explanation = pickLocalized(content.explanation, INSTRUCTION_LOCALE_PREFERENCE);
  const present = [title?.text, explanation?.text, ...(content.worked_example_steps ?? [])]
    .filter((t): t is string => typeof t === "string" && t.trim() !== "")
    .map((text) => ({ kind: "present", text }));
  const items: ItemView[] = playableItems(content).map((i) => ({
    item_ref: i.item_ref,
    prompt: i.prompt,
    options: i.options,
    hint_count: i.hints.length,
  }));
  return { utterances: present, items };
}

/** The lesson's content language (from its title, else its first item). */
export function contentLocale(content: OfflineContent): string | null {
  return (
    pickLocalized(content.title, INSTRUCTION_LOCALE_PREFERENCE)?.locale ??
    (playableItems(content)[0] ? pickLocalized(playableItems(content)[0]!.prompt, INSTRUCTION_LOCALE_PREFERENCE)?.locale : null) ??
    null
  );
}

// ---- the offline reducer -----------------------------------------------------------------------------

export interface OfflinePlayerState {
  player: PlayerState;
  content: OfflineContent | null;
  /** Answers saved on this phone in this run (for the end screen). */
  savedCount: number;
  /** The item just saved, for the "saved" notice; cleared on the next action. */
  justSaved: boolean;
  done: boolean;
}

export type OfflineAction =
  | { type: "load"; content: OfflineContent; resumeAt?: number }
  | Extract<PlayerAction, { type: "nextStep" | "previousStep" | "ready" }>
  | { type: "hint" }
  | { type: "saved" };

export const initialOfflineState: OfflinePlayerState = {
  player: initialPlayerState,
  content: null,
  savedCount: 0,
  justSaved: false,
  done: false,
};

export function offlineItem(state: OfflinePlayerState): OfflineItem | undefined {
  return state.content ? playableItems(state.content)[state.player.itemIndex] : undefined;
}

/** Whether another authored hint exists for the current item. */
export function canShowHint(state: OfflinePlayerState): boolean {
  const item = offlineItem(state);
  return !!item && state.player.phase === "asking" && state.player.hints.length < item.hints.length;
}

export function offlineReducer(state: OfflinePlayerState, action: OfflineAction): OfflinePlayerState {
  switch (action.type) {
    case "load": {
      const teach = toTeachView(action.content);
      let player = playerReducer(initialPlayerState, { type: "taught", objective: action.content.objective_code, teach });
      const resumeAt = action.resumeAt ?? 0;
      const total = teach.items.length;
      if (resumeAt > 0) {
        // Resume skips the presentation the child already read and lands on the next item.
        if (resumeAt >= total) return { ...initialOfflineState, player, content: action.content, done: true };
        player = { ...player, phase: "asking", itemIndex: resumeAt };
      }
      return { ...initialOfflineState, player, content: action.content, done: total === 0 && presentationSteps(player).length === 0 };
    }
    case "nextStep":
    case "previousStep":
      return { ...state, justSaved: false, player: playerReducer(state.player, action) };
    case "ready": {
      // A lesson with no items ends after its steps.
      if (state.player.phase === "presenting" && !currentItem(state.player)) return { ...state, done: true };
      return { ...state, justSaved: false, player: playerReducer(state.player, action) };
    }
    case "hint": {
      const item = offlineItem(state);
      if (!item || !canShowHint(state)) return state;
      const next = item.hints[state.player.hints.length] ?? null;
      const exhausted = state.player.hints.length + 1 >= item.hints.length;
      return { ...state, justSaved: false, player: playerReducer(state.player, { type: "hint", hint: next, exhausted }) };
    }
    case "saved": {
      if (state.player.phase !== "asking") return state;
      const total = state.player.teach?.items.length ?? 0;
      const savedCount = state.savedCount + 1;
      if (state.player.itemIndex + 1 >= total) return { ...state, savedCount, justSaved: true, done: true };
      return { ...state, savedCount, justSaved: true, player: playerReducer(state.player, { type: "nextItem" }) };
    }
  }
}

// ---- persistence -------------------------------------------------------------------------------------

export interface RunnerDeps {
  getLesson: (lessonId: string) => Promise<OfflineContent | undefined>;
  progress: ProgressStore;
  checkpoints: CheckpointStore;
  queue: SyncQueue;
}

export interface OpenedLesson {
  content: OfflineContent;
  checkpoint: SessionCheckpoint;
  /** How many items were already answered (0 = a fresh start). */
  resumeAt: number;
}

export function createOfflineRunner(deps: RunnerDeps, studentRef: string) {
  return {
    /** Open an installed lesson, resuming its latest checkpoint if there is one. Null if not installed. */
    async open(lessonId: string): Promise<OpenedLesson | null> {
      const content = await deps.getLesson(lessonId);
      if (!content) return null;
      const existing = await deps.checkpoints.latestForLesson(studentRef, lessonId);
      if (existing) return { content, checkpoint: existing, resumeAt: existing.item_index };
      const checkpoint = await deps.checkpoints.start({ student_ref: studentRef, lesson_id: lessonId, objective_code: content.objective_code });
      await deps.progress.record({ student_ref: studentRef, lesson_id: lessonId, objective_code: content.objective_code, kind: "lesson_opened" });
      return { content, checkpoint, resumeAt: 0 };
    },

    /** Save one answer durably: progress event -> queued attempt (same id) -> checkpoint. */
    async answer(input: {
      checkpoint: SessionCheckpoint;
      item: OfflineItem;
      option: number;
      hintsUsed: number;
      responseTimeMs?: number;
    }): Promise<SessionCheckpoint> {
      const { checkpoint, item } = input;
      const event = await deps.progress.record({
        student_ref: studentRef,
        lesson_id: checkpoint.lesson_id,
        objective_code: item.objective_code,
        kind: "item_attempted",
        item_ref: item.item_ref,
        selected_option: input.option,
      });
      await deps.queue.enqueueAttempt({
        student_ref: studentRef,
        objective_code: item.objective_code,
        item_ref: item.item_ref,
        option: input.option,
        evidence_id: event.client_event_id,
        // Same correlation key reconcileAndResume uses for offline attempts.
        session_id: checkpoint.lesson_id,
        hints_used: input.hintsUsed,
        ...(input.responseTimeMs !== undefined ? { response_time_ms: input.responseTimeMs } : {}),
        context: "practice",
      });
      return deps.checkpoints.advance(checkpoint, item.item_ref);
    },

    /** The lesson is finished: record it and drop the checkpoint, so the next open starts fresh. */
    async complete(checkpoint: SessionCheckpoint): Promise<void> {
      await deps.progress.record({
        student_ref: studentRef,
        lesson_id: checkpoint.lesson_id,
        objective_code: checkpoint.objective_code,
        kind: "lesson_completed",
      });
      await deps.checkpoints.clear(checkpoint.session_id);
    },

    /** Start this lesson again from the beginning (answers already saved stay queued). */
    async restart(checkpoint: SessionCheckpoint): Promise<SessionCheckpoint> {
      await deps.checkpoints.clear(checkpoint.session_id);
      return deps.checkpoints.start({ student_ref: studentRef, lesson_id: checkpoint.lesson_id, objective_code: checkpoint.objective_code });
    },
  };
}

export type OfflineRunner = ReturnType<typeof createOfflineRunner>;
