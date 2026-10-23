import { describe, expect, it } from "vitest";

import { CATALOGS } from "../../i18n/messages";
import { granted, learner } from "../../guardian/__tests__/fixtures";
import { ApiError } from "../../student/types";
import {
  dueAtFromDateInput,
  isPastDue,
  lessonChoices,
  localDateInput,
  objectiveCodeProblem,
  sortAssignments,
} from "../assignments";
import { classNameProblem, learnerRows, sortClasses } from "../classes";
import {
  createAssignmentErrorKey,
  createClassErrorKey,
  joinClassErrorKey,
  signInErrorKey,
  teacherFailure,
} from "../errors";
import { joinAvailability, normaliseClassCode, sharesProgress } from "../join";
import { learnerStatus, masteryKey, progressView } from "../progress";
import { teacherEnvelope } from "../session";
import type {
  Assignment,
  AssignmentProgress,
  Classroom,
  LearnerAssignmentProgress,
  PublishedLesson,
} from "../types";

const err = (status: number, problem: Record<string, unknown> = {}) => new ApiError(status, problem);

describe("teacherFailure — honest, non-leaking access states", () => {
  it("separates offline, signed out and an inactive teacher", () => {
    expect(teacherFailure(err(0))).toBe("offline");
    expect(teacherFailure(err(401))).toBe("signed-out");
    expect(teacherFailure(err(403, { code: "TEACHER_INACTIVE" }))).toBe("inactive");
  });

  it("shows 404 and any other 403 identically, so a class's existence is never confirmed", () => {
    expect(teacherFailure(err(404, { code: "NOT_FOUND" }))).toBe("not-available");
    expect(teacherFailure(err(403, { code: "FORBIDDEN" }))).toBe("not-available");
  });

  it("anything else is a plain error", () => {
    expect(teacherFailure(err(500))).toBe("error");
    expect(teacherFailure(new Error("boom"))).toBe("error");
  });
});

describe("signInErrorKey — one uniform failure", () => {
  it("gives the same message for every rejected credential", () => {
    expect(signInErrorKey(err(401, { detail: "Sign-in details are not correct" }))).toBe("teacher.signIn.failed");
    expect(signInErrorKey(err(422))).toBe("teacher.signIn.failed");
  });

  it("distinguishes only rate limiting and connectivity", () => {
    expect(signInErrorKey(err(429))).toBe("teacher.signIn.tooMany");
    expect(signInErrorKey(err(0))).toBe("teacher.signIn.offline");
    expect(signInErrorKey(err(500))).toBe("teacher.signIn.generic");
  });

  it("the uniform message explains locking without saying which detail was wrong", () => {
    const text = CATALOGS.en.teacher.signIn.failed;
    expect(text).toMatch(/locked/);
    expect(text).not.toMatch(/email (is|was) (wrong|unknown)|no account/i);
  });
});

describe("mutation error keys", () => {
  it("class creation", () => {
    expect(createClassErrorKey(err(422))).toBe("teacher.classes.nameInvalid");
    expect(createClassErrorKey(err(403, { code: "TEACHER_INACTIVE" }))).toBe("teacher.errors.inactive");
    expect(createClassErrorKey(err(0))).toBe("teacher.errors.offline");
  });

  it("assignment creation", () => {
    expect(createAssignmentErrorKey(err(422, { code: "LESSON_NOT_PUBLISHED" }))).toBe("teacher.assign.notPublished");
    expect(createAssignmentErrorKey(err(422, { code: "VALIDATION_FAILED", detail: "due date must be in the future" }))).toBe(
      "teacher.assign.duePast",
    );
    expect(createAssignmentErrorKey(err(422, { code: "VALIDATION_FAILED" }))).toBe("teacher.errors.checkDetails");
    expect(createAssignmentErrorKey(err(404))).toBe("teacher.errors.notAvailable");
  });

  it("guardian join", () => {
    expect(joinClassErrorKey(err(404))).toBe("teacher.guardianJoin.errors.notFound");
    expect(joinClassErrorKey(err(409, { code: "CONSENT_REQUIRED" }))).toBe("teacher.guardianJoin.errors.consentNeeded");
    expect(joinClassErrorKey(err(429))).toBe("teacher.guardianJoin.errors.tooMany");
    expect(joinClassErrorKey(err(403))).toBe("teacher.guardianJoin.errors.notGuardian");
    expect(joinClassErrorKey(err(401))).toBe("teacher.guardianJoin.errors.signedOut");
    expect(joinClassErrorKey(err(0))).toBe("teacher.guardianJoin.errors.offline");
    expect(joinClassErrorKey(err(422))).toBe("teacher.guardianJoin.errors.checkDetails");
    expect(joinClassErrorKey(new Error())).toBe("teacher.guardianJoin.errors.generic");
  });
});

describe("teacherEnvelope", () => {
  it("adapts the school sign-in into the shared session envelope with no refresh token", () => {
    const env = teacherEnvelope({
      teacher: {
        teacher_ref: "tch_1",
        organization_id: "org_1",
        email: "t@example.org",
        display_name: "Ms Ayesha",
        status: "active",
        created_at: 1,
      },
      session: { access_token: "tok", token_type: "Bearer", expires_at: 99, expires_in: 60, role: "teacher", subject: "tch_1" },
    });
    expect(env.refresh_token).toBe("");
    expect(env.session.role).toBe("teacher");
    expect(env.session.access_token).toBe("tok");
    // Nothing about the teacher's account is copied into the stored learner/guardian slots.
    expect(env.learner).toBeUndefined();
    expect(env.guardian).toBeUndefined();
  });
});

function cls(over: Partial<Classroom> = {}): Classroom {
  return { class_id: "c1", organization_id: "o", teacher_ref: "t", name: "A", join_code: "ABCD-EFGH", created_at: 10, ...over };
}

describe("classes", () => {
  it("validates the class name like the server (1..80 after trimming)", () => {
    expect(classNameProblem("   ")).toBe("teacher.classes.nameEmpty");
    expect(classNameProblem("x".repeat(81))).toBe("teacher.classes.nameLong");
    expect(classNameProblem(" Grade 4 ")).toBeNull();
  });

  it("lists newest first", () => {
    const sorted = sortClasses([cls({ class_id: "old", created_at: 1 }), cls({ class_id: "new", created_at: 5 })]);
    expect(sorted.map((c) => c.class_id)).toEqual(["new", "old"]);
  });

  it("shows only what the API returned and never the ref as a name", () => {
    const rows = learnerRows([
      { student_ref: "stu_b", display_name: "Zara", joined_at: 2 },
      { student_ref: "stu_a", display_name: "", joined_at: 1 },
      { student_ref: "stu_c", display_name: "Ali", joined_at: 3 },
    ]);
    expect(rows.map((r) => r.name)).toEqual(["Ali", "Zara", null]);
    expect(rows[2]!.fallbackKey).toBe("teacher.detail.unnamed");
    expect(Object.keys(rows[0]!).sort()).toEqual(["fallbackKey", "joinedAt", "name", "ref"]);
  });
});

describe("lessonChoices — honest about what is published", () => {
  it("is 'unavailable' (not 'none') when the list cannot be read (403, offline)", () => {
    expect(lessonChoices({ ok: false, error: err(403) })).toEqual({ kind: "unavailable" });
    expect(lessonChoices({ ok: false, error: err(0) })).toEqual({ kind: "unavailable" });
  });

  it("is 'none-published' for an empty index — today's reality", () => {
    expect(lessonChoices({ ok: true, value: { lessons: [] } })).toEqual({ kind: "none-published" });
    expect(lessonChoices({ ok: true, value: {} })).toEqual({ kind: "none-published" });
  });

  it("lists each published objective once, sorted, with the title in the reader's locale", () => {
    const lesson = (objective_code: string, en: string, ur?: string): PublishedLesson => ({
      objective_code,
      title: ur ? { en, ur } : { en },
    });
    const value = { lessons: [lesson("M4-B", "Fractions", "کسور"), lesson("M4-A", "Place value"), lesson("M4-B", "Dup")] };
    expect(lessonChoices({ ok: true, value }, "ur")).toEqual({
      kind: "list",
      lessons: [
        { objectiveCode: "M4-A", title: "Place value" }, // no Urdu title: falls back to English
        { objectiveCode: "M4-B", title: "کسور" },
      ],
    });
    expect(lessonChoices({ ok: true, value: { lessons: [{ objective_code: "X", title: {} }] } })).toEqual({
      kind: "list",
      lessons: [{ objectiveCode: "X", title: "" }],
    });
  });
});

describe("assignment inputs", () => {
  it("validates the objective code length", () => {
    expect(objectiveCodeProblem(" ")).toBe("teacher.assign.codeEmpty");
    expect(objectiveCodeProblem("x".repeat(65))).toBe("teacher.assign.codeLong");
    expect(objectiveCodeProblem("M4-NUM-01")).toBeNull();
  });

  const now = Math.floor(new Date(2026, 9, 23, 10, 0, 0).getTime() / 1000);

  it("turns a date into the end of that local day", () => {
    const result = dueAtFromDateInput("2026-10-30", now);
    expect(result).toEqual({ ok: true, dueAt: Math.floor(new Date(2026, 9, 30, 23, 59, 59).getTime() / 1000) });
  });

  it("accepts today (due tonight) but not yesterday", () => {
    expect(dueAtFromDateInput("2026-10-23", now).ok).toBe(true);
    expect(dueAtFromDateInput("2026-10-22", now)).toEqual({ ok: false, problem: "teacher.assign.duePast" });
  });

  it("rejects empty and impossible dates", () => {
    expect(dueAtFromDateInput("", now)).toEqual({ ok: false, problem: "teacher.assign.dueEmpty" });
    expect(dueAtFromDateInput("2026-02-31", now)).toEqual({ ok: false, problem: "teacher.assign.dueInvalid" });
    expect(dueAtFromDateInput("31/10/2026", now)).toEqual({ ok: false, problem: "teacher.assign.dueInvalid" });
  });

  it("formats a date-input value in the local calendar", () => {
    expect(localDateInput(now)).toBe("2026-10-23");
  });

  it("orders assignments soonest-due first and knows when one is past due", () => {
    const a = (id: string, due_at: number): Assignment => ({
      assignment_id: id,
      class_id: "c",
      objective_code: id,
      due_at,
      assigned_by: "t",
      created_at: 0,
    });
    expect(sortAssignments([a("late", 30), a("soon", 10)]).map((x) => x.assignment_id)).toEqual(["soon", "late"]);
    expect(isPastDue(a("x", 10), 11)).toBe(true);
    expect(isPastDue(a("x", 10), 10)).toBe(false);
  });
});

function row(over: Partial<LearnerAssignmentProgress> = {}): LearnerAssignmentProgress {
  return {
    student_ref: "stu",
    display_name: "Ali",
    completed: false,
    attempts_since_assigned: 0,
    mastery: null,
    mastery_state: "not_started",
    mastered: false,
    ...over,
  };
}

describe("progress — plain-language states", () => {
  it("derives one status per learner", () => {
    expect(learnerStatus(row({ mastered: true, completed: true }), false)).toBe("mastered");
    expect(learnerStatus(row({ completed: true, attempts_since_assigned: 2 }), true)).toBe("practised");
    expect(learnerStatus(row(), true)).toBe("overdue");
    expect(learnerStatus(row(), false)).toBe("not-started");
  });

  it("maps every engine mastery state, and an unknown one to 'not known yet'", () => {
    for (const s of ["not_started", "in_progress", "mastered", "needs_review", "at_risk"]) {
      expect(masteryKey(s)).toBe(`teacher.progress.mastery.${s}`);
    }
    expect(masteryKey("weird")).toBe("teacher.progress.mastery.unknown");
  });

  it("summarises and puts learners needing attention first", () => {
    const progress: AssignmentProgress = {
      assignment_id: "a",
      class_id: "c",
      objective_code: "M4-A",
      due_at: 1,
      assigned_by: "t",
      created_at: 0,
      overdue: true,
      learners: [
        row({ student_ref: "m", display_name: "Mona", completed: true, mastered: true, mastery: 0.93, mastery_state: "mastered", attempts_since_assigned: 6 }),
        row({ student_ref: "p", display_name: "Bilal", completed: true, mastery: 0.5, mastery_state: "in_progress", attempts_since_assigned: 3 }),
        row({ student_ref: "n", display_name: "" }),
      ],
    };
    const view = progressView(progress);
    expect(view.rows.map((r) => r.status)).toEqual(["overdue", "practised", "mastered"]);
    expect(view.rows[0]!.attention).toBe(true);
    expect(view.rows[0]!.name).toBeNull();
    expect(view.summary).toEqual({ total: 3, practised: 2, mastered: 1, notStarted: 1 });
    expect(view.rows[2]!.mastery).toBe(0.93);
    expect(view.rows[0]!.mastery).toBeNull();
  });

  it("clamps a malformed mastery and attempt count rather than showing nonsense", () => {
    const view = progressView({
      assignment_id: "a",
      class_id: "c",
      objective_code: "x",
      due_at: 1,
      assigned_by: "t",
      created_at: 0,
      overdue: false,
      learners: [row({ mastery: 1.7, attempts_since_assigned: -3 })],
    });
    expect(view.rows[0]!.mastery).toBe(1);
    expect(view.rows[0]!.attempts).toBe(0);
  });
});

describe("guardian join", () => {
  it("normalises a class code like the server", () => {
    expect(normaliseClassCode("abcd efgh")).toBe("ABCD-EFGH");
    expect(normaliseClassCode(" ABCD-2345 ")).toBe("ABCD-2345");
    expect(normaliseClassCode("ABCD-EFG")).toBeNull();
    // 0, O, 1, I and L are not in the alphabet.
    expect(normaliseClassCode("ABCD-EFG0")).toBeNull();
    expect(normaliseClassCode("ABCD-EFGI")).toBeNull();
  });

  it("is available only while the child may learn", () => {
    expect(joinAvailability(learner({ consent: granted(["learning_data"]) }))).toBe("ready");
    expect(joinAvailability(learner())).toBe("needs-learning-consent");
    expect(joinAvailability(learner({ status: "suspended", consent: granted(["learning_data"]) }))).toBe(
      "needs-learning-consent",
    );
  });

  it("knows whether progress is shared now", () => {
    expect(sharesProgress(learner({ consent: granted(["learning_data", "progress_sharing"]) }))).toBe(true);
    expect(sharesProgress(learner({ consent: granted(["learning_data"]) }))).toBe(false);
  });
});

describe("teacher wording rule (TALEEM_SCHOOL_PARTNER_REQUIREMENTS: no formal-schooling claims)", () => {
  type Tree = { [k: string]: string | Tree };
  const leaves = (t: Tree): string[] => Object.values(t).flatMap((v) => (typeof v === "string" ? [v] : leaves(v)));

  it("the English teacher copy never says accredited, enrolment or school", () => {
    for (const text of leaves(CATALOGS.en.teacher as unknown as Tree)) {
      expect(text).not.toMatch(/accredit|enrol|school|qualification|diploma/i);
    }
  });

  it("the Urdu teacher copy never says school (اسکول) or accredited (تسلیم شدہ)", () => {
    for (const text of leaves(CATALOGS.ur.teacher as unknown as Tree)) {
      expect(text).not.toMatch(/اسکول|سکول|تسلیم شدہ|داخلہ/);
    }
  });

  it("the join copy explains the progress_sharing consent and how to stop it", () => {
    const j = CATALOGS.en.teacher.guardianJoin;
    expect(j.sharing).toMatch(/shared with that class's teacher/);
    expect(j.stop).toContain("{scope}");
    expect(j.agree).toContain("{name}");
  });
});
