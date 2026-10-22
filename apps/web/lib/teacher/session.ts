// Teacher sign-in → the shared session store.
//
// The school API issues an access token and no refresh token (its sign-in response is
// `{teacher, session}`). Rather than fork the store, the response is adapted into the same
// envelope guardians and learners use, with an empty refresh token; the store treats a teacher
// session without one as "sign in again when the token expires" (lib/session/store.ts).

import type { SessionEnvelope } from "../session/types";
import type { TeacherSignInResponse } from "./types";

export function teacherEnvelope(response: TeacherSignInResponse): SessionEnvelope {
  return {
    session: { ...response.session, role: "teacher" },
    refresh_token: "",
  };
}
