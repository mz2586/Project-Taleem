// Curriculum Studio staff sign-in against the identity API.
//
// The integration point for the Studio pages: call `signInStaff` from a sign-in form, then read the
// actor from `studioSession` / `useStudioActor` exactly as before. `refreshStaffSession` exchanges
// the rotating refresh token for a fresh access token (call it on a 401 before giving up), and
// `signOutStaff` ends the server session as well as the tab's copy.
//
// The server decides the role and the subject (the account's one Studio role and its stable
// `staff_ref`); nothing here can choose either.

import { createApiClient } from "../apiClient";
import { API_BASE } from "../session/config";
import { studioSession, type ActorParse } from "./session";

export interface StaffAccount {
  staff_ref: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  created_at: number;
}

export interface StaffSessionEnvelope {
  staff: StaffAccount;
  session: { access_token: string; role: string; subject: string; expires_at: number };
  refresh_token: string;
}

const anonymous = createApiClient(API_BASE, () => "");

/** Adopt a sign-in or refresh envelope into the tab's studio session. */
export function adoptStaffEnvelope(envelope: StaffSessionEnvelope): ActorParse {
  const parsed = studioSession.signIn(envelope.session.access_token);
  studioSession.setRefreshToken(parsed.ok ? envelope.refresh_token : null);
  return parsed;
}

/** Passphrase sign-in. Throws the API's `ApiError` (401 uniform failure, 429 rate limited). */
export async function signInStaff(email: string, passphrase: string): Promise<ActorParse> {
  const envelope = await anonymous.post<StaffSessionEnvelope>("/v1/identity/staff:signin", {
    email,
    passphrase,
  });
  return adoptStaffEnvelope(envelope);
}

/** Rotate the refresh token. Returns false (and signs the tab out) when the session is over. */
export async function refreshStaffSession(): Promise<boolean> {
  const refreshToken = studioSession.refreshToken();
  if (!refreshToken) return false;
  try {
    const envelope = await anonymous.post<StaffSessionEnvelope>("/v1/identity/sessions:refresh", {
      refreshToken,
    });
    return adoptStaffEnvelope(envelope).ok;
  } catch {
    studioSession.clear();
    return false;
  }
}

/** End the server-side session family, then forget the tab's tokens. Never throws. */
export async function signOutStaff(): Promise<void> {
  const refreshToken = studioSession.refreshToken();
  try {
    if (refreshToken) {
      await anonymous.post("/v1/identity/sessions:signout", { refreshToken });
    }
  } catch {
    /* offline: the refresh token lapses on its own; the tab still forgets it */
  } finally {
    studioSession.clear();
  }
}
