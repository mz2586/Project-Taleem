// Typed client for the identity API (/v1/identity/*).
//
// Split into two halves on purpose. `publicIdentityApi` calls are how a caller *obtains* a token,
// so they carry none; `guardianIdentityApi` calls carry the guardian's access token, which the
// session store supplies. Nothing here decides who may do what — the server does, and this client
// never sends a ref it was not given by the server.

import { createApiClient, type TokenProvider } from "../apiClient";
import { API_BASE } from "./config";
import type {
  AuditEvent,
  ConsentScope,
  ConsentState,
  ConsentStateWithHistory,
  GuardianProfile,
  Learner,
  PolicyDescriptor,
  RosterEntry,
  SessionEnvelope,
} from "./types";

const anonymous = createApiClient(API_BASE, () => "");

export const publicIdentityApi = {
  registerGuardian: (body: {
    email: string;
    passphrase: string;
    displayName: string;
    locale?: string;
  }) => anonymous.post<SessionEnvelope>("/v1/identity/guardians", body),

  signInGuardian: (body: { email: string; passphrase: string }) =>
    anonymous.post<SessionEnvelope>("/v1/identity/guardians:signin", body),

  // POST, not GET: the family code is a shared secret and must not reach a URL, a proxy log, or a
  // browser history entry.
  roster: (familyCode: string) =>
    anonymous.post<{ learners: RosterEntry[] }>("/v1/identity/learners:roster", { familyCode }),

  signInLearner: (body: {
    familyCode: string;
    displayName: string;
    pin: string;
    deviceId?: string;
  }) => anonymous.post<SessionEnvelope>("/v1/identity/learners:signin", body),

  refresh: (body: { refreshToken: string; deviceId?: string }) =>
    anonymous.post<SessionEnvelope>("/v1/identity/sessions:refresh", body),

  signOut: (refreshToken: string) =>
    anonymous.post<{ signed_out: boolean }>("/v1/identity/sessions:signout", { refreshToken }),

  policy: () => anonymous.get<PolicyDescriptor>("/v1/identity/policy"),
};

export function createGuardianIdentityApi(getToken: TokenProvider) {
  const client = createApiClient(API_BASE, getToken);
  return {
    me: () => client.get<GuardianProfile>("/v1/identity/me"),

    listLearners: () => client.get<{ learners: Learner[] }>("/v1/identity/learners"),

    enrolLearner: (body: {
      displayName: string;
      pin: string;
      gradeBand?: string;
      gradeLevel?: number;
      locale?: string;
    }) => client.post<Learner>("/v1/identity/learners", body),

    resetPin: (studentRef: string, pin: string) =>
      client.post<Learner>(
        `/v1/identity/learners/${encodeURIComponent(studentRef)}/pin:reset`,
        { pin },
      ),

    consent: (studentRef: string) =>
      client.get<ConsentStateWithHistory>(
        `/v1/identity/consents/${encodeURIComponent(studentRef)}`,
      ),

    grantConsent: (body: {
      studentRef: string;
      scopes: ConsentScope[];
      attestation: string;
    }) => client.post<ConsentState>("/v1/identity/consents", body),

    withdrawConsent: (body: {
      studentRef: string;
      scopes?: ConsentScope[];
      attestation?: string;
    }) => client.post<ConsentState>("/v1/identity/consents:withdraw", body),

    audit: () => client.get<{ events: AuditEvent[] }>("/v1/identity/audit"),
  };
}

export type GuardianIdentityApi = ReturnType<typeof createGuardianIdentityApi>;
