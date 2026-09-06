// Student-portal configuration.
//
// This file used to hold a governance-safe development stub: a synthetic learner and a bearer token
// an operator minted by hand. Both are gone. A learner now signs in through /v1/identity with their
// family code, their own name, and a PIN, and every screen reads the signed-in learner from the
// session store rather than from a constant compiled into the bundle.

export { API_BASE } from "../session/config";
export type { GradeBand, Learner } from "../session/types";
