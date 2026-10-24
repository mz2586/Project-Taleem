// The ONE client for report cards (REPORT_CARD_CONTRACT.md §2–§3). Every path and body for this
// feature is spelled here and nowhere else, so following a server change is a one-file edit.
//
// Teacher calls carry the teacher token, guardian calls the guardian token, learner calls the
// learner token — whatever the session store holds. The server decides who may see which card.

import { createApiClient } from "../apiClient";
import { API_BASE } from "../session/config";
import { currentAccessToken, withSession } from "../session/store";
import type {
  AcknowledgeWire,
  GenerateBody,
  IssueBody,
  IssueResultWire,
  NotificationListWire,
  PreviewBody,
  ReportCardListWire,
  ReportCardWire,
} from "./types";

const client = createApiClient(API_BASE, () => currentAccessToken());
const seg = encodeURIComponent;

export const REPORTING_PATHS = {
  preview: (classId: string) => `/v1/reporting/classes/${seg(classId)}/report-cards:preview`,
  issue: (classId: string) => `/v1/reporting/classes/${seg(classId)}/report-cards`,
  childCards: (studentRef: string) => `/v1/reporting/children/${seg(studentRef)}/report-cards`,
  generate: (studentRef: string) => `/v1/reporting/children/${seg(studentRef)}/report-cards:generate`,
  notifications: (studentRef: string) => `/v1/reporting/children/${seg(studentRef)}/notifications`,
  card: (cardId: string) => `/v1/reporting/report-cards/${seg(cardId)}`,
  acknowledge: (cardId: string) => `/v1/reporting/report-cards/${seg(cardId)}:acknowledge`,
  // §3: the learner's own cards. "Teacher: the same list for a learner in their class" names no
  // separate route, so the teacher reads the same one (the server scopes it to their class).
  learnerCards: (studentRef: string) => `/v1/reporting/learners/${seg(studentRef)}/report-cards`,
} as const;

/** Teacher (§2): preview without storing, then issue. */
export const reportIssueApi = {
  preview: (classId: string, body: PreviewBody) =>
    withSession(() => client.post<IssueResultWire>(REPORTING_PATHS.preview(classId), body)),
  issue: (classId: string, body: IssueBody) => withSession(() => client.post<IssueResultWire>(REPORTING_PATHS.issue(classId), body)),
  /** A learner's existing cards — the ones a correction can supersede. */
  learnerCards: (studentRef: string) => withSession(() => client.get<ReportCardListWire>(REPORTING_PATHS.learnerCards(studentRef))),
};

/** Guardian (§3): a child's cards, one card, "I have seen this", "get a report", and the feed. */
export const guardianReportApi = {
  list: (studentRef: string) => withSession(() => client.get<ReportCardListWire>(REPORTING_PATHS.childCards(studentRef))),
  /** Taleem issues the child's card for a closed period (201 with the card). */
  generate: (studentRef: string, body: GenerateBody) =>
    withSession(() => client.post<ReportCardWire>(REPORTING_PATHS.generate(studentRef), body)),
  notifications: (studentRef: string) =>
    withSession(() => client.get<NotificationListWire>(REPORTING_PATHS.notifications(studentRef))),
  card: (cardId: string) => withSession(() => client.get<ReportCardWire>(REPORTING_PATHS.card(cardId))),
  acknowledge: (cardId: string) =>
    withSession(() => client.post<AcknowledgeWire | undefined>(REPORTING_PATHS.acknowledge(cardId))),
};

/** Learner (§3): their own cards, read-only. The single-card view is picked from this list. */
export const learnerReportApi = {
  list: (studentRef: string) => withSession(() => client.get<ReportCardListWire>(REPORTING_PATHS.learnerCards(studentRef))),
};
