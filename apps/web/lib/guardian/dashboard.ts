// Family dashboard states — what /guardian shows, as a pure function of two requests. Unit-tested.
//
// The dashboard reads two services that can fail independently:
//
// - `GET /v1/identity/me` — the guardian's learners: names, account status, consent. This is the
//   source of truth for "who is in my family". A child enrolled a minute ago is here.
// - `GET /v1/guardian/dashboard` — per-child learning summaries. Its child list is resolved by the
//   guardian service (being moved from the TALEEM_GUARDIAN_LINKS config to identity enrolments), so
//   for a while it may lag or differ from the identity list.
//
// The rows are therefore the UNION of both, keyed by `student_ref`, in identity order. A request
// that fails degrades its half of the card ("progress unavailable") rather than blanking the page;
// only when both fail is the whole screen a failure. A child with no answered question yet shows "no
// progress yet", never a row of zeros and a 0% accuracy they did not earn.

import type { GuardianProfile, Learner } from "../session/types";
import { classifyLoadError, type LoadFailure } from "../student/journey";
import { consentStatus, type ConsentStatus } from "./consent";
import type { ChildSummary, GuardianDashboard } from "./types";

export type Request<T> =
  | { status: "pending" }
  | { status: "ok"; value: T }
  | { status: "error"; error: unknown };

export type ChildAccess =
  | ConsentStatus
  /** Too many wrong PINs: the guardian must set a new PIN. */
  | "locked"
  /** Suspended by an operator. */
  | "suspended"
  /** Identity could not be read, so access is not known. */
  | "unknown";

export type ChildProgress =
  | { kind: "none-yet" }
  | { kind: "summary"; summary: ChildSummary }
  | { kind: "unavailable" };

export interface ChildRow {
  studentRef: string;
  /** Null when only the guardian service knows the child (identity unavailable or not yet linked). */
  name: string | null;
  gradeLevel: number | null;
  access: ChildAccess;
  canSignIn: boolean;
  progress: ChildProgress;
}

export type FamilyDashboardModel =
  | { kind: "loading" }
  | { kind: "failed"; failure: LoadFailure }
  /** A newly registered guardian: nobody enrolled yet. */
  | { kind: "no-children" }
  | {
      kind: "children";
      children: ChildRow[];
      /** The learning service failed: progress is missing on every card. */
      progressUnavailable: boolean;
      /** Identity failed: names and permission status are missing. */
      identityUnavailable: boolean;
      /** Every child is enrolled but none has answered a question yet. */
      noProgressYet: boolean;
    };

const FAILURE_PRIORITY: LoadFailure[] = ["signed-out", "offline", "error"];

function worst(...errors: unknown[]): LoadFailure {
  const kinds = errors.map(classifyLoadError);
  return FAILURE_PRIORITY.find((k) => kinds.includes(k)) ?? "error";
}

export function childAccess(learner: Learner): ChildAccess {
  if (learner.status === "locked") return "locked";
  if (learner.status === "suspended") return "suspended";
  return consentStatus(learner.consent);
}

function progressOf(summary: ChildSummary | undefined, available: boolean): ChildProgress {
  if (!available) return { kind: "unavailable" };
  // In the identity list but not (yet) in the guardian service's: nothing has been recorded the
  // guardian can be shown. The honest reading is "no progress yet", not a failure.
  if (!summary) return { kind: "none-yet" };
  if (summary.progress.total_attempts <= 0) return { kind: "none-yet" };
  return { kind: "summary", summary };
}

export function familyDashboardModel(input: {
  identity: Request<GuardianProfile>;
  dashboard: Request<GuardianDashboard>;
}): FamilyDashboardModel {
  const { identity, dashboard } = input;
  if (identity.status === "pending" || dashboard.status === "pending") return { kind: "loading" };
  if (identity.status === "error" && dashboard.status === "error") {
    return { kind: "failed", failure: worst(identity.error, dashboard.error) };
  }
  // A lost session is a lost session even if the other request squeaked through first.
  if (identity.status === "error" && classifyLoadError(identity.error) === "signed-out") {
    return { kind: "failed", failure: "signed-out" };
  }
  if (dashboard.status === "error" && classifyLoadError(dashboard.error) === "signed-out") {
    return { kind: "failed", failure: "signed-out" };
  }

  const learners = identity.status === "ok" ? identity.value.learners : [];
  const summaries = dashboard.status === "ok" ? dashboard.value.children : [];
  const byRef = new Map(summaries.map((s) => [s.student_ref, s]));
  const progressAvailable = dashboard.status === "ok";

  const rows: ChildRow[] = learners.map((learner) => ({
    studentRef: learner.student_ref,
    name: learner.display_name,
    gradeLevel: learner.grade_level,
    access: childAccess(learner),
    canSignIn: learner.can_sign_in,
    progress: progressOf(byRef.get(learner.student_ref), progressAvailable),
  }));
  const known = new Set(rows.map((r) => r.studentRef));
  for (const summary of summaries) {
    if (known.has(summary.student_ref)) continue;
    rows.push({
      studentRef: summary.student_ref,
      name: null,
      gradeLevel: null,
      access: "unknown",
      canSignIn: false,
      progress: progressOf(summary, true),
    });
  }

  if (rows.length === 0) return { kind: "no-children" };
  return {
    kind: "children",
    children: rows,
    progressUnavailable: !progressAvailable,
    identityUnavailable: identity.status === "error",
    noProgressYet: progressAvailable && rows.every((r) => r.progress.kind === "none-yet"),
  };
}

/** The family-level next step a guardian should see first, if any. */
export type FamilyNudge = "add-child" | "give-permission" | "unlock" | null;

export function familyNudge(model: FamilyDashboardModel): FamilyNudge {
  if (model.kind === "no-children") return "add-child";
  if (model.kind !== "children") return null;
  if (model.children.some((c) => c.access === "locked")) return "unlock";
  // A deliberate withdrawal is the guardian's decision and is not nagged about; a child who was
  // never given permission (or whose permission predates a policy change) cannot start at all.
  if (model.children.some((c) => c.access === "not-given" || c.access === "policy-changed")) {
    return "give-permission";
  }
  return null;
}
