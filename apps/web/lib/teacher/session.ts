// Teacher sign-in → the shared session store.
//
// The school sign-in returns `{teacher, session, refresh_token}`. The refresh token is one of
// identity's rotating, device-bound chains, so the shared store refreshes it at
// /v1/identity/sessions:refresh and ends it at sessions:signout exactly like a guardian's.

import type { SessionEnvelope } from "../session/types";
import type { TeacherSignInResponse } from "./types";

export function teacherEnvelope(response: TeacherSignInResponse): SessionEnvelope {
  return {
    session: { ...response.session, role: "teacher" },
    refresh_token: response.refresh_token,
  };
}
