// Progress presentation for guardians — summaries, the weekly digest, and the child detail view.
// Pure: strings come from the catalog through `translate`, numbers through the locale's Intl
// formatting (Western digits by default, the locale's own on request). Unit-tested.
//
// Two honesty rules, carried over from the student journey (lib/student/journey.ts):
// - Before the first answered question there is no accuracy. "0%" would tell a guardian their child
//   got everything wrong, when they have simply not started.
// - Server-generated English sentences (notification `message`, achievement `name`) are not shown
//   as interface text. Each is rebuilt from its machine-readable kind in the guardian's language;
//   only an unknown kind falls back to the server text, marked with its own direction.
//
// Phrasing is "label: value" rather than sentences with counts in them. That sidesteps plural rules
// the catalog does not model, and it is easier to scan for a guardian who reads slowly.

import type { Locale } from "../i18n/config";
import { formatPercent, type DigitStyle } from "../i18n/format";
import type { MessageKey } from "../i18n/messages";
import { translate } from "../i18n/translate";
import { objectiveName } from "../student/objectiveName";
import { formatDate } from "./format";
import type { ChildOverview, ChildSummary, Streak } from "./types";

export interface FormatContext {
  locale: Locale;
  digits?: DigitStyle;
  timeZone?: string;
}

function t(ctx: FormatContext, key: MessageKey, params?: Record<string, string | number>): string {
  return translate(ctx.locale, key, params, ctx.digits ?? "western");
}

function pct(ctx: FormatContext, ratio: number): string {
  return formatPercent(ratio, ctx.locale, { digits: ctx.digits ?? "western" });
}

// ---- dashboard card ------------------------------------------------------------------------------

export interface ChildSummaryText {
  /** 0..1, for the mastery ring. */
  masteryRatio: number;
  mastered: string;
  inProgress: string;
  /** Null before any answer. */
  accuracy: string | null;
  answered: string;
  streak: string;
  achievements: string | null;
  attention: string | null;
  sync: string;
  syncStale: boolean;
}

export function streakText(ctx: FormatContext, streak: Streak): string {
  return streak.current > 0
    ? t(ctx, "guardian.progress.streak", { count: streak.current })
    : t(ctx, "guardian.progress.noStreak");
}

export function formatChildSummary(ctx: FormatContext, summary: ChildSummary): ChildSummaryText {
  const { progress } = summary;
  const total = progress.objectives_mastered + progress.objectives_in_progress;
  return {
    masteryRatio: total > 0 ? progress.objectives_mastered / total : 0,
    mastered: t(ctx, "guardian.progress.mastered", { count: progress.objectives_mastered }),
    inProgress: t(ctx, "guardian.progress.inProgress", { count: progress.objectives_in_progress }),
    accuracy:
      progress.total_attempts > 0
        ? t(ctx, "guardian.progress.accuracy", { value: pct(ctx, progress.accuracy) })
        : null,
    answered: t(ctx, "guardian.progress.answered", { count: progress.total_attempts }),
    streak: streakText(ctx, summary.streak),
    achievements:
      summary.achievements_count > 0
        ? t(ctx, "guardian.progress.achievements", { count: summary.achievements_count })
        : null,
    attention:
      summary.open_interventions > 0
        ? t(ctx, "guardian.progress.attention", { count: summary.open_interventions })
        : null,
    sync: summary.sync_status.is_stale ? t(ctx, "guardian.sync.stale") : t(ctx, "guardian.sync.fresh"),
    syncStale: summary.sync_status.is_stale,
  };
}

// ---- weekly summary ------------------------------------------------------------------------------

export type WeeklySummaryModel =
  | { kind: "quiet"; text: string }
  | { kind: "active"; lines: string[]; encouragement: string };

/**
 * The once-a-week digest (`weekly_summary` = the trailing 7 days of sessions). A quiet week is said
 * plainly and kindly; an active week lists sessions, answers, and — only once there are answers —
 * how many were right.
 */
export function weeklySummaryModel(ctx: FormatContext, weekly: ChildOverview["weekly_summary"]): WeeklySummaryModel {
  if (!weekly || weekly.sessions <= 0) return { kind: "quiet", text: t(ctx, "guardian.weekly.quiet") };
  const lines = [
    t(ctx, "guardian.weekly.sessions", { count: weekly.sessions }),
    t(ctx, "guardian.weekly.answered", { count: weekly.attempts }),
  ];
  if (weekly.attempts > 0) {
    lines.push(t(ctx, "guardian.weekly.correct", { count: weekly.correct, value: pct(ctx, weekly.accuracy) }));
  }
  return { kind: "active", lines, encouragement: t(ctx, "guardian.weekly.encouragement") };
}

// ---- child detail ---------------------------------------------------------------------------------

/** Text that came from the server or from curriculum, not from the catalog. */
export interface ForeignText {
  text: string;
  /** True when this is content (a code, a server sentence) to be marked with its own lang/dir. */
  content: true;
  /** The authored locale, when the text is a lesson title (drives lang/dir). */
  locale?: string;
}

export interface DetailItem {
  /** Interface text in the guardian's language. */
  text: string;
  /** An objective code or server sentence shown alongside, in its own direction. */
  extra?: ForeignText;
}

export interface ChildDetailModel {
  /** False until the child has answered at least one question. */
  hasProgress: boolean;
  overview: string[];
  streak: string;
  attendance: string;
  weekly: WeeklySummaryModel;
  sync: { text: string; stale: boolean; lastSync: string | null };
  knowledge: Array<{ objective: ForeignText; value: string; ratio: number }>;
  attention: DetailItem[];
  recommendations: DetailItem[];
  nextStep: DetailItem | null;
  timeline: DetailItem[];
  assessments: DetailItem[];
  achievements: DetailItem[];
}

const RECOMMENDATION_KEYS: Record<string, MessageKey> = {
  remediate: "guardian.child.recommendation.remediate",
  review: "guardian.child.recommendation.review",
  learn: "guardian.child.recommendation.learn",
};

const NEXT_STEP_KEYS: Record<string, MessageKey> = {
  diagnose: "guardian.child.nextStep.diagnose",
  teach: "guardian.child.nextStep.teach",
  continue: "guardian.child.nextStep.continue",
  review: "guardian.child.nextStep.review",
  remediate: "guardian.child.nextStep.remediate",
  advance: "guardian.child.nextStep.advance",
  revise: "guardian.child.nextStep.revise",
  escalate: "guardian.child.nextStep.escalate",
  rest: "guardian.child.nextStep.rest",
  complete: "guardian.child.nextStep.complete",
};

const ATTENTION_KEYS: Record<string, MessageKey> = {
  revision_due: "guardian.child.attention.revision_due",
  at_risk: "guardian.child.attention.at_risk",
};

function code(text: string): ForeignText {
  return { text, content: true };
}

interface AiPlan {
  next_action?: { kind?: string; objective_code?: string | null };
  weak_topics?: unknown[];
  revision_due?: unknown[];
}

interface Assessment {
  id?: string;
  objective_code?: string;
  type?: string;
  item_count?: number;
  mentor_mediated?: boolean;
}

export function childDetailModel(ctx: FormatContext, data: ChildOverview): ChildDetailModel {
  // An objective is named by its lesson title (the guardian's language first), never its code;
  // the code is the fallback only when the server sent no title.
  const titlePreference = [ctx.locale, "ur", "en"];
  const objective = (codeText: string): ForeignText => {
    const name = objectiveName(codeText, data.objective_titles, titlePreference);
    return name.kind === "title" ? { text: name.text, content: true, locale: name.locale } : code(codeText);
  };
  const p = data.progress_overview;
  const hasProgress = (p?.total_attempts ?? 0) > 0;

  const overview = [
    t(ctx, "guardian.progress.mastered", { count: p.objectives_mastered }),
    t(ctx, "guardian.progress.inProgress", { count: p.objectives_in_progress }),
    t(ctx, "guardian.progress.answered", { count: p.total_attempts }),
  ];
  if (hasProgress) {
    overview.push(t(ctx, "guardian.progress.accuracy", { value: pct(ctx, p.accuracy) }));
    if (p.misconceptions_cleared > 0) {
      overview.push(t(ctx, "guardian.child.misconceptionsCleared", { count: p.misconceptions_cleared }));
    }
  }

  const sync = data.offline_sync_status;
  const lastSync = sync?.last_synced_at ? formatDate(sync.last_synced_at, ctx.locale, ctx) : null;

  const plan = (data.ai_teacher_activity ?? {}) as AiPlan;
  const kind = plan.next_action?.kind;
  const nextKey = kind ? NEXT_STEP_KEYS[kind] : undefined;
  const nextStep: DetailItem | null =
    hasProgress && nextKey
      ? {
          text: t(ctx, nextKey),
          ...(plan.next_action?.objective_code ? { extra: objective(plan.next_action.objective_code) } : {}),
        }
      : null;

  const assessments = ((data.assessment_history?.assessments ?? []) as Assessment[]).map((a) => ({
    text: t(ctx, a.type === "summative" ? "guardian.child.assessment.summative" : "guardian.child.assessment.formative", {
      count: a.item_count ?? 0,
    }),
    ...(a.objective_code ? { extra: objective(a.objective_code) } : {}),
  }));

  return {
    hasProgress,
    overview,
    streak:
      data.learning_streaks.current > 0
        ? t(ctx, "guardian.child.streakDetail", {
            count: data.learning_streaks.current,
            longest: data.learning_streaks.longest,
          })
        : t(ctx, "guardian.progress.noStreak"),
    attendance: t(ctx, "guardian.child.activeDays", { count: data.attendance?.active_days ?? 0 }),
    weekly: weeklySummaryModel(ctx, data.weekly_summary),
    sync: {
      text: sync?.is_stale ? t(ctx, "guardian.sync.stale") : t(ctx, "guardian.sync.fresh"),
      stale: !!sync?.is_stale,
      lastSync: lastSync ? t(ctx, "guardian.sync.lastSync", { date: lastSync }) : null,
    },
    knowledge: Object.entries(data.knowledge_growth ?? {}).map(([codeText, ratio]) => ({
      objective: objective(codeText),
      value: pct(ctx, ratio),
      ratio,
    })),
    attention: (data.intervention_notifications ?? []).map((n) => {
      const key = ATTENTION_KEYS[n.type];
      return key ? { text: t(ctx, key) } : { text: t(ctx, "guardian.child.attention.other"), extra: code(n.message) };
    }),
    recommendations: (data.recommendations ?? []).map((r) => ({
      text: t(ctx, RECOMMENDATION_KEYS[r.reason] ?? "guardian.child.recommendation.other"),
      extra: objective(r.objective_code),
    })),
    nextStep,
    timeline: (data.learning_timeline ?? []).map((s) => ({
      text: t(ctx, "guardian.child.timelineEntry", {
        date: formatDate(s.at, ctx.locale, ctx),
        attempts: s.attempts,
        correct: s.correct,
      }),
    })),
    assessments,
    achievements: (data.achievement_history ?? []).map((a) => {
      if (a.id.startsWith("mastery-")) {
        return { text: t(ctx, "guardian.child.achievement.mastered"), extra: objective(a.id.slice("mastery-".length)) };
      }
      if (a.id.startsWith("cleared-")) return { text: t(ctx, "guardian.child.achievement.cleared") };
      return { text: t(ctx, "guardian.child.achievement.other"), extra: code(a.name) };
    }),
  };
}
