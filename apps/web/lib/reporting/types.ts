// Wire shapes for report cards (docs/06-portals/REPORT_CARD_CONTRACT.md and
// packages/contracts/reporting.openapi.yaml).
//
// The shapes follow the server exactly. Parsing stays tolerant (an optional alias, a localized map OR
// a plain string, a missing optional field) and is normalised in exactly one place — `./wire.ts` — so
// a field-name change on the server is a one-file edit there.

export type Mastery = "mastered" | "developing" | "not_started";

/** Authored text: a `{locale: text}` map (curriculum) or a single string. */
export type LocalizedWire = string | Record<string, string>;

/** `issued_by` on a card Taleem issued itself (no teacher). */
export const SYSTEM_ISSUER = "system";

export interface ObjectiveWire {
  objective_code: string;
  title?: LocalizedWire | null;
  /** Mastery state at `period_end`. */
  mastery?: string | null;
  /** Auto-scored attempts in the period, and how many were correct. */
  attempts?: number | null;
  correct?: number | null;
  /** Homework outcomes in the period. */
  homework_met?: number | null;
  homework_not_yet?: number | null;
  /** The curriculum version pin: the published lesson this was learned from. */
  lesson_id?: string | null;
  lesson_version?: number | string | null;
}

export interface SubjectWire {
  subject_key: string;
  subject_name?: LocalizedWire | null;
  objectives?: ObjectiveWire[] | null;
}

/** Whole-card figures; `null` on a card with no evidence. */
export interface TotalsWire {
  objectives?: number | null;
  objectives_mastered?: number | null;
  attempts?: number | null;
  correct?: number | null;
  homework_met?: number | null;
  homework_not_yet?: number | null;
}

export type CardStatusWire = "issued" | "superseded" | "preview";

/** One stored card body plus read-time metadata, as every read (and a preview) returns it. */
export interface ReportCardWire {
  format?: string | null;
  derivation?: string | null;
  /** Null only on a preview. */
  card_id?: string | null;
  student_ref: string;
  learner_display_name?: string | null;
  /** Alias some older reads used for the learner's name. */
  display_name?: string | null;
  /** Null on a system card: a child does not need to be in a class. */
  class_id?: string | null;
  class_name?: string | null;
  organization_id?: string | null;
  organization_name?: string | null;
  curriculum_pack?: string | null;
  period_start: number;
  /** Exclusive (`period_rule: "start_inclusive_end_exclusive"`). */
  period_end: number;
  period_rule?: string | null;
  /** `"system"` (Taleem) or the issuing teacher's ref. */
  issued_by?: string | null;
  /** `"Taleem"` on a system card. */
  issued_by_name?: string | null;
  issued_at?: number | null;
  supersedes?: string | null;
  /** Teacher-issued cards only. */
  comment?: string | null;
  has_evidence?: boolean | null;
  /** `"no_evidence_in_period"` when nothing was recorded. */
  notice?: string | null;
  totals?: TotalsWire | null;
  subjects?: SubjectWire[] | null;
  superseded_by?: string | null;
  status?: string | null;
  acknowledged_at?: number | null;
  content_hash?: string | null;
  /** Re-verified on every read; `false` means the stored body no longer matches its hash. */
  hash_verified?: boolean | null;
}

export type SkipReasonWire = "consent_withdrawn" | "inactive" | "not_in_class" | "already_issued";

/** A learner the server left out of a preview or an issue, with its reason. */
export interface SkippedWire {
  student_ref: string;
  /** Null for a learner the teacher may not see. */
  learner_display_name?: string | null;
  display_name?: string | null;
  reason?: string | null;
  /** For `already_issued`: the current card a correction must name. */
  card_id?: string | null;
}

/** A list read: `{report_cards}` (tolerated: `{cards}`, or a bare array). */
export type ReportCardListWire = ReportCardWire[] | { report_cards?: ReportCardWire[]; cards?: ReportCardWire[] };

/** :preview and issue answers. */
export interface IssueResultWire {
  class_id?: string;
  period_start?: number;
  period_end?: number;
  /** Preview only: always false. */
  stored?: boolean;
  report_cards?: ReportCardWire[];
  /** Tolerated older spellings. */
  cards?: ReportCardWire[];
  previews?: ReportCardWire[];
  issued?: ReportCardWire[];
  skipped?: SkippedWire[];
}

/** POST …/report-cards:preview and POST …/report-cards (the same IssueIn). */
export interface PreviewBody {
  period_start: number;
  period_end: number;
  student_refs?: string[];
  supersedes?: Record<string, string>;
}

export interface IssueBody extends PreviewBody {
  comments?: Record<string, string>;
}

/** POST /v1/reporting/children/{student_ref}/report-cards:generate — a closed period. */
export interface GenerateBody {
  period_start: number;
  period_end: number;
}

/** POST /v1/reporting/report-cards/{card_id}:acknowledge */
export interface AcknowledgeWire {
  card_id?: string | null;
  acknowledged_at?: number | null;
}

/** One entry of the guardian's in-app feed: one per current card; `read` = acknowledged. */
export interface NotificationWire {
  id?: string | null;
  kind?: string | null;
  card_id?: string | null;
  student_ref?: string | null;
  class_id?: string | null;
  period_start?: number | null;
  period_end?: number | null;
  supersedes?: string | null;
  issued_at?: number | null;
  read?: boolean | null;
}

/** GET /v1/reporting/children/{student_ref}/notifications (tolerated: a bare array). */
export type NotificationListWire = NotificationWire[] | { notifications?: NotificationWire[] | null; unread?: number | null };
