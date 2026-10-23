// Safeguarding lead session for the /safeguarding console.
//
// A safeguarding lead is an operator-provisioned staff account (role `safeguarding_lead`) and signs
// in exactly like Studio staff (POST /v1/identity/staff:signin). The tokens live in sessionStorage
// for this tab only, under keys of their own: the Studio session never becomes a console session or
// the reverse. Claims are decoded only to drive the interface; the server re-checks every request.

import { createApiClient } from "../apiClient";
import { API_BASE } from "../session/config";

export const LEAD_ROLE = "safeguarding_lead";

export interface LeadActor {
  subject: string;
  expiresAt: number | null;
}

export type LeadParse =
  | { ok: true; actor: LeadActor }
  | { ok: false; reason: "malformed" | "not-lead" | "expired" };

function base64UrlDecode(segment: string): string {
  const b64 = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(segment.length / 4) * 4, "=");
  const binary = atob(b64);
  return new TextDecoder().decode(Uint8Array.from(binary, (c) => c.charCodeAt(0)));
}

/** Read `sub`/`role`/`exp` for display. Never a security decision. */
export function parseLeadToken(token: string, nowSeconds: number): LeadParse {
  const parts = token.trim().split(".");
  if (parts.length !== 3 || !parts[1]) return { ok: false, reason: "malformed" };
  let claims: Record<string, unknown>;
  try {
    claims = JSON.parse(base64UrlDecode(parts[1])) as Record<string, unknown>;
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (typeof claims.sub !== "string" || !claims.sub) return { ok: false, reason: "malformed" };
  if (claims.role !== LEAD_ROLE) return { ok: false, reason: "not-lead" };
  const exp = typeof claims.exp === "number" ? claims.exp : null;
  if (exp !== null && exp <= nowSeconds) return { ok: false, reason: "expired" };
  return { ok: true, actor: { subject: claims.sub, expiresAt: exp } };
}

const TOKEN_KEY = "taleem.safeguarding.token.v1";
const REFRESH_KEY = "taleem.safeguarding.refresh.v1";
type Listener = (actor: LeadActor | null) => void;
const listeners = new Set<Listener>();

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function read(key: string): string | null {
  try {
    return storage()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value) storage()?.setItem(key, value);
    else storage()?.removeItem(key);
  } catch {
    /* tab-lifetime only */
  }
}

export const leadSession = {
  token: (): string | null => read(TOKEN_KEY),
  actor(now: number = Math.floor(Date.now() / 1000)): LeadActor | null {
    const token = read(TOKEN_KEY);
    if (!token) return null;
    const parsed = parseLeadToken(token, now);
    return parsed.ok ? parsed.actor : null;
  },
  adopt(accessToken: string, refreshToken: string | null, now: number = Math.floor(Date.now() / 1000)): LeadParse {
    const parsed = parseLeadToken(accessToken, now);
    if (!parsed.ok) return parsed; // a Studio reviewer's account is refused here, not adopted
    write(TOKEN_KEY, accessToken.trim());
    write(REFRESH_KEY, refreshToken);
    for (const l of listeners) l(parsed.actor);
    return parsed;
  },
  refreshToken: (): string | null => read(REFRESH_KEY),
  clear(): void {
    write(TOKEN_KEY, null);
    write(REFRESH_KEY, null);
    for (const l of listeners) l(null);
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

interface StaffEnvelope {
  session: { access_token: string };
  refresh_token: string;
}

const anonymous = createApiClient(API_BASE, () => "");

/** Passphrase sign-in. Throws the API's ApiError on 401/429; `not-lead` for any other staff role. */
export async function signInLead(email: string, passphrase: string): Promise<LeadParse> {
  const envelope = await anonymous.post<StaffEnvelope>("/v1/identity/staff:signin", { email, passphrase });
  const parsed = leadSession.adopt(envelope.session.access_token, envelope.refresh_token);
  if (!parsed.ok) {
    // Another staff role: end the server session it just opened instead of leaving it live.
    await anonymous.post("/v1/identity/sessions:signout", { refreshToken: envelope.refresh_token }).catch(() => undefined);
  }
  return parsed;
}

/** Rotate the refresh token; false (and signed out) when the session is over. */
export async function refreshLead(): Promise<boolean> {
  const refreshToken = leadSession.refreshToken();
  if (!refreshToken) return false;
  try {
    const envelope = await anonymous.post<StaffEnvelope>("/v1/identity/sessions:refresh", { refreshToken });
    return leadSession.adopt(envelope.session.access_token, envelope.refresh_token).ok;
  } catch {
    leadSession.clear();
    return false;
  }
}

export async function signOutLead(): Promise<void> {
  const refreshToken = leadSession.refreshToken();
  try {
    if (refreshToken) await anonymous.post("/v1/identity/sessions:signout", { refreshToken });
  } catch {
    /* offline: the refresh token lapses on its own */
  } finally {
    leadSession.clear();
  }
}
