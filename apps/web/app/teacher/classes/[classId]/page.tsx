"use client";
// One class: its join code, the learners currently sharing progress with this teacher (exactly what
// GET /v1/school/classes/{id} returns — a display name and a join date, nothing more), its
// assignments, and the form to assign a published lesson. A class that is not this teacher's is
// "not available" — the same answer as one that does not exist.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { FormError, FormNotice, TextField } from "@/components/form";
import { RequireSession } from "@/components/RequireSession";
import { Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { formatDate, isoDateTime } from "@/lib/guardian/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { teacherApi } from "@/lib/teacher/api";
import {
  dueAtFromDateInput,
  isPastDue,
  lessonChoices,
  localDateInput,
  objectiveCodeProblem,
  OBJECTIVE_CODE_MAX,
  sortAssignments,
  type LessonChoices,
} from "@/lib/teacher/assignments";
import { learnerRows } from "@/lib/teacher/classes";
import { createAssignmentErrorKey, teacherFailure, type TeacherFailure } from "@/lib/teacher/errors";
import type { Assignment, ClassDetail } from "@/lib/teacher/types";

import { JoinCodeCard } from "../../JoinCodeCard";
import { TeacherShell } from "../../TeacherShell";
import { TeacherState } from "../../TeacherState";

const sectionStyle = {
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-4)",
  display: "grid",
  gap: "var(--space-3)",
} as const;

const selectStyle = {
  minHeight: "var(--size-touch-min)",
  padding: "var(--space-2)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
  fontSize: "var(--font-size-body-min-urdu)",
} as const;

const nowSeconds = () => Math.floor(Date.now() / 1000);

function AssignForm({ classId, onAssigned }: { classId: string; onAssigned: () => Promise<void> }) {
  const { t, locale } = useLocale();
  const selectId = useId();
  const [choices, setChoices] = useState<LessonChoices | null>(null);
  const [code, setCode] = useState("");
  const [due, setDue] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ code?: MessageKey; due?: MessageKey }>({});
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    teacherApi
      .publishedLessons()
      .then((value) => live && setChoices(lessonChoices({ ok: true, value }, locale)))
      .catch((error: unknown) => live && setChoices(lessonChoices({ ok: false, error })));
    return () => {
      live = false;
    };
  }, [locale]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice("");
    const codeIssue = objectiveCodeProblem(code);
    const dueAt = dueAtFromDateInput(due, nowSeconds());
    const next = { code: codeIssue ?? undefined, due: dueAt.ok ? undefined : dueAt.problem };
    setFieldErrors(next);
    if (next.code || !dueAt.ok) return;
    setBusy(true);
    try {
      const assignment = await teacherApi.createAssignment(classId, { objectiveCode: code.trim(), dueAt: dueAt.dueAt });
      setNotice(t("teacher.assign.done", { code: assignment.objective_code, date: formatDate(assignment.due_at, locale) }));
      setCode("");
      setDue("");
      await onAssigned();
    } catch (e) {
      setError(createAssignmentErrorKey(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={sectionStyle} aria-labelledby="assign-title">
      <h2 id="assign-title" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t("teacher.assign.title")}
      </h2>
      <p style={{ margin: 0 }}>{t("teacher.assign.intro")}</p>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
        {!choices ? <Skeleton lines={1} label={t("teacher.assign.checking")} /> : null}
        {choices?.kind === "none-published" ? <p style={{ margin: 0 }}>{t("teacher.assign.nonePublished")}</p> : null}
        {choices?.kind === "unavailable" ? <p style={{ margin: 0 }}>{t("teacher.assign.listUnavailable")}</p> : null}
        {error ? <FormError message={t(error)} /> : null}
        {notice ? <FormNotice message={notice} /> : null}
      </div>
      {choices && choices.kind !== "none-published" ? (
        <form onSubmit={submit} noValidate style={{ display: "grid", gap: "var(--space-3)" }}>
          {choices.kind === "list" ? (
            <div style={{ display: "grid", gap: "var(--space-1)" }}>
              <label htmlFor={selectId}>{t("teacher.assign.lessonLabel")}</label>
              <select
                id={selectId}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                aria-invalid={fieldErrors.code ? true : undefined}
                aria-describedby={fieldErrors.code ? `${selectId}-error` : undefined}
                style={selectStyle}
              >
                <option value="">{t("teacher.assign.lessonPick")}</option>
                {choices.lessons.map((l) => (
                  <option key={l.objectiveCode} value={l.objectiveCode}>
                    {l.title ? `${l.title} (${l.objectiveCode})` : l.objectiveCode}
                  </option>
                ))}
              </select>
              {fieldErrors.code ? (
                <span id={`${selectId}-error`} role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-body-min)" }}>
                  {t(fieldErrors.code)}
                </span>
              ) : null}
            </div>
          ) : (
            <TextField
              id="objective-code"
              label={t("teacher.assign.codeLabel")}
              hint={t("teacher.assign.codeHint")}
              error={fieldErrors.code ? t(fieldErrors.code) : undefined}
              value={code}
              maxLength={OBJECTIVE_CODE_MAX + 8}
              onChange={(e) => setCode(e.target.value)}
              dir="ltr"
              autoComplete="off"
              spellCheck={false}
              required
            />
          )}
          <TextField
            id="due-date"
            type="date"
            label={t("teacher.assign.dueLabel")}
            hint={t("teacher.assign.dueHint")}
            error={fieldErrors.due ? t(fieldErrors.due) : undefined}
            value={due}
            min={localDateInput(nowSeconds())}
            onChange={(e) => setDue(e.target.value)}
            required
          />
          <div>
            <Button type="submit" variant="brand" label={t("teacher.assign.submit")} loading={busy} />
          </div>
        </form>
      ) : null}
    </section>
  );
}

function AssignmentList({ classId, assignments }: { classId: string; assignments: Assignment[] }) {
  const { t, locale } = useLocale();
  if (assignments.length === 0) return <p style={{ margin: 0 }}>{t("teacher.assignments.empty")}</p>;
  const now = nowSeconds();
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
      {assignments.map((a) => {
        const past = isPastDue(a, now);
        return (
          <li
            key={a.assignment_id}
            style={{ display: "grid", gap: "var(--space-1)", paddingBottom: "var(--space-2)", borderBottom: "1px solid var(--color-focus-ring)" }}
          >
            <strong>
              {t("teacher.assignments.lessonLabel")}:{" "}
              <bdi dir="ltr" style={{ fontFamily: "var(--font-latin)" }}>
                {a.objective_code}
              </bdi>
            </strong>
            <span>
              <time dateTime={isoDateTime(a.due_at)}>{t("teacher.assignments.due", { date: formatDate(a.due_at, locale) })}</time>
              {past ? (
                <>
                  {" · "}
                  <span style={{ color: "var(--color-danger)" }}>
                    <span aria-hidden="true">⚠ </span>
                    {t("teacher.assignments.pastDue")}
                  </span>
                </>
              ) : null}
            </span>
            <span>
              <Link
                href={`/teacher/classes/${encodeURIComponent(classId)}/assignments/${encodeURIComponent(a.assignment_id)}`}
                style={{ color: "var(--color-action-primary)", display: "inline-flex", alignItems: "center", minHeight: "var(--size-touch-min)" }}
              >
                {t("teacher.assignments.viewProgress")}
              </Link>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function ClassPage() {
  const { t, locale } = useLocale();
  const params = useParams<{ classId: string }>();
  const classId = params?.classId ?? "";
  const [detail, setDetail] = useState<ClassDetail | null>(null);
  const [assignments, setAssignments] = useState<Assignment[] | null>(null);
  const [failure, setFailure] = useState<TeacherFailure | null>(null);
  const [assignmentsFailed, setAssignmentsFailed] = useState(false);

  const loadAssignments = useCallback(async () => {
    setAssignmentsFailed(false);
    try {
      setAssignments(sortAssignments((await teacherApi.listAssignments(classId)).assignments));
    } catch {
      setAssignmentsFailed(true);
    }
  }, [classId]);

  const load = useCallback(async () => {
    setFailure(null);
    try {
      setDetail(await teacherApi.classDetail(classId));
    } catch (e) {
      setFailure(teacherFailure(e));
      return;
    }
    await loadAssignments();
  }, [classId, loadAssignments]);

  useEffect(() => {
    void load();
  }, [load]);

  const title = detail && !failure ? detail.name : failure === "not-available" ? t("teacher.state.notAvailableTitle") : t("teacher.classes.title");
  const learners = detail ? learnerRows(detail.learners) : [];

  return (
    <TeacherShell title={title}>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {failure ? <TeacherState failure={failure} onRetry={() => void load()} /> : null}
        {!failure && !detail ? <Skeleton lines={4} label={t("teacher.detail.loading")} /> : null}
      </div>

      {detail && !failure ? (
        <>
          {detail.join_code ? <JoinCodeCard code={detail.join_code} className={detail.name} headingId="class-code-title" /> : null}

          <section style={sectionStyle} aria-labelledby="learners-title">
            <h2 id="learners-title" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {t("teacher.detail.learnersTitle")}
            </h2>
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("teacher.detail.learnersIntro")}</p>
            {learners.length === 0 ? <p style={{ margin: 0 }}>{t("teacher.detail.learnersEmpty")}</p> : null}
            {learners.length > 0 ? (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                {learners.map((l) => (
                  <li key={l.ref}>
                    {l.name ? <bdi>{l.name}</bdi> : t(l.fallbackKey)}
                    {" — "}
                    <time dateTime={isoDateTime(l.joinedAt)} style={{ fontSize: "var(--font-size-body-min)" }}>
                      {t("teacher.detail.joined", { date: formatDate(l.joinedAt, locale) })}
                    </time>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <section style={sectionStyle} aria-labelledby="assignments-title">
            <h2 id="assignments-title" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {t("teacher.assignments.title")}
            </h2>
            <div aria-live="polite">
              {assignmentsFailed ? (
                <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
                  <p style={{ margin: 0 }}>{t("teacher.assignments.loadError")}</p>
                  <Button variant="ghost" label={t("teacher.state.retry")} onClick={() => void loadAssignments()} />
                </div>
              ) : null}
              {!assignmentsFailed && !assignments ? <Skeleton lines={2} label={t("teacher.assignments.loading")} /> : null}
              {assignments ? <AssignmentList classId={classId} assignments={assignments} /> : null}
            </div>
          </section>

          <AssignForm classId={classId} onAssigned={loadAssignments} />
        </>
      ) : null}
    </TeacherShell>
  );
}

export default function GuardedClassPage() {
  return (
    <RequireSession role="teacher" signInPath="/teacher/signin">
      <ClassPage />
    </RequireSession>
  );
}
