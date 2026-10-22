// Guardian side of joining a class. Pure; unit-tested.
//
// Joining is the guardian's consent act: POST /v1/school/classes:join records the
// `progress_sharing` scope for that child, with the sentence the guardian affirmed stored verbatim.
// Withdrawing that scope in the consent form stops the sharing; the teacher stops seeing the child
// on the very next request.

import { childAccess } from "../guardian/dashboard";
import type { Learner } from "../session/types";

/** The server's class-code alphabet (no 0/O, 1/I/L): school/domain/model.py. */
export const CLASS_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";

/**
 * `abcd efgh` / `ABCD-EFGH` → `ABCD-EFGH`, or null if it cannot be a class code. Mirrors the
 * server's normalisation so an obviously mistyped code is caught before a rate-limited request.
 */
export function normaliseClassCode(raw: string): string | null {
  const code = raw.replace(/[\s-]/g, "").toUpperCase();
  if (code.length !== 8) return null;
  for (const c of code) if (!CLASS_CODE_ALPHABET.includes(c)) return null;
  return `${code.slice(0, 4)}-${code.slice(4)}`;
}

export type JoinAvailability = "ready" | "needs-learning-consent";

/**
 * The server refuses a join (409 CONSENT_REQUIRED) unless the child may learn — joining never
 * restores a withdrawn learning consent. Say so before the guardian types a code.
 */
export function joinAvailability(learner: Learner): JoinAvailability {
  return childAccess(learner) === "given" ? "ready" : "needs-learning-consent";
}

export function sharesProgress(learner: Learner): boolean {
  return learner.consent?.granted_scopes?.includes("progress_sharing") ?? false;
}
