// Normalising the progression wire into plain values. Pure. Every tolerance for an open field
// spelling lives here (see ./types.ts), so the view models and pages never touch raw wire objects.
//
// Honesty rules applied at the edge:
// - an unknown lesson or unit state reads as "not started" — never as practised, mastered or passed;
// - "completed" (practice finished) and "mastered" (demonstrated) are separate states and are never
//   merged: a lesson is mastered only when the server says `mastered`;
// - an expired unfinished sitting is `incomplete`, never a failure (§2);
// - "passed" comes from the server; it is derived from the pass mark only when the flag is absent.

import { pickLocalized, type LocalizedText } from "../i18n/content";
import type {
  AnswerResultWire,
  CheckItemWire,
  FinishWire,
  LessonState,
  LocalizedWire,
  NextStepWire,
  ObjectiveResultWire,
  PathWire,
  RecordSittingWire,
  RecordWire,
  SittingWire,
  TimeWire,
  UnitCheckSummaryWire,
  UnitState,
} from "./types";

export const DEFAULT_PASS_MARK = 70;

// ---- primitives -----------------------------------------------------------------------------------

export function localized(value: LocalizedWire | null | undefined, preference: readonly string[]): LocalizedText | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.trim() ? { text: value, locale: "" } : null;
  if (typeof value !== "object") return null;
  return pickLocalized(value, preference);
}

/** Epoch seconds from seconds, milliseconds or ISO-8601; null when absent or unreadable. */
export function toSeconds(value: TimeWire | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") {
    if (!Number.isFinite(value) || value <= 0) return null;
    return value > 1e12 ? Math.floor(value / 1000) : value;
  }
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? Math.floor(ms / 1000) : null;
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? Math.floor(value) : 0;
}

function percent(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  // A ratio (0–1) is read as a fraction only when it is not a whole percentage like 1.
  const pct = value > 0 && value < 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(pct)));
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

// ---- states (§1) ----------------------------------------------------------------------------------

const LESSON_ALIASES: Record<string, LessonState> = {
  not_started: "not_started",
  in_progress: "in_progress",
  started: "in_progress",
  practised: "practised",
  practiced: "practised",
  completed: "practised",
  mastered: "mastered",
  demonstrated: "mastered",
};

const UNIT_ALIASES: Record<string, UnitState> = {
  not_started: "not_started",
  in_progress: "in_progress",
  started: "in_progress",
  ready_for_check: "ready_for_check",
  ready: "ready_for_check",
  completed: "completed",
  passed: "completed",
};

export function lessonState(raw: string | null | undefined): LessonState {
  return (raw && LESSON_ALIASES[raw]) || "not_started";
}

export function unitState(raw: string | null | undefined): UnitState {
  return (raw && UNIT_ALIASES[raw]) || "not_started";
}

// ---- path -----------------------------------------------------------------------------------------

export interface LessonView {
  lessonId: string;
  objectiveCode: string;
  title: LocalizedText | null;
  state: LessonState;
}

export interface CheckSummary {
  available: boolean;
  bestScore: number | null;
  passed: boolean;
  lastSittingId: string | null;
  openSittingId: string | null;
  /** null: the server did not say (the retake rule is then explained, not decided, here). */
  canRetake: boolean | null;
  retakeAfter: number | null;
  itemCount: number | null;
  passMark: number;
}

export interface UnitView {
  key: string;
  title: LocalizedText | null;
  state: UnitState;
  lessons: LessonView[];
  check: CheckSummary;
}

export interface SubjectView {
  key: string;
  title: LocalizedText | null;
  units: UnitView[];
}

export type NextStepKind = "lesson" | "unit_check";

export interface NextStepView {
  kind: NextStepKind;
  title: LocalizedText | null;
  unitKey: string | null;
}

export interface PathView {
  grade: number | null;
  gradeCompleted: boolean;
  subjects: SubjectView[];
  nextStep: NextStepView | null;
}

export function checkSummary(wire: UnitCheckSummaryWire | null | undefined): CheckSummary {
  const w = wire ?? {};
  const bestScore = percent(w.best_score);
  return {
    available: w.available === true,
    bestScore,
    passed: w.passed === true,
    lastSittingId: str(w.last_sitting_id) || null,
    openSittingId: str(w.open_sitting_id) || null,
    canRetake: typeof w.can_retake === "boolean" ? w.can_retake : null,
    retakeAfter: toSeconds(w.retake_after),
    itemCount: typeof w.item_count === "number" && w.item_count > 0 ? Math.floor(w.item_count) : null,
    passMark: percent(w.pass_mark) ?? DEFAULT_PASS_MARK,
  };
}

function nextStep(wire: NextStepWire | null | undefined, preference: readonly string[]): NextStepView | null {
  if (wire === null || wire === undefined) return null;
  if (typeof wire === "string") {
    const title = localized(wire, preference);
    return title ? { kind: "lesson", title, unitKey: null } : null;
  }
  if (typeof wire !== "object") return null;
  const kind: NextStepKind = wire.kind === "unit_check" || wire.kind === "check" ? "unit_check" : "lesson";
  const unitKey = str(wire.unit_key) || null;
  const title = localized(wire.title, preference);
  if (kind === "unit_check" && !unitKey) return title ? { kind: "lesson", title, unitKey: null } : null;
  if (!title && kind === "lesson") return null;
  return { kind, title, unitKey };
}

export function pathView(wire: PathWire | null | undefined, preference: readonly string[]): PathView {
  const w = wire ?? {};
  const subjects: SubjectView[] = (w.subjects ?? []).map((s, si) => ({
    key: str(s.subject_key) || `subject-${si}`,
    title: localized(s.title, preference),
    units: (s.units ?? []).map((u, ui) => ({
      key: str(u.unit_key) || `unit-${si}-${ui}`,
      title: localized(u.title, preference),
      state: unitState(u.state),
      lessons: (u.lessons ?? []).map((l, li) => ({
        lessonId: str(l.lesson_id) || `lesson-${si}-${ui}-${li}`,
        objectiveCode: str(l.objective_code),
        title: localized(l.title, preference),
        state: lessonState(l.state),
      })),
      check: checkSummary(u.check),
    })),
  }));
  const allUnits = subjects.flatMap((s) => s.units);
  return {
    grade: typeof w.grade === "number" && Number.isFinite(w.grade) ? w.grade : null,
    gradeCompleted: w.grade_state === "completed" || (allUnits.length > 0 && allUnits.every((u) => u.state === "completed")),
    subjects,
    nextStep: nextStep(w.next_step, preference),
  };
}

export function findUnit(path: PathView, unitKey: string): UnitView | null {
  for (const s of path.subjects) for (const u of s.units) if (u.key === unitKey) return u;
  return null;
}

// ---- sitting (§2) ---------------------------------------------------------------------------------

export interface CheckItemView {
  item_ref: string;
  kind: string | null;
  prompt: LocalizedText | null;
  options: string[];
  left_count: number | null;
}

export type SittingState = "open" | "finished" | "incomplete";

export interface SittingView {
  sittingId: string;
  unitKey: string;
  expiresAt: number | null;
  total: number;
  answered: number;
  item: CheckItemView | null;
  state: SittingState;
}

export function checkItem(wire: CheckItemWire | null | undefined, preference: readonly string[]): CheckItemView | null {
  if (!wire || typeof wire !== "object" || !str(wire.item_ref)) return null;
  return {
    item_ref: wire.item_ref,
    kind: str(wire.kind) || null,
    prompt: localized(wire.prompt, preference),
    options: Array.isArray(wire.options) ? wire.options.map((o) => String(o)) : [],
    left_count: typeof wire.left_count === "number" ? wire.left_count : null,
  };
}

export function sittingView(wire: SittingWire, unitKey: string, preference: readonly string[]): SittingView {
  const total = count(wire.total);
  const answered = Math.min(count(wire.answered), total || Number.MAX_SAFE_INTEGER);
  const raw = str(wire.state);
  const state: SittingState =
    raw === "finished" || raw === "scored" ? "finished" : raw === "incomplete" || raw === "expired" ? "incomplete" : "open";
  return {
    sittingId: wire.sitting_id,
    unitKey: str(wire.unit_key) || unitKey,
    expiresAt: toSeconds(wire.expires_at),
    total,
    answered,
    item: checkItem(wire.item, preference),
    state,
  };
}

/** The sitting after an accepted answer: counts from the server, the next item (or none left). */
export function afterAnswer(sitting: SittingView, wire: AnswerResultWire | null | undefined, preference: readonly string[]): SittingView {
  const w = wire ?? {};
  const total = count(w.total) || sitting.total;
  const answered = Math.min(typeof w.answered === "number" ? count(w.answered) : sitting.answered + 1, total);
  return { ...sitting, total, answered, item: checkItem(w.next_item, preference) };
}

// ---- result (§2) ----------------------------------------------------------------------------------

export interface ObjectiveResult {
  code: string;
  title: LocalizedText | null;
  correct: number;
  total: number;
}

export interface RemediationTarget {
  code: string;
  title: LocalizedText | null;
}

export interface CheckResult {
  scorePercent: number;
  passed: boolean;
  passMark: number;
  perObjective: ObjectiveResult[];
  remediation: RemediationTarget[];
  retakeAfter: number | null;
}

function objectiveResults(list: ObjectiveResultWire[] | null | undefined, preference: readonly string[]): ObjectiveResult[] {
  return (list ?? []).map((o) => {
    const total = count(o.total);
    return { code: str(o.objective_code), title: localized(o.title, preference), correct: Math.min(count(o.correct), total), total };
  });
}

export function checkResult(wire: FinishWire | null | undefined, preference: readonly string[]): CheckResult {
  const w = wire ?? {};
  const perObjective = objectiveResults(w.per_objective, preference);
  const passMark = percent(w.pass_mark) ?? DEFAULT_PASS_MARK;
  // §2: one point per correct item — the per-objective breakdown reproduces the score if it is absent.
  const items = perObjective.reduce((n, o) => n + o.total, 0);
  const correct = perObjective.reduce((n, o) => n + o.correct, 0);
  const scorePercent = percent(w.score_percent) ?? (items > 0 ? Math.round((correct / items) * 100) : 0);
  const passed = typeof w.passed === "boolean" ? w.passed : scorePercent >= passMark;
  const remediation = (w.remediation ?? []).map((r) => ({ code: str(r.objective_code), title: localized(r.title, preference) }));
  return { scorePercent, passed, passMark, perObjective, remediation, retakeAfter: toSeconds(w.retake_after) };
}

// ---- record (§3) ----------------------------------------------------------------------------------

export interface RecordSitting {
  sittingId: string;
  unitKey: string;
  unitTitle: LocalizedText | null;
  at: number | null;
  state: "finished" | "incomplete";
  scorePercent: number | null;
  passed: boolean;
  perObjective: ObjectiveResult[];
}

export interface RecordUnit {
  key: string;
  title: LocalizedText | null;
  state: UnitState;
  /** Newest first. */
  sittings: RecordSitting[];
  best: { scorePercent: number; passed: boolean } | null;
}

export interface RecordSubject {
  key: string;
  title: LocalizedText | null;
  units: RecordUnit[];
}

export interface MasteredLesson {
  lessonId: string;
  objectiveCode: string;
  title: LocalizedText | null;
}

export interface AcademicRecord {
  grade: number | null;
  /** The grade-completion entry (§3), present only when the server derived it. */
  gradeCompletion: { grade: number | null; at: number | null } | null;
  subjects: RecordSubject[];
  lessonsMasteredCount: number;
  lessonsMastered: MasteredLesson[];
  reportCards: Array<{ cardId: string; periodStart: number | null; periodEnd: number | null; issuedAt: number | null }>;
  derivedAt: number | null;
}

function recordSitting(s: RecordSittingWire, fallbackUnit: string, preference: readonly string[]): RecordSitting {
  const scored = typeof s.score_percent === "number";
  const raw = str(s.state);
  const state = raw === "incomplete" || raw === "expired" || (!raw && !scored) ? "incomplete" : "finished";
  return {
    sittingId: str(s.sitting_id),
    unitKey: str(s.unit_key) || fallbackUnit,
    unitTitle: localized(s.unit_title, preference),
    at: toSeconds(s.finished_at) ?? toSeconds(s.started_at),
    state,
    scorePercent: state === "finished" ? percent(s.score_percent) : null,
    passed: state === "finished" && s.passed === true,
    perObjective: objectiveResults(s.per_objective, preference),
  };
}

/** The best finished sitting: highest score, a pass beating a non-pass at the same score. */
export function bestResult(sittings: readonly RecordSitting[]): { scorePercent: number; passed: boolean } | null {
  let best: { scorePercent: number; passed: boolean } | null = null;
  for (const s of sittings) {
    if (s.state !== "finished" || s.scorePercent === null) continue;
    if (!best || s.scorePercent > best.scorePercent || (s.scorePercent === best.scorePercent && s.passed && !best.passed)) {
      best = { scorePercent: s.scorePercent, passed: s.passed };
    }
  }
  return best;
}

export function academicRecord(wire: RecordWire | null | undefined, preference: readonly string[]): AcademicRecord {
  const w = wire ?? {};
  const topLevel = (w.sittings ?? []).map((s) => recordSitting(s, "", preference));
  const seen = new Set<string>();
  const subjects: RecordSubject[] = (w.subjects ?? []).map((s, si) => ({
    key: str(s.subject_key) || `subject-${si}`,
    title: localized(s.title, preference),
    units: (s.units ?? []).map((u, ui) => {
      const key = str(u.unit_key) || `unit-${si}-${ui}`;
      const nested = (u.sittings ?? []).map((x) => recordSitting(x, key, preference));
      const ids = new Set(nested.map((x) => x.sittingId).filter(Boolean));
      const merged = [...nested, ...topLevel.filter((x) => x.unitKey === key && !(x.sittingId && ids.has(x.sittingId)))];
      merged.sort((a, b) => (b.at ?? 0) - (a.at ?? 0));
      for (const x of merged) seen.add(x.sittingId || `${key}-${x.at}`);
      const fromSittings = bestResult(merged);
      const serverBest = percent(u.best_score);
      const best =
        fromSittings ?? (serverBest !== null ? { scorePercent: serverBest, passed: u.passed === true } : null);
      return { key, title: localized(u.title, preference), state: unitState(u.state), sittings: merged, best };
    }),
  }));
  // Sittings for a unit the subject tree does not list are still the child's record: keep them.
  const orphans = topLevel.filter((x) => !seen.has(x.sittingId || `${x.unitKey}-${x.at}`));
  if (orphans.length > 0) {
    const byUnit = new Map<string, RecordSitting[]>();
    for (const x of orphans) byUnit.set(x.unitKey, [...(byUnit.get(x.unitKey) ?? []), x]);
    subjects.push({
      key: "other",
      title: null,
      units: [...byUnit.entries()].map(([key, list]) => {
        list.sort((a, b) => (b.at ?? 0) - (a.at ?? 0));
        return { key, title: list.find((x) => x.unitTitle)?.unitTitle ?? null, state: "not_started", sittings: list, best: bestResult(list) };
      }),
    });
  }

  const lessons = Array.isArray(w.lessons_mastered)
    ? w.lessons_mastered.map((l, i) => ({
        lessonId: str(l.lesson_id) || `lesson-${i}`,
        objectiveCode: str(l.objective_code),
        title: localized(l.title, preference),
      }))
    : [];
  const lessonsMasteredCount = typeof w.lessons_mastered === "number" ? count(w.lessons_mastered) : lessons.length;

  const completion = w.grade_completion ?? null;
  const completedAt = toSeconds(completion?.completed_at) ?? toSeconds(w.grade_completed_at);
  const gradeCompletion =
    completion || completedAt !== null || w.grade_state === "completed"
      ? { grade: typeof completion?.grade === "number" ? completion.grade : (w.grade ?? null), at: completedAt }
      : null;

  return {
    grade: typeof w.grade === "number" && Number.isFinite(w.grade) ? w.grade : null,
    gradeCompletion,
    subjects,
    lessonsMasteredCount,
    lessonsMastered: lessons,
    reportCards: (w.report_cards ?? [])
      .filter((c) => str(c.card_id))
      .map((c) => ({
        cardId: str(c.card_id),
        periodStart: toSeconds(c.period_start),
        periodEnd: toSeconds(c.period_end),
        issuedAt: toSeconds(c.issued_at),
      })),
    derivedAt: toSeconds(w.derived_at),
  };
}
