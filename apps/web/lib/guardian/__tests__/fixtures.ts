// Shared fixtures for the guardian journey tests — shaped exactly like the identity and guardian
// API responses (packages/contracts/identity.openapi.yaml, guardian.openapi.yaml).
import type { ConsentScope, ConsentState, GuardianProfile, Learner } from "../../session/types";
import type { ChildSummary, GuardianDashboard } from "../types";

export const POLICY_VERSION = "2026-09-consent-v1";

export function consent(over: Partial<ConsentState> = {}): ConsentState {
  return {
    student_ref: "stu_1",
    granted_scopes: [],
    policy_version: "",
    current_policy_version: POLICY_VERSION,
    policy_current: false,
    permits_sign_in: false,
    granted_at: 0,
    last_change_at: 0,
    ...over,
  };
}

/** Live, current-policy consent for the given scopes. */
export function granted(scopes: ConsentScope[], over: Partial<ConsentState> = {}): ConsentState {
  return consent({
    granted_scopes: scopes,
    policy_version: POLICY_VERSION,
    policy_current: true,
    permits_sign_in: scopes.includes("learning_data"),
    granted_at: 1_700_000_000,
    last_change_at: 1_700_000_000,
    ...over,
  });
}

export function learner(over: Partial<Learner> = {}): Learner {
  const c = over.consent ?? consent({ student_ref: over.student_ref ?? "stu_1" });
  return {
    student_ref: "stu_1",
    display_name: "Ali",
    grade_band: "middle",
    grade_level: 4,
    locale: "ur",
    status: "active",
    created_at: 1_700_000_000,
    can_sign_in: c.permits_sign_in,
    ...over,
    consent: c,
  };
}

export function profile(learners: Learner[]): GuardianProfile {
  return {
    guardian: {
      guardian_ref: "gdn_1",
      email: "parent@example.org",
      display_name: "Ayesha",
      family_code: "K7QM-3XPZ",
      locale: "ur",
      status: "active",
      created_at: 1_700_000_000,
    },
    learners,
    policy_version: POLICY_VERSION,
  };
}

export function summary(ref: string, over: Partial<ChildSummary["progress"]> = {}, extra: Partial<ChildSummary> = {}): ChildSummary {
  return {
    student_ref: ref,
    progress: { objectives_mastered: 0, objectives_in_progress: 0, accuracy: 0, total_attempts: 0, ...over },
    streak: { current: 0, longest: 0, last_active_day: null },
    sync_status: { last_synced_at: null, is_stale: true, seconds_since_sync: null, pending_is_device_reported: true },
    open_interventions: 0,
    achievements_count: 0,
    ...extra,
  };
}

export function dashboard(children: ChildSummary[]): GuardianDashboard {
  return { guardian_ref: "gdn_1", child_count: children.length, children };
}
