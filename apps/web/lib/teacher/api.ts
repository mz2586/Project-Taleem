// Typed client for the teacher half of the school API (/v1/school/*).
//
// The server decides everything: which classes are this teacher's, which learners are visible
// (only those whose guardian currently shares progress), and whether a lesson is published. This
// client never sends a teacher or organization id — both come from the verified token.

import { createApiClient } from "../apiClient";
import { API_BASE } from "../session/config";
import { currentAccessToken, withSession } from "../session/store";
import type {
  Assignment,
  AssignmentProgress,
  ClassDetail,
  Classroom,
  PublishedLessonManifest,
  TeacherProfile,
  TeacherSignInResponse,
} from "./types";

const anonymous = createApiClient(API_BASE, () => "");
const client = createApiClient(API_BASE, () => currentAccessToken());

const seg = encodeURIComponent;

export const publicTeacherApi = {
  signIn: (body: { email: string; passphrase: string }) =>
    anonymous.post<TeacherSignInResponse>("/v1/school/teachers:signin", body),
};

export const teacherApi = {
  me: () => withSession(() => client.get<TeacherProfile>("/v1/school/me")),

  listClasses: () => withSession(() => client.get<{ classes: Classroom[] }>("/v1/school/classes")),

  createClass: (name: string) => withSession(() => client.post<Classroom>("/v1/school/classes", { name })),

  classDetail: (classId: string) =>
    withSession(() => client.get<ClassDetail>(`/v1/school/classes/${seg(classId)}`)),

  listAssignments: (classId: string) =>
    withSession(() =>
      client.get<{ assignments: Assignment[] }>(`/v1/school/classes/${seg(classId)}/assignments`),
    ),

  createAssignment: (classId: string, body: { objectiveCode: string; dueAt: number }) =>
    withSession(() =>
      client.post<Assignment>(`/v1/school/classes/${seg(classId)}/assignments`, body),
    ),

  progress: (classId: string, assignmentId: string) =>
    withSession(() =>
      client.get<AssignmentProgress>(
        `/v1/school/classes/${seg(classId)}/assignments/${seg(assignmentId)}/progress`,
      ),
    ),

  /**
   * The published-lesson index. The school API has no lesson list of its own; this is the offline
   * package index, which today's PDP does not grant to the `teacher` role (403). The caller turns
   * that into an honest "the list is not available" — see lessonChoices().
   */
  publishedLessons: () =>
    withSession(() => client.get<{ packages: PublishedLessonManifest[] }>("/v1/offline/packages")),
};
