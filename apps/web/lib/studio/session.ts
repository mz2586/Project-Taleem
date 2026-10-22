// Curriculum Studio staff session.
//
// There is no staff sign-in flow yet: identity issues tokens to learners and guardians only (an API
// gap, listed in the commit). Until one exists, a staff member signs in with an access token an
// operator issued to them. The token is typed in at run time and kept in sessionStorage for this
// tab only. Nothing is compiled into the bundle, so this is not a dev stub, and closing the tab
// forgets it.
//
// The claims are decoded here ONLY to drive the interface (which actions to show). The server
// verifies the signature and re-derives the role on every request; a forged token buys nothing but
// a page of 401s.

export const STUDIO_ROLES = [
  "subject_author",
  "subject_expert",
  "instructional_designer",
  "a11y_specialist",
  "language_editor",
  "safety_officer",
  "curriculum_architect",
] as const;
export type StudioRole = (typeof STUDIO_ROLES)[number];

export interface StudioActor {
  /** The token subject — the reviewer's identity as the server sees it. */
  subject: string;
  role: StudioRole;
  /** Unix seconds. */
  expiresAt: number | null;
}

export function isStudioRole(value: unknown): value is StudioRole {
  return typeof value === "string" && (STUDIO_ROLES as readonly string[]).includes(value);
}

function base64UrlDecode(segment: string): string {
  const b64 = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(segment.length / 4) * 4, "=");
  const binary = atob(b64);
  const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export type ActorParse =
  | { ok: true; actor: StudioActor }
  | { ok: false; reason: "malformed" | "not-studio-role" | "expired" };

/** Read `sub`/`role`/`exp` from a JWT for display. Never a security decision. */
export function parseStudioToken(token: string, nowSeconds: number): ActorParse {
  const parts = token.trim().split(".");
  if (parts.length !== 3 || !parts[1]) return { ok: false, reason: "malformed" };
  let claims: Record<string, unknown>;
  try {
    claims = JSON.parse(base64UrlDecode(parts[1])) as Record<string, unknown>;
  } catch {
    return { ok: false, reason: "malformed" };
  }
  if (typeof claims.sub !== "string" || !claims.sub) return { ok: false, reason: "malformed" };
  if (!isStudioRole(claims.role)) return { ok: false, reason: "not-studio-role" };
  const exp = typeof claims.exp === "number" ? claims.exp : null;
  if (exp !== null && exp <= nowSeconds) return { ok: false, reason: "expired" };
  return { ok: true, actor: { subject: claims.sub, role: claims.role, expiresAt: exp } };
}

const STORAGE_KEY = "taleem.studio.token.v1";
type Listener = (actor: StudioActor | null) => void;
const listeners = new Set<Listener>();
let memory: string | null = null;

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function notify(): void {
  const actor = studioSession.actor();
  for (const l of listeners) l(actor);
}

export const studioSession = {
  token(): string | null {
    if (memory) return memory;
    try {
      memory = storage()?.getItem(STORAGE_KEY) ?? null;
    } catch {
      memory = null;
    }
    return memory;
  },
  actor(now: number = Math.floor(Date.now() / 1000)): StudioActor | null {
    const token = studioSession.token();
    if (!token) return null;
    const parsed = parseStudioToken(token, now);
    return parsed.ok ? parsed.actor : null;
  },
  /** Adopt a token; returns why it was refused, or null on success. */
  signIn(token: string, now: number = Math.floor(Date.now() / 1000)): ActorParse {
    const parsed = parseStudioToken(token, now);
    if (!parsed.ok) return parsed;
    memory = token.trim();
    try {
      storage()?.setItem(STORAGE_KEY, memory);
    } catch {
      /* tab-lifetime only */
    }
    notify();
    return parsed;
  },
  clear(): void {
    memory = null;
    try {
      storage()?.removeItem(STORAGE_KEY);
    } catch {
      /* nothing stored */
    }
    notify();
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
