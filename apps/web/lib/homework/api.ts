// The ONE client for homework and marking (HOMEWORK_AND_MARKING_CONTRACT.md). Every path and body
// for this feature is spelled here and nowhere else, so following a server change is a one-file edit.
//
// Learner calls carry the learner token; teacher calls the teacher token — both are whatever the
// session store holds, and the server decides which class, learner and submission each may touch.

import { createApiClient } from "../apiClient";
import { API_BASE } from "../session/config";
import { currentAccessToken, withSession } from "../session/store";
import type { ConcernBody } from "./teacher";
import type {
  LearnerHomeworkWire,
  LearnerSubmissionWire,
  MarkBody,
  QueueStatus,
  ReturnBody,
  SubmissionQueueWire,
  SubmitBody,
} from "./types";

const client = createApiClient(API_BASE, () => currentAccessToken());
const seg = encodeURIComponent;

export const HOMEWORK_PATHS = {
  learnerHomework: (studentRef: string) => `/v1/school/learners/${seg(studentRef)}/homework`,
  submit: (studentRef: string, assignmentId: string, itemRef: string) =>
    `/v1/school/learners/${seg(studentRef)}/homework/${seg(assignmentId)}/items/${seg(itemRef)}:submit`,
  // §6: practice from the learner's own lessons has no assignment; it is addressed by objective.
  submitSelfPaced: (studentRef: string, objectiveCode: string, itemRef: string) =>
    `/v1/school/learners/${seg(studentRef)}/homework/self-paced/${seg(objectiveCode)}/items/${seg(itemRef)}:submit`,
  queue: (classId: string, status: QueueStatus) =>
    `/v1/school/classes/${seg(classId)}/submissions?status=${seg(status)}`,
  mark: (submissionId: string) => `/v1/school/submissions/${seg(submissionId)}:mark`,
  return: (submissionId: string) => `/v1/school/submissions/${seg(submissionId)}:return`,
  // §4 names the effect (a teacher-sourced concern about that learner, referencing the submission)
  // but not the route. A school route is the one that can check "a learner in your own class".
  concern: (submissionId: string) => `/v1/school/submissions/${seg(submissionId)}:concern`,
} as const;

/** Where an item is sent: an assignment (§2) or the learner's own lesson practice (§6). */
export type SubmitTarget =
  | { source: "assignment"; assignmentId: string }
  | { source: "self_paced"; objectiveCode: string };

export function submitPath(studentRef: string, target: SubmitTarget, itemRef: string): string {
  return target.source === "self_paced"
    ? HOMEWORK_PATHS.submitSelfPaced(studentRef, target.objectiveCode, itemRef)
    : HOMEWORK_PATHS.submit(studentRef, target.assignmentId, itemRef);
}

/** Learner side (§2). Online only: the page never calls `submit` while offline. */
export const homeworkApi = {
  list: (studentRef: string) => withSession(() => client.get<LearnerHomeworkWire>(HOMEWORK_PATHS.learnerHomework(studentRef))),
  submit: (studentRef: string, target: SubmitTarget, itemRef: string, body: SubmitBody) =>
    withSession(() =>
      client.post<LearnerSubmissionWire | undefined>(submitPath(studentRef, target, itemRef), body),
    ),
};

/** Teacher side (§3, §4). */
export const markingApi = {
  queue: (classId: string, status: QueueStatus) =>
    withSession(() => client.get<SubmissionQueueWire>(HOMEWORK_PATHS.queue(classId, status))),
  mark: (submissionId: string, body: MarkBody) => withSession(() => client.post<unknown>(HOMEWORK_PATHS.mark(submissionId), body)),
  return: (submissionId: string, body: ReturnBody) =>
    withSession(() => client.post<unknown>(HOMEWORK_PATHS.return(submissionId), body)),
  raiseConcern: (submissionId: string, body: ConcernBody) =>
    withSession(() => client.post<unknown>(HOMEWORK_PATHS.concern(submissionId), body)),
};
