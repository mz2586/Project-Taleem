// Teacher portal types — mirror packages/contracts/school.openapi.yaml exactly. Nothing here is
// richer than the API: a learner is a ref, a display name and a join time, because that is all the
// server returns to a teacher.

export type TeacherStatus = "active" | "locked" | "suspended";

export interface Teacher {
  teacher_ref: string;
  organization_id: string;
  email: string;
  display_name: string;
  status: TeacherStatus;
  created_at: number;
}

export interface Organization {
  organization_id: string;
  name: string;
  country: string;
  curriculum_pack_id: string;
  default_locale: string;
  created_at: number;
}

export interface TeacherSessionToken {
  access_token: string;
  token_type: "Bearer";
  expires_at: number;
  expires_in: number;
  role: "teacher";
  subject: string;
}

/** POST /v1/school/teachers:signin — note: no refresh token yet (60-minute access token). */
export interface TeacherSignInResponse {
  teacher: Teacher;
  session: TeacherSessionToken;
}

export interface TeacherProfile {
  teacher: Teacher;
  organization: Organization | null;
}

export interface Classroom {
  class_id: string;
  organization_id: string;
  teacher_ref: string;
  name: string;
  join_code?: string;
  created_at: number;
  /** GET /v1/school/classes only: learners the teacher can see now (never hidden ones). */
  learner_count?: number;
}

export interface ClassLearner {
  student_ref: string;
  display_name: string;
  joined_at: number;
}

export type ClassDetail = Classroom & { learners: ClassLearner[] };

export interface Assignment {
  assignment_id: string;
  class_id: string;
  objective_code: string;
  due_at: number;
  assigned_by: string;
  created_at: number;
}

export interface LearnerAssignmentProgress {
  student_ref: string;
  display_name: string;
  /** Practised this objective since it was assigned. */
  completed: boolean;
  attempts_since_assigned: number;
  mastery: number | null;
  mastery_state: string;
  mastered: boolean;
}

export type AssignmentProgress = Assignment & {
  overdue: boolean;
  learners: LearnerAssignmentProgress[];
};

/** POST /v1/school/classes:join (guardian). */
export interface JoinClassResult {
  class_id: string;
  class_name: string;
  joined: boolean;
}

/** One entry of GET /v1/school/lessons: the teacher's curriculum pack, titles only. */
export interface PublishedLesson {
  objective_code: string;
  /** Localized title by locale tag ({ ur, en }). */
  title: Record<string, string>;
}

/** One entry of GET /v1/school/children/{ref}/classes (guardian of that child only). */
export interface ChildClass {
  class_id: string;
  class_name: string;
  organization_name: string;
  teacher_display_name: string;
  joined_at: number;
  /** Live: progress_sharing (the master switch) and learning consent are both current. */
  teacher_can_see_progress: boolean;
}
