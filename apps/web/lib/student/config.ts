// Student-portal configuration + the GOVERNANCE-SAFE dev auth stub.
//
// Child-safe production authentication (device-linked identity, guardian provisioning) is BLOCKED by
// the Phase-1.5 governance gate. For local development the portal uses a synthetic, pseudonymous
// learner and a dev bearer token supplied out-of-band (an operator mints it against the API's dev
// secret). There is NO real child identity, no PII, and this must never ship to a real child.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// A synthetic, pseudonymous learner for development. Never a real child.
export const SYNTHETIC_STUDENT_REF =
  process.env.NEXT_PUBLIC_DEV_STUDENT_REF ?? "dev-learner-001";

// Dev-only bearer token (role: student, sub == SYNTHETIC_STUDENT_REF). Supplied via env in dev.
// Production replaces this entire path with the governance-approved child-safe auth flow.
export const DEV_STUDENT_TOKEN = process.env.NEXT_PUBLIC_DEV_STUDENT_TOKEN ?? "";

export type GradeBand = "early" | "middle" | "senior";

export interface Learner {
  student_ref: string;
  display_name: string;
  grade_band: GradeBand;
  locale: "ur" | "en";
}

// The current dev learner (a stand-in for the gated sign-in flow).
export const DEV_LEARNER: Learner = {
  student_ref: SYNTHETIC_STUDENT_REF,
  display_name: process.env.NEXT_PUBLIC_DEV_LEARNER_NAME ?? "طالبِ علم",
  grade_band: (process.env.NEXT_PUBLIC_DEV_GRADE_BAND as GradeBand) ?? "middle",
  locale: "ur",
};
