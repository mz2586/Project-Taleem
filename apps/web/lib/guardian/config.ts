// Guardian Portal configuration + the GOVERNANCE-SAFE dev auth stub.
//
// Like the student portal, production guardian auth (identity, consent-linked children) is gated by
// M-Gov; for local/dev the portal uses a synthetic guardian and a dev bearer token (role: guardian)
// supplied via env. No real guardian identity, no PII. Never ships to a real guardian.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const DEV_GUARDIAN_REF = process.env.NEXT_PUBLIC_DEV_GUARDIAN_REF ?? "dev-guardian-001";

// Dev-only bearer token (role: guardian, sub == DEV_GUARDIAN_REF). Supplied via env in dev.
export const DEV_GUARDIAN_TOKEN = process.env.NEXT_PUBLIC_DEV_GUARDIAN_TOKEN ?? "";

export const DEV_GUARDIAN_NAME = process.env.NEXT_PUBLIC_DEV_GUARDIAN_NAME ?? "سرپرست";
