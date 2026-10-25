// Typed clients for /v1/safeguarding (packages/contracts/safeguarding.openapi.yaml).
//
// - `childConcernApi` — a signed-in learner raises a concern about themselves. It never sends a
//   learner ref: the server takes the learner from the token.
// - `guardianConcernApi` — a guardian raises about one of their learners and lists what they raised.
// - `leadApi` — the safeguarding console (safeguarding_lead token from ./session).

import { createApiClient } from "../apiClient";
import { currentAccessToken, withSession } from "../session/store";
import { API_BASE } from "../session/config";
import { ApiError } from "../student/types";
import type { Category } from "./categories";
import type { RaisePayload } from "./childFlow";
import { leadSession, refreshLead } from "./session";
import type { ConcernContextWire, ConcernDetailWire, GuardianConcernWire, Outcome, QueueWire } from "./triage";

const learnerOrGuardian = createApiClient(API_BASE, () => currentAccessToken());

export interface ChildReceipt {
  received: true;
  raised_at: number;
  notice: string;
}

export const childConcernApi = {
  raise: (payload: RaisePayload) =>
    withSession(() => learnerOrGuardian.post<ChildReceipt>("/v1/safeguarding/concerns", payload)),
};

export const guardianConcernApi = {
  raise: (body: { studentRef: string; category: Category; text?: string }) =>
    withSession(() =>
      learnerOrGuardian.post<GuardianConcernWire>("/v1/safeguarding/concerns", {
        ...body,
        context: { screen: "guardian/concerns" },
      }),
    ),
  mine: () =>
    withSession(() => learnerOrGuardian.get<{ concerns: GuardianConcernWire[] }>("/v1/safeguarding/my-concerns")),
};

const lead = createApiClient(API_BASE, () => leadSession.token() ?? "");

/** One retry after a refresh on 401 (the access token lives an hour); then the error surfaces. */
async function asLead<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401 && (await refreshLead())) return call();
    throw error;
  }
}

const concernPath = (id: string) => `/v1/safeguarding/concerns/${encodeURIComponent(id)}`;

export const leadApi = {
  queue: (includeResolved: boolean) =>
    asLead(() => lead.get<QueueWire>(`/v1/safeguarding/queue${includeResolved ? "?includeResolved=true" : ""}`)),
  detail: (id: string) => asLead(() => lead.get<ConcernDetailWire>(concernPath(id))),
  /** What the child wrote (on demand only: every call is an audited read). */
  context: (id: string) => asLead(() => lead.get<ConcernContextWire>(`${concernPath(id)}/context`)),
  acknowledge: (id: string) => asLead(() => lead.post<ConcernDetailWire>(`${concernPath(id)}:acknowledge`)),
  addNote: (id: string, body: string) =>
    asLead(() => lead.post<ConcernDetailWire>(`${concernPath(id)}/notes`, { body })),
  escalate: (id: string, reason: string) =>
    asLead(() => lead.post<ConcernDetailWire>(`${concernPath(id)}:escalate`, { reason })),
  resolve: (id: string, outcome: Outcome, note?: string) =>
    asLead(() => lead.post<ConcernDetailWire>(`${concernPath(id)}:resolve`, note ? { outcome, note } : { outcome })),
};
