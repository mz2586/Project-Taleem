// Why a recommendation was made — the structured rationale in plain words. Pure; tested.
//
// Contract: packages/contracts/ai-teacher.openapi.yaml (`Reason`, `ExplainedRecommendation`). The
// server sends stable reason codes with parameters (never English sentences); this module turns
// each into a catalog key + parameters for one of two audiences:
//
// - "student": short, warm, no numbers (the "Why this next?" view on Today);
// - "adult":   teachers and guardians — the numbers behind the reason (mastery, the mastery goal,
//              uncertainty, evidence counts), so a teacher can see *why*.
//
// An unknown code (a newer server) still gets a neutral line, never the raw code or an empty one.
// Probabilities arrive in [0, 1] and are shown as whole percentages.

import type { MessageKey } from "../i18n/messages";

export interface ReasonWire {
  code: string;
  params?: Record<string, string | number>;
}

export interface EvidenceCountsWire {
  practice: number;
  practice_correct: number;
  diagnostic: number;
  diagnostic_correct: number;
  last_at?: number | null;
}

export interface ExplainedRecommendationWire {
  kind: string;
  objective_code: string | null;
  is_next_action?: boolean;
  reasons: ReasonWire[];
  confidence: string;
  mastery: number | null;
  uncertainty: number | null;
  state?: string;
  evidence?: EvidenceCountsWire;
  estimate_source?: string;
}

export interface PlacementSummaryWire {
  placed: boolean;
  placement_id: string | null;
  objectives_secure: number;
  objectives_not_yet: number;
  objectives_uncertain: number;
}

export type Audience = "student" | "adult";

export type LineParams = Record<string, string | number>;

export interface ReasonLine {
  key: MessageKey;
  params?: LineParams;
}

/** The codes this client knows. Must match the server's `ReasonCode` (tested). */
export const REASON_CODES = [
  "safety_gate",
  "review_due",
  "misconception_active",
  "high_uncertainty",
  "ready_for_new",
  "mastery_below_threshold",
  "prerequisite_gap",
  "diagnostic_placement",
  "placed_above",
  "retention_at_risk",
  "repeated_failure",
  "mastery_reached",
  "all_mastered",
] as const;
export type ReasonCode = (typeof REASON_CODES)[number];

const PLACEMENT_STATUSES = ["secure", "not_yet", "uncertain"] as const;
type PlacementStatus = (typeof PLACEMENT_STATUSES)[number];

function isCode(value: string): value is ReasonCode {
  return (REASON_CODES as readonly string[]).includes(value);
}

function str(params: ReasonWire["params"], name: string): string {
  const v = params?.[name];
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : "";
}

function num(params: ReasonWire["params"], name: string): number {
  const v = params?.[name];
  const n = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
  return Number.isFinite(n) ? n : 0;
}

/** A probability in [0, 1] as a whole percentage (clamped). */
export function pct(value: number | null | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.round(Math.min(1, Math.max(0, value)) * 100);
}

function placementStatus(params: ReasonWire["params"]): PlacementStatus {
  const s = str(params, "status");
  return (PLACEMENT_STATUSES as readonly string[]).includes(s) ? (s as PlacementStatus) : "uncertain";
}

/** One reason, in words, for one audience. */
export function reasonLine(reason: ReasonWire, audience: Audience): ReasonLine {
  const p = reason.params;
  const code = reason.code;
  if (!isCode(code)) return { key: audience === "student" ? "common.rationale.student.other" : "common.rationale.adult.other" };
  const objective = str(p, "objective");

  if (audience === "student") {
    switch (code) {
      case "diagnostic_placement":
        return { key: `common.rationale.student.diagnostic_placement.${placementStatus(p)}` };
      case "review_due":
        return { key: "common.rationale.student.review_due" };
      case "placed_above":
        return { key: "common.rationale.student.placed_above", params: { count: num(p, "count") } };
      default:
        return { key: `common.rationale.student.${code}` };
    }
  }

  switch (code) {
    case "safety_gate":
    case "all_mastered":
      return { key: `common.rationale.adult.${code}` };
    case "review_due":
      return {
        key: "common.rationale.adult.review_due",
        params: { objective, days: Math.max(0, Math.round(num(p, "days_overdue"))), count: num(p, "due_count") },
      };
    case "misconception_active":
      return {
        key: "common.rationale.adult.misconception_active",
        params: { objective, misconception: str(p, "misconception"), count: num(p, "evidence_count") },
      };
    case "high_uncertainty":
      return { key: "common.rationale.adult.high_uncertainty", params: { objective, uncertainty: pct(num(p, "uncertainty")) } };
    case "ready_for_new":
      return { key: "common.rationale.adult.ready_for_new", params: { objective } };
    case "mastery_below_threshold":
    case "mastery_reached":
      return {
        key: `common.rationale.adult.${code}`,
        params: { objective, mastery: pct(num(p, "mastery")), threshold: pct(num(p, "threshold")) },
      };
    case "prerequisite_gap":
      return { key: "common.rationale.adult.prerequisite_gap", params: { objective, prereq: str(p, "prereq") } };
    case "diagnostic_placement": {
      const inferred = str(p, "inferred_from");
      if (inferred) {
        return { key: "common.rationale.adult.diagnostic_placement.inferred", params: { objective, from: inferred } };
      }
      return {
        key: `common.rationale.adult.diagnostic_placement.${placementStatus(p)}`,
        params: {
          objective,
          correct: num(p, "correct"),
          incorrect: num(p, "incorrect"),
          prior: pct(num(p, "prior")),
          uncertainty: pct(num(p, "uncertainty")),
        },
      };
    }
    case "placed_above":
      return { key: "common.rationale.adult.placed_above", params: { count: num(p, "count") } };
    case "retention_at_risk":
      return { key: "common.rationale.adult.retention_at_risk", params: { objective, mastery: pct(num(p, "mastery")) } };
    case "repeated_failure":
      return { key: "common.rationale.adult.repeated_failure", params: { objective, count: num(p, "consecutive_failures") } };
  }
}

/** Every reason, in order, without repeating the same sentence. */
export function reasonLines(reasons: readonly ReasonWire[] | undefined, audience: Audience): ReasonLine[] {
  const seen = new Set<string>();
  const out: ReasonLine[] = [];
  for (const r of reasons ?? []) {
    if (!r || typeof r.code !== "string") continue;
    const line = reasonLine(r, audience);
    const id = `${line.key}|${JSON.stringify(line.params ?? {})}`;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(line);
  }
  return out;
}

// ---- a recommendation, for a teacher or guardian ---------------------------------------------------

const RECOMMENDATION_KINDS = [
  "diagnose",
  "teach",
  "continue",
  "review",
  "remediate",
  "advance",
  "revise",
  "escalate",
  "rest",
  "complete",
  "practice",
] as const;
type RecommendationKind = (typeof RECOMMENDATION_KINDS)[number];

const CONFIDENCE = ["low", "medium", "high"] as const;
type Confidence = (typeof CONFIDENCE)[number];

export interface RecommendationView {
  /** What is recommended, in words. */
  kind: MessageKey;
  /** The curriculum code, shown with its own direction; null for "complete" / "rest". */
  objective: string | null;
  isNext: boolean;
  reasons: ReasonLine[];
  confidence: MessageKey;
  /** "Uncertainty: 49%" — absent when the server has no estimate for the objective. */
  uncertainty: ReasonLine | null;
  /** The evidence the estimate rests on, diagnostic and practice counted apart. */
  evidence: ReasonLine;
  /** What the estimate rests on. */
  source: MessageKey;
}

export function recommendationView(rec: ExplainedRecommendationWire): RecommendationView {
  const kind = (RECOMMENDATION_KINDS as readonly string[]).includes(rec.kind) ? (rec.kind as RecommendationKind) : null;
  const confidence: Confidence = (CONFIDENCE as readonly string[]).includes(rec.confidence) ? (rec.confidence as Confidence) : "low";
  const ev = rec.evidence;
  const practice = ev?.practice ?? 0;
  const diagnostic = ev?.diagnostic ?? 0;
  const evidence: ReasonLine =
    practice + diagnostic === 0
      ? { key: "common.rationale.evidence.none" }
      : {
          key: "common.rationale.evidence.counts",
          params: {
            practice,
            practiceCorrect: ev?.practice_correct ?? 0,
            diagnostic,
            diagnosticCorrect: ev?.diagnostic_correct ?? 0,
          },
        };
  const source = rec.estimate_source === "practice" || rec.estimate_source === "diagnostic" ? rec.estimate_source : "none";
  return {
    kind: kind ? `common.rationale.kind.${kind}` : "common.rationale.kind.other",
    objective: rec.objective_code ?? null,
    isNext: rec.is_next_action === true,
    reasons: reasonLines(rec.reasons, "adult"),
    confidence: `common.rationale.confidence.${confidence}`,
    uncertainty:
      typeof rec.uncertainty === "number" ? { key: "common.rationale.uncertainty", params: { value: pct(rec.uncertainty) } } : null,
    evidence,
    source: `common.rationale.source.${source}`,
  };
}

/** The list a teacher or guardian reads: next action first (the server's order), bounded. */
export function recommendationViews(list: readonly ExplainedRecommendationWire[] | undefined, limit = 6): RecommendationView[] {
  return (Array.isArray(list) ? list : []).slice(0, limit).map(recommendationView);
}
