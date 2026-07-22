// Typed client for the Learning Intelligence API (/v1/learning/*).
// Bearer auth, RFC 9457 problem+json errors. Presentation layer only — no AI content is ever
// constructed here; the client only relays approved server responses.

import { API_BASE, DEV_STUDENT_TOKEN } from "./config";
import type {
  AnswerView,
  ApiError as ApiErrorType,
  DecisionView,
  KnowledgeView,
  ProgressView,
  SessionEndView,
  SessionView,
  TeachView,
} from "./types";
import { ApiError } from "./types";
import type { BatchResult, OfflinePackage, PackageManifest, SyncDelta } from "../offline/types";

// A token provider so the auth source can be swapped (dev stub now; gated child-safe auth later).
export type TokenProvider = () => string;

let tokenProvider: TokenProvider = () => DEV_STUDENT_TOKEN;

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

export const learningApi = {
  startSession: (studentRef: string) =>
    post<SessionView>("/v1/learning/sessions", { student_ref: studentRef }),

  next: (sessionId: string) =>
    post<DecisionView>(`/v1/learning/sessions/${sessionId}:next`),

  teach: (sessionId: string, objectiveCode: string) =>
    post<TeachView>(`/v1/learning/sessions/${sessionId}:teach`, {
      objective_code: objectiveCode,
    }),

  answer: (
    sessionId: string,
    body: {
      objective_code: string;
      item_ref: string;
      option: number;
      hints_used?: number;
      self_confidence?: number | null;
    },
  ) => post<AnswerView>(`/v1/learning/sessions/${sessionId}:answer`, body),

  end: (sessionId: string) =>
    post<SessionEndView>(`/v1/learning/sessions/${sessionId}:end`),

  knowledge: (studentRef: string) =>
    req<KnowledgeView>(`/v1/learning/students/${studentRef}/knowledge`),

  progress: (studentRef: string) =>
    req<ProgressView>(`/v1/learning/students/${studentRef}/progress`),
};

// Offline lesson packages (Phase 6.2A). Content is C0 curriculum (no child data). The download
// manager uses `fetchPackage` to install a lesson for offline rendering.
export const offlineApi = {
  listPackages: () => req<{ packages: PackageManifest[] }>("/v1/offline/packages"),
  fetchPackage: (lessonId: string) => req<OfflinePackage>(`/v1/offline/packages/${lessonId}`),
};

// Offline sync (Phase 6.2B). Drains the durable queue to the server; attempts are graded + recorded
// as durable evidence server-side (idempotent by client evidence_id).
export const syncApi = {
  batch: (cursor: number, deltas: SyncDelta[]) =>
    post<BatchResult>("/v1/sync/batch", { cursor, deltas }),
};

export type { ApiErrorType };
