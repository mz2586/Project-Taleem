// The session store: one place that holds the current tokens, keeps them fresh, and hands the
// access token to every API client.
//
// Three things here are load-bearing and easy to get wrong:
//
// 1. **Refresh is single-flight.** Refresh tokens rotate and the server treats a replayed token as
//    theft, revoking the whole chain. Two components hitting 401 at the same moment would fire two
//    refreshes with the same token and log the family out. Every caller therefore awaits one shared
//    promise.
// 2. **The successor is persisted before it is used.** Rotation invalidates the old token the moment
//    the server responds, so if we returned first and stored later, a crash in between would strand
//    the user. Store, then resolve.
// 3. **Expiry is checked with a margin.** A token that expires in four seconds is treated as expired,
//    because a request in flight over a slow connection would land after it died.
//
// Tokens live in localStorage. On a shared family phone that is a real trade: anything with script
// access to this origin can read them. The alternative — httpOnly cookies — needs the API to set
// them, which would couple the browser client to a same-site deployment the offline-first design
// does not assume. The mitigations are the ones that matter for a child: a ten-minute access token,
// device-bound refresh, rotation with theft detection, and a sign-out that revokes server-side.

import { ApiError } from "../student/types";
import { deviceId } from "./device";
import { publicIdentityApi } from "./identityApi";
import type { Guardian, Learner, Role, SessionEnvelope } from "./types";

const STORAGE_KEY = "taleem.session.v1";

// Refresh this many seconds before the access token actually expires.
const EXPIRY_MARGIN_SECONDS = 30;

export interface StoredSession {
  role: Role;
  subject: string;
  accessToken: string;
  expiresAt: number;
  refreshToken: string;
  learner?: Learner;
  guardian?: Guardian;
}

type Listener = (session: StoredSession | null) => void;

let current: StoredSession | null = null;
let hydrated = false;
let inFlight: Promise<StoredSession | null> | null = null;
const listeners = new Set<Listener>();

function read(): StoredSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession;
    if (!parsed?.accessToken || !parsed?.refreshToken || !parsed?.role) return null;
    return parsed;
  } catch {
    // Unparseable or unavailable storage is the same as no session — never a crash on boot.
    return null;
  }
}

function write(session: StoredSession | null): void {
  current = session;
  if (typeof window !== "undefined") {
    try {
      if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable: the session still works for this page's lifetime */
    }
  }
  for (const listener of listeners) listener(session);
}

function fromEnvelope(envelope: SessionEnvelope): StoredSession {
  return {
    role: envelope.session.role,
    subject: envelope.session.subject,
    accessToken: envelope.session.access_token,
    expiresAt: envelope.session.expires_at,
    refreshToken: envelope.refresh_token,
    learner: envelope.learner,
    guardian: envelope.guardian,
  };
}

function isExpired(session: StoredSession, nowSeconds: number): boolean {
  return session.expiresAt - EXPIRY_MARGIN_SECONDS <= nowSeconds;
}

export const sessionStore = {
  /** The session as last known, without touching the network. */
  peek(): StoredSession | null {
    if (!hydrated) {
      current = read();
      hydrated = true;
    }
    return current;
  },

  /** Replace the session from a sign-in or refresh response. */
  adopt(envelope: SessionEnvelope): StoredSession {
    const session = fromEnvelope(envelope);
    hydrated = true;
    write(session);
    return session;
  },

  /** Forget the session locally. Does not call the server — see `signOut`. */
  clear(): void {
    hydrated = true;
    write(null);
  },

  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },

  /**
   * The current access token, refreshed if it is at or near expiry.
   *
   * Returns null when there is no usable session, which is the caller's cue to send the person to
   * a sign-in screen rather than to retry.
   */
  async valid(): Promise<StoredSession | null> {
    const session = sessionStore.peek();
    if (!session) return null;
    const now = Math.floor(Date.now() / 1000);
    if (!isExpired(session, now)) return session;
    return sessionStore.refresh();
  },

  /** Force a refresh. Concurrent callers share one request — see note 1 above. */
  async refresh(): Promise<StoredSession | null> {
    if (inFlight) return inFlight;
    const session = sessionStore.peek();
    if (!session) return null;

    inFlight = (async () => {
      try {
        const envelope = await publicIdentityApi.refresh({
          refreshToken: session.refreshToken,
          deviceId: deviceId(),
        });
        return sessionStore.adopt(envelope);
      } catch (error) {
        if (error instanceof ApiError && error.status === 0) {
          // Offline. Keep the session: the network will come back, and discarding a valid refresh
          // token because a tunnel was long would sign a child out for no reason.
          return session;
        }
        // Anything else — revoked, expired, consent withdrawn, theft detected — is terminal.
        sessionStore.clear();
        return null;
      } finally {
        inFlight = null;
      }
    })();

    return inFlight;
  },

  /** End the session on the server as well as here. Safe to call when already signed out. */
  async signOut(): Promise<void> {
    const session = sessionStore.peek();
    sessionStore.clear();
    if (!session) return;
    try {
      await publicIdentityApi.signOut(session.refreshToken);
    } catch {
      // Best effort: the local session is already gone, and the token expires on its own.
    }
  },
};

/**
 * The synchronous token provider the existing API clients expect.
 *
 * Synchronous by necessity — `createApiClient` reads it inline — so it returns whatever is stored
 * without refreshing. Freshness is the job of `withSession`, which callers use to wrap a request.
 */
export function currentAccessToken(): string {
  return sessionStore.peek()?.accessToken ?? "";
}

/**
 * Run an API call with a guaranteed-fresh token, retrying once if the server rejects it anyway.
 *
 * The retry exists because expiry is not the only reason for a 401: a key rotation, a clock skew,
 * or a revocation between the check and the call all look the same from here. One retry after a
 * forced refresh distinguishes "stale token" from "no longer permitted" without looping.
 */
export async function withSession<T>(call: () => Promise<T>): Promise<T> {
  await sessionStore.valid();
  try {
    return await call();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    const refreshed = await sessionStore.refresh();
    if (!refreshed) throw error;
    return call();
  }
}
