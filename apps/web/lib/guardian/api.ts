// Typed clients for everything the guardian portal calls.
//
// - `guardianApi` — the Guardian Portal API (/v1/guardian/*): read-only learning aggregates. No
//   aggregation here; the server already aggregates from the learning read models.
// - `familyApi` — the guardian's half of the identity API (/v1/identity/*), from the shared session
//   client, plus the audit trail with its `limit` parameter.
//
// Every call runs through `withSession`, so a guardian who leaves the tab open past the access
// token's lifetime gets a refreshed token instead of a spurious "offline" or "signed out".

import { createApiClient, type TokenProvider } from "../apiClient";
import { clearHomeworkDrafts } from "../homework/drafts";
// Side effect: a withdrawal's draft wipe also removes that child's queued offline homework.
import "../student/offlineClient";
import { createGuardianIdentityApi, publicIdentityApi } from "../session/identityApi";
import { currentAccessToken, withSession } from "../session/store";
import type { AuditEvent } from "../session/types";
import type { ChildClass, JoinClassResult } from "../teacher/types";
import { API_BASE } from "./config";
import type { ChildOverview, GuardianDashboard, GuardianProfile } from "./types";

let tokenProvider: TokenProvider = currentAccessToken;

export function setGuardianTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

const client = createApiClient(API_BASE, () => tokenProvider());
const identity = createGuardianIdentityApi(() => tokenProvider());

export const guardianApi = {
  me: () => withSession(() => client.get<GuardianProfile>("/v1/guardian/me")),
  dashboard: () => withSession(() => client.get<GuardianDashboard>("/v1/guardian/dashboard")),
  child: (studentRef: string) =>
    withSession(() =>
      client.get<ChildOverview>(`/v1/guardian/children/${encodeURIComponent(studentRef)}`),
    ),
};

type IdentityApi = ReturnType<typeof createGuardianIdentityApi>;

export const familyApi = {
  me: () => withSession(() => identity.me()),
  listLearners: () => withSession(() => identity.listLearners()),
  enrolLearner: (body: Parameters<IdentityApi["enrolLearner"]>[0]) =>
    withSession(() => identity.enrolLearner(body)),
  resetPin: (studentRef: string, pin: string) => withSession(() => identity.resetPin(studentRef, pin)),
  consent: (studentRef: string) => withSession(() => identity.consent(studentRef)),
  grantConsent: (body: Parameters<IdentityApi["grantConsent"]>[0]) =>
    withSession(() => identity.grantConsent(body)),
  /**
   * Any withdrawal also removes that child's kept homework drafts from this phone (a shared family
   * device): the child's text must not outlive the permission it was written under.
   */
  withdrawConsent: async (body: Parameters<IdentityApi["withdrawConsent"]>[0]) => {
    const state = await withSession(() => identity.withdrawConsent(body));
    clearHomeworkDrafts(body.studentRef);
    return state;
  },
  audit: (limit: number) =>
    withSession(() => client.get<{ events: AuditEvent[] }>(`/v1/identity/audit?limit=${encodeURIComponent(limit)}`)),
  /**
   * Join the guardian's own child to a teacher's class with its code (POST /v1/school/classes:join).
   * The server records the `progress_sharing` consent with `attestation` stored verbatim.
   */
  joinClass: (body: { classCode: string; studentRef: string; attestation: string }) =>
    withSession(() => client.post<JoinClassResult>("/v1/school/classes:join", body)),
  /** The classes this guardian's child has joined (another family's child is a 404). */
  childClasses: (studentRef: string) =>
    withSession(() =>
      client.get<{ classes: ChildClass[] }>(`/v1/school/children/${encodeURIComponent(studentRef)}/classes`),
    ),
  /** Leave one class; that teacher stops seeing the child at once. progress_sharing is untouched. */
  leaveClass: (studentRef: string, classId: string) =>
    withSession(() =>
      client.post<{ class_id: string; left: boolean }>(
        `/v1/school/children/${encodeURIComponent(studentRef)}/classes/${encodeURIComponent(classId)}:leave`,
      ),
    ),
  /** Public; the consent form is rendered from it. */
  policy: () => publicIdentityApi.policy(),
};
