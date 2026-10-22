// Per-learner assignment progress in plain words. Pure; unit-tested.
//
// Built only from GET .../assignments/{id}/progress. "Completed" in the API means "practised this
// objective since it was assigned" — not "finished" — so the label says "Practised". Mastery
// states come from the learning engine's vocabulary; an unknown state is shown as "not known yet"
// rather than echoed raw.

import type { MessageKey } from "../i18n/messages";
import type { AssignmentProgress, LearnerAssignmentProgress } from "./types";

export type LearnerStatus = "mastered" | "practised" | "overdue" | "not-started";

export const STATUS_KEYS: Record<LearnerStatus, MessageKey> = {
  mastered: "teacher.progress.status.mastered",
  practised: "teacher.progress.status.practised",
  overdue: "teacher.progress.status.overdue",
  "not-started": "teacher.progress.status.notStarted",
};

const MASTERY_KEYS: Record<string, MessageKey> = {
  not_started: "teacher.progress.mastery.not_started",
  in_progress: "teacher.progress.mastery.in_progress",
  mastered: "teacher.progress.mastery.mastered",
  needs_review: "teacher.progress.mastery.needs_review",
  at_risk: "teacher.progress.mastery.at_risk",
};

export function masteryKey(state: string): MessageKey {
  return MASTERY_KEYS[state] ?? "teacher.progress.mastery.unknown";
}

export function learnerStatus(row: LearnerAssignmentProgress, overdue: boolean): LearnerStatus {
  if (row.mastered) return "mastered";
  if (row.completed) return "practised";
  return overdue ? "overdue" : "not-started";
}

export interface ProgressRow {
  ref: string;
  name: string | null;
  status: LearnerStatus;
  statusKey: MessageKey;
  /** Whether the status needs the teacher's attention (shown with a mark, not colour alone). */
  attention: boolean;
  attempts: number;
  masteryKey: MessageKey;
  /** 0..1, or null when the engine has no estimate yet. */
  mastery: number | null;
}

export interface ProgressView {
  overdue: boolean;
  rows: ProgressRow[];
  summary: { total: number; practised: number; mastered: number; notStarted: number };
}

const ORDER: Record<LearnerStatus, number> = { overdue: 0, "not-started": 1, practised: 2, mastered: 3 };

export function progressView(progress: AssignmentProgress): ProgressView {
  const rows = progress.learners.map((l): ProgressRow => {
    const status = learnerStatus(l, progress.overdue);
    return {
      ref: l.student_ref,
      name: l.display_name.trim() ? l.display_name : null,
      status,
      statusKey: STATUS_KEYS[status],
      attention: status === "overdue",
      attempts: Math.max(0, l.attempts_since_assigned | 0),
      masteryKey: masteryKey(l.mastery_state),
      mastery: typeof l.mastery === "number" && Number.isFinite(l.mastery) ? Math.min(1, Math.max(0, l.mastery)) : null,
    };
  });
  // Learners who need attention first, then by name.
  rows.sort((a, b) => ORDER[a.status] - ORDER[b.status] || (a.name ?? "￿").localeCompare(b.name ?? "￿"));
  return {
    overdue: progress.overdue,
    rows,
    summary: {
      total: rows.length,
      practised: rows.filter((r) => r.status === "practised" || r.status === "mastered").length,
      mastered: rows.filter((r) => r.status === "mastered").length,
      notStarted: rows.filter((r) => r.status === "not-started" || r.status === "overdue").length,
    },
  };
}
