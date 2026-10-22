// What a failed school-API call means on a teacher (or guardian join) screen. Pure; unit-tested.
//
// Access boundaries are the server's: a class, assignment or organization outside the teacher's
// scope is a 404, and a locked or suspended teacher gets 403 TEACHER_INACTIVE on the next request.
// The UI shows both honestly — and shows 404 and a non-inactive 403 the SAME way ("not
// available"), so the screen never confirms whether some other teacher's class exists.

import type { MessageKey } from "../i18n/messages";
import { ApiError } from "../student/types";

export type TeacherFailure = "offline" | "signed-out" | "inactive" | "not-available" | "error";

export function teacherFailure(error: unknown): TeacherFailure {
  if (!(error instanceof ApiError)) return "error";
  if (error.status === 0) return "offline";
  if (error.status === 401) return "signed-out";
  if (error.status === 403 && error.problem.code === "TEACHER_INACTIVE") return "inactive";
  if (error.status === 403 || error.status === 404) return "not-available";
  return "error";
}

/**
 * Sign-in failure copy. The server answers an unknown email, a wrong passphrase and a locked or
 * suspended account with one identical 401, and so does this screen — naming the reason would tell
 * a stranger that the address belongs to a teacher. The one message therefore also explains locking.
 */
export function signInErrorKey(error: unknown): MessageKey {
  if (!(error instanceof ApiError)) return "teacher.signIn.generic";
  if (error.status === 0) return "teacher.signIn.offline";
  if (error.status === 429) return "teacher.signIn.tooMany";
  // 422 is a malformed email/passphrase; answering it differently from 401 would leak nothing, but
  // one message for "these details did not work" is simpler for the person reading it.
  if (error.status === 401 || error.status === 422) return "teacher.signIn.failed";
  return "teacher.signIn.generic";
}

function commonKey(error: ApiError): MessageKey | null {
  switch (teacherFailure(error)) {
    case "offline":
      return "teacher.errors.offline";
    case "signed-out":
      return "teacher.errors.signedOut";
    case "inactive":
      return "teacher.errors.inactive";
    case "not-available":
      return "teacher.errors.notAvailable";
    default:
      if (error.status === 429) return "teacher.errors.tooMany";
      return null;
  }
}

export function createClassErrorKey(error: unknown): MessageKey {
  if (!(error instanceof ApiError)) return "teacher.errors.generic";
  if (error.status === 422) return "teacher.classes.nameInvalid";
  return commonKey(error) ?? "teacher.errors.generic";
}

export function createAssignmentErrorKey(error: unknown): MessageKey {
  if (!(error instanceof ApiError)) return "teacher.errors.generic";
  if (error.status === 422) {
    if (error.problem.code === "LESSON_NOT_PUBLISHED") return "teacher.assign.notPublished";
    if (/future/i.test(error.problem.detail ?? "")) return "teacher.assign.duePast";
    return "teacher.errors.checkDetails";
  }
  return commonKey(error) ?? "teacher.errors.generic";
}

/** Guardian side: POST /v1/school/classes:join. */
export function joinClassErrorKey(error: unknown): MessageKey {
  if (!(error instanceof ApiError)) return "teacher.guardianJoin.errors.generic";
  if (error.status === 0) return "teacher.guardianJoin.errors.offline";
  if (error.status === 429) return "teacher.guardianJoin.errors.tooMany";
  if (error.status === 401) return "teacher.guardianJoin.errors.signedOut";
  if (error.status === 403) return "teacher.guardianJoin.errors.notGuardian";
  // One answer for a mistyped code, an unknown class and a learner that is not this guardian's:
  // the server does not distinguish them, and neither does the screen.
  if (error.status === 404) return "teacher.guardianJoin.errors.notFound";
  if (error.status === 409 && error.problem.code === "CONSENT_REQUIRED")
    return "teacher.guardianJoin.errors.consentNeeded";
  if (error.status === 422) return "teacher.guardianJoin.errors.checkDetails";
  return "teacher.guardianJoin.errors.generic";
}
