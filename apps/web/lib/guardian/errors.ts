// What a failed identity call says to a guardian (or a child at sign-in). Pure; unit-tested.
//
// Every 422 from the identity API is `code: VALIDATION_FAILED` with an English `detail`
// (services/core-api platform/errors.py). Showing that English sentence inside an Urdu screen is
// what the old pages did; instead the known details are matched to catalog keys here, and anything
// unrecognised falls back to a generic "please check" line in the guardian's own language. A stable
// per-error `code` from the server would make the matching unnecessary (see GUARDIAN_EXPERIENCE.md).

import type { MessageKey } from "../i18n/messages";
import { ApiError } from "../student/types";

export type IdentityAction =
  | "register"
  | "guardian-sign-in"
  | "roster"
  | "learner-sign-in"
  | "enrol"
  | "pin-reset"
  | "consent"
  | "load";

const VALIDATION_DETAILS: Array<[RegExp, MessageKey]> = [
  [/already exists in your family/i, "auth.errors.duplicateName"],
  [/at most \d+ learners/i, "auth.errors.familyFull"],
  [/too easily guessed/i, "auth.errors.pinTooEasy"],
  [/PIN must be/i, "auth.errors.pinFormat"],
  [/passphrase must be at least/i, "auth.errors.passphraseShort"],
  [/passphrase must be at most/i, "auth.errors.passphraseLong"],
  [/whitespace/i, "auth.errors.passphraseSpaces"],
  [/email/i, "auth.errors.emailInvalid"],
  [/display.?name|name must/i, "auth.errors.nameInvalid"],
  [/consent must include/i, "auth.errors.consentRequiredScope"],
];

function validationKey(detail: string | undefined): MessageKey {
  if (detail) {
    for (const [pattern, key] of VALIDATION_DETAILS) if (pattern.test(detail)) return key;
  }
  return "auth.errors.checkDetails";
}

/** The catalog key describing `error` for the given action. */
export function identityErrorKey(error: unknown, action: IdentityAction): MessageKey {
  if (!(error instanceof ApiError)) return "auth.errors.generic";
  if (error.status === 0) return "auth.errors.offline";
  if (error.status === 429) return "auth.errors.tooMany";

  switch (action) {
    case "register":
      if (error.status === 409) return "auth.errors.emailTaken";
      break;
    case "guardian-sign-in":
      // The server answers an unknown address and a wrong passphrase identically, and so does this
      // screen — saying which would confirm to a stranger that the address is registered.
      if (error.status === 401) return "auth.errors.guardianCredentials";
      break;
    case "learner-sign-in":
      if (error.problem.code === "CONSENT_REQUIRED") return "auth.errors.consentNeeded";
      if (error.status === 401) return "auth.errors.learnerCredentials";
      if (error.status === 503) return "auth.errors.paused";
      break;
    case "roster":
      if (error.status === 503) return "auth.errors.paused";
      break;
    case "enrol":
    case "pin-reset":
    case "consent":
    case "load":
      if (error.status === 401) return "auth.errors.signedOut";
      if (error.status === 404) return "auth.errors.learnerNotFound";
      if (error.status === 403) return "auth.errors.notGuardian";
      break;
  }
  if (error.status === 422) return validationKey(error.problem.detail);
  return "auth.errors.generic";
}
