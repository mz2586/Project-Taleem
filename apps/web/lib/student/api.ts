// Typed client for the Learning Intelligence API (/v1/learning/*).
// Bearer auth, RFC 9457 problem+json errors. Presentation layer only — no AI content is ever
// constructed here; the client only relays approved server responses.

import { API_BASE } from "./config";
import type {
  AnswerView,
  ApiError as ApiErrorType,
  DecisionView,
  HintView,
  KnowledgeView,
  ProgressView,
  SessionEndView,
  SessionView,
  TeachView,
  TodayView,
} from "./types";
import { ApiError } from "./types";
import type { AdaptivePlanWire, CapabilitiesWire, ExplainStyle, ExplanationWire } from "./aiTeacher";
import type { PlacementWire } from "./placement";
import { currentAccessToken, withSession } from "../session/store";
import type {
  BatchResult,
  OfflinePackage,
  PackageManifest,
  SigningKey,
  SyncDelta,
} from "../offline/types";

// The access token comes from the session store, which keeps it fresh. The indirection remains so
// tests can supply a fixed token without a browser.
export type TokenProvider = () => string;

let tokenProvider: TokenProvider = currentAccessToken;

export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = tokenProvider();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    // Network failure (offline) — surfaced as a status-0 ApiError so callers show the offline UX.
    throw new ApiError(0, { code: "OFFLINE", detail: "network unavailable" });
  }
  if (!res.ok) {
    let problem = { code: res.statusText, status: res.status };
    try {
      problem = { ...(await res.json()), status: res.status };
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, problem);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const post = <T>(path: string, body?: unknown): Promise<T> =>
  req<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

// Learner calls run inside `withSession`: the access token lives ten minutes, and without a refresh
// a child who paused mid-lesson came back to every call failing 401 — which the screens then showed
// as "offline". A refresh that fails terminally clears the session, and the route guard sends the
// child to sign-in.
const authed = <T>(call: () => Promise<T>): Promise<T> => withSession(call);

export const learningApi = {
  startSession: (studentRef: string) =>
    authed(() => post<SessionView>("/v1/learning/sessions", { student_ref: studentRef })),

  next: (sessionId: string) =>
    authed(() => post<DecisionView>(`/v1/learning/sessions/${sessionId}:next`)),

  teach: (sessionId: string, objectiveCode: string) =>
    authed(() =>
      post<TeachView>(`/v1/learning/sessions/${sessionId}:teach`, {
        objective_code: objectiveCode,
      }),
    ),

  answer: (
    sessionId: string,
    body: {
      objective_code: string;
      item_ref: string;
      option: number;
      hints_used?: number;
      self_confidence?: number | null;
    },
  ) => authed(() => post<AnswerView>(`/v1/learning/sessions/${sessionId}:answer`, body)),

  // The next AUTHORED hint on the item's graduated ladder (never the answer).
  hint: (sessionId: string, body: { objective_code: string; item_ref: string; hint_level: number }) =>
    authed(() => post<HintView>(`/v1/learning/sessions/${sessionId}:hint`, body)),

  end: (sessionId: string) =>
    authed(() => post<SessionEndView>(`/v1/learning/sessions/${sessionId}:end`)),

  // 404 for a learner with no recorded knowledge yet (a brand-new learner) — see journey.ts.
  knowledge: (studentRef: string) =>
    authed(() => req<KnowledgeView>(`/v1/learning/students/${studentRef}/knowledge`)),

  progress: (studentRef: string) =>
    authed(() => req<ProgressView>(`/v1/learning/students/${studentRef}/progress`)),

  // Dashboard aggregate: next action (or "complete") + mastery summary + due reviews.
  today: (studentRef: string) =>
    authed(() => req<TodayView>(`/v1/learning/students/${studentRef}/today`)),

  // Diagnostic placement ("Find your starting point") — see lib/student/placement.ts.
  placement: (studentRef: string) =>
    authed(() => req<PlacementWire>(`/v1/learning/students/${studentRef}/placement`)),

  placementAnswer: (studentRef: string, body: { item_ref: string; option: number; response_time_ms?: number }) =>
    authed(() => post<PlacementWire>(`/v1/learning/students/${studentRef}/placement:answer`, body)),
};

// AI Teacher (packages/contracts/ai-teacher.openapi.yaml). Templated, curriculum-grounded; any
// generated rephrase arrives separately in `generation` and is labelled by lib/student/aiTeacher.ts.
export const aiTeacherApi = {
  explain: (
    sessionId: string,
    body: { objective_code: string; style?: ExplainStyle | null; grade_band?: string; locale?: string },
  ) => authed(() => post<ExplanationWire>(`/v1/learning/sessions/${sessionId}:explain`, body)),

  plan: (studentRef: string) =>
    authed(() => req<AdaptivePlanWire>(`/v1/learning/students/${studentRef}/ai-teacher/plan`)),

  capabilities: (studentRef: string) =>
    authed(() => req<CapabilitiesWire>(`/v1/learning/students/${studentRef}/ai-teacher/capabilities`)),
};

// Offline lesson packages (Phase 6.2A). Content is C0 curriculum (no child data). The download
// manager uses `fetchPackage` to install a lesson for offline rendering.
export const offlineApi = {
  listPackages: () => req<{ packages: PackageManifest[] }>("/v1/offline/packages"),
  fetchPackage: (lessonId: string) => req<OfflinePackage>(`/v1/offline/packages/${lessonId}`),
  // Public Ed25519 signing keys (6.2C-1) a client may pin to verify package signatures.
  signingKeys: () => req<{ keys: SigningKey[] }>("/v1/offline/signing-keys"),
};

// Offline sync (Phase 6.2B). Drains the durable queue to the server; attempts are graded + recorded
// as durable evidence server-side (idempotent by client evidence_id).
export const syncApi = {
  batch: (cursor: number, deltas: SyncDelta[]) =>
    post<BatchResult>("/v1/sync/batch", { cursor, deltas }),
};

export type { ApiErrorType };
