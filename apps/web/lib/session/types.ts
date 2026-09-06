// Types for the identity API (packages/contracts/identity.openapi.yaml).
//
// Note what a Learner does not have: an email, a phone number, a date of birth. The type mirrors
// the database, and the database has no column for any of them.

export type Role = "student" | "guardian";
export type GradeBand = "early" | "middle" | "senior";
export type AccountStatus = "active" | "locked" | "suspended";

export type ConsentScope = "learning_data" | "ai_teaching" | "voice_audio" | "progress_sharing";

export interface AccessToken {
  access_token: string;
  token_type: "Bearer";
  expires_at: number; // unix seconds
  expires_in: number;
  role: Role;
  subject: string;
}

export interface ConsentState {
  student_ref: string;
  granted_scopes: ConsentScope[];
  policy_version: string;
  current_policy_version: string;
  policy_current: boolean;
  permits_sign_in: boolean;
  granted_at: number;
  last_change_at: number;
}

export interface ConsentHistoryEntry {
  consent_id: string;
  action: "granted" | "withdrawn";
  scopes: ConsentScope[];
  policy_version: string;
  recorded_at: number;
  method: string;
}

export type ConsentStateWithHistory = ConsentState & { history: ConsentHistoryEntry[] };

export interface Learner {
  student_ref: string;
  display_name: string;
  grade_band: GradeBand;
  grade_level: number;
  locale: string;
  status: AccountStatus;
  created_at: number;
  consent: ConsentState;
  can_sign_in: boolean;
}

export interface Guardian {
  guardian_ref: string;
  email: string;
  display_name: string;
  family_code: string;
  locale: string;
  status: AccountStatus;
  created_at: number;
}

export interface GuardianProfile {
  guardian: Guardian;
  learners: Learner[];
  policy_version: string;
}

export interface RosterEntry {
  display_name: string;
  grade_level: number;
}

export interface PolicyScope {
  key: ConsentScope;
  required: boolean;
}

export interface PolicyDescriptor {
  policy_version: string;
  scopes: PolicyScope[];
}

export interface AuditEvent {
  event_id: string;
  at: number;
  action: string;
  actor_ref: string;
  actor_role: string;
  subject_ref: string;
  correlation_id: string;
  detail: Record<string, unknown>;
}

/** What every sign-in and refresh response carries. */
export interface SessionEnvelope {
  session: AccessToken;
  refresh_token: string;
  learner?: Learner;
  guardian?: Guardian;
  consent?: ConsentState;
}
