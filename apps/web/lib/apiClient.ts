// Shared HTTP client factory — bearer auth + RFC 9457 problem+json, with a status-0 ApiError on
// network failure (so callers render the offline UX). Reused across portals so the request/error
// handling lives in exactly one place.

import { ApiError } from "./student/types";

export type TokenProvider = () => string;

export interface ApiClient {
  get<T>(path: string): Promise<T>;
  post<T>(path: string, body?: unknown): Promise<T>;
}

export function createApiClient(base: string, getToken: TokenProvider): ApiClient {
  async function req<T>(path: string, init?: RequestInit): Promise<T> {
    const token = getToken();
    let res: Response;
    try {
      res = await fetch(`${base}${path}`, {
        ...init,
        headers: {
          "content-type": "application/json",
          ...(token ? { authorization: `Bearer ${token}` } : {}),
          ...(init?.headers ?? {}),
        },
      });
    } catch {
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

  return {
    get: <T>(path: string) => req<T>(path),
    post: <T>(path: string, body?: unknown) =>
      req<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  };
}
