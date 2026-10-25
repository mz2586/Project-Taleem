// The ONE client for the path, unit checks and the academic record
// (PROGRESSION_AND_EXAMINATION_CONTRACT.md). Every path and body for this feature is spelled here
// and nowhere else, so following a server change is a one-file edit.
//
// Learner calls carry the learner token, guardian calls the guardian token — whatever the session
// store holds. The server decides which learner each may read. Unit checks are online only (§2):
// assembly and scoring happen on the server, and no answer key ever reaches the device.

import { createApiClient } from "../apiClient";
import { API_BASE } from "../session/config";
import { currentAccessToken, withSession } from "../session/store";
import type { AnswerBody } from "../student/itemAnswer";
import type { AnswerResultWire, FinishWire, PathWire, RecordWire, SittingWire } from "./types";

const client = createApiClient(API_BASE, () => currentAccessToken());
const seg = encodeURIComponent;

const learner = (studentRef: string) => `/v1/learning/students/${seg(studentRef)}`;

export const PROGRESSION_PATHS = {
  path: (studentRef: string) => `${learner(studentRef)}/path`,
  startCheck: (studentRef: string, unitKey: string) => `${learner(studentRef)}/units/${seg(unitKey)}/checks`,
  /** Resume (§2: a sitting is resumable for 24 hours). */
  sitting: (studentRef: string, unitKey: string, sittingId: string) =>
    `${learner(studentRef)}/units/${seg(unitKey)}/checks/${seg(sittingId)}`,
  answer: (studentRef: string, unitKey: string, sittingId: string) =>
    `${learner(studentRef)}/units/${seg(unitKey)}/checks/${seg(sittingId)}:answer`,
  finish: (studentRef: string, unitKey: string, sittingId: string) =>
    `${learner(studentRef)}/units/${seg(unitKey)}/checks/${seg(sittingId)}:finish`,
  learnerRecord: (studentRef: string) => `${learner(studentRef)}/record`,
  guardianRecord: (studentRef: string) => `/v1/guardian/children/${seg(studentRef)}/record`,
} as const;

/** The `:answer` body: the item plus exactly one ITEM_INTERACTION_CONTRACT answer field. */
export type CheckAnswerBody = { item_ref: string } & AnswerBody;

export function checkAnswerBody(itemRef: string, answer: AnswerBody): CheckAnswerBody {
  return { item_ref: itemRef, ...answer };
}

export const pathApi = {
  path: (studentRef: string) => withSession(() => client.get<PathWire>(PROGRESSION_PATHS.path(studentRef))),
};

export const unitCheckApi = {
  start: (studentRef: string, unitKey: string) =>
    withSession(() => client.post<SittingWire>(PROGRESSION_PATHS.startCheck(studentRef, unitKey))),
  sitting: (studentRef: string, unitKey: string, sittingId: string) =>
    withSession(() => client.get<SittingWire>(PROGRESSION_PATHS.sitting(studentRef, unitKey, sittingId))),
  answer: (studentRef: string, unitKey: string, sittingId: string, body: CheckAnswerBody) =>
    withSession(() => client.post<AnswerResultWire>(PROGRESSION_PATHS.answer(studentRef, unitKey, sittingId), body)),
  finish: (studentRef: string, unitKey: string, sittingId: string) =>
    withSession(() => client.post<FinishWire>(PROGRESSION_PATHS.finish(studentRef, unitKey, sittingId))),
};

export const recordApi = {
  learner: (studentRef: string) => withSession(() => client.get<RecordWire>(PROGRESSION_PATHS.learnerRecord(studentRef))),
  guardian: (studentRef: string) => withSession(() => client.get<RecordWire>(PROGRESSION_PATHS.guardianRecord(studentRef))),
};
