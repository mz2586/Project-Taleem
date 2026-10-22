"use client";
// My classes — the teacher's home. Lists the teacher's own classes (the server scopes them to the
// token's teacher and organization), each with its join code, and creates new ones. Rules:
// lib/teacher/*, unit-tested.
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { FormError, FormNotice, TextField } from "@/components/form";
import { RequireSession } from "@/components/RequireSession";
import { Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { formatDate } from "@/lib/guardian/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { teacherApi } from "@/lib/teacher/api";
import { CLASS_NAME_MAX, classNameProblem, sortClasses } from "@/lib/teacher/classes";
import { createClassErrorKey, teacherFailure, type TeacherFailure } from "@/lib/teacher/errors";
import type { Classroom, TeacherProfile } from "@/lib/teacher/types";

import { JoinCodeCard } from "./JoinCodeCard";
import { TeacherShell } from "./TeacherShell";
import { TeacherState } from "./TeacherState";

const cardStyle = {
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-4)",
  display: "grid",
  gap: "var(--space-2)",
} as const;

function CreateClassForm({ onCreated }: { onCreated: (c: Classroom) => void }) {
  const { t } = useLocale();
  const [name, setName] = useState("");
  const [fieldError, setFieldError] = useState<MessageKey | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState("");
  const [created, setCreated] = useState<Classroom | null>(null);
  const [busy, setBusy] = useState(false);
  const createdRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Move focus to the new code so a keyboard or screen-reader user lands on what to do next.
    if (created) createdRef.current?.focus();
  }, [created]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice("");
    const problem = classNameProblem(name);
    setFieldError(problem);
    if (problem) return;
    setBusy(true);
    try {
      const classroom = await teacherApi.createClass(name.trim());
      setName("");
      setNotice(t("teacher.classes.createdNotice", { name: classroom.name }));
      setCreated(classroom);
      onCreated(classroom);
    } catch (e) {
      setError(createClassErrorKey(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={cardStyle} aria-labelledby="create-class-title">
      <h2 id="create-class-title" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t("teacher.classes.createTitle")}
      </h2>
      <form onSubmit={submit} noValidate style={{ display: "grid", gap: "var(--space-3)" }}>
        <div aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
          {error ? <FormError message={t(error)} /> : null}
          {notice ? <FormNotice message={notice} /> : null}
        </div>
        <TextField
          id="class-name"
          label={t("teacher.classes.nameLabel")}
          hint={t("teacher.classes.nameHint")}
          error={fieldError ? t(fieldError) : undefined}
          value={name}
          maxLength={CLASS_NAME_MAX + 20}
          onChange={(e) => setName(e.target.value)}
          dir="auto"
          autoComplete="off"
          required
        />
        <div>
          <Button type="submit" variant="brand" label={t("teacher.classes.createSubmit")} loading={busy} />
        </div>
      </form>
      {created?.join_code ? (
        <div ref={createdRef} tabIndex={-1}>
          <JoinCodeCard code={created.join_code} className={created.name} headingLevel={3} headingId="created-code-title" />
        </div>
      ) : null}
    </section>
  );
}

function ClassesPage() {
  const { t, locale } = useLocale();
  const [profile, setProfile] = useState<TeacherProfile | null>(null);
  const [classes, setClasses] = useState<Classroom[] | null>(null);
  const [failure, setFailure] = useState<TeacherFailure | null>(null);

  const load = useCallback(async () => {
    setFailure(null);
    try {
      const [me, list] = await Promise.all([teacherApi.me(), teacherApi.listClasses()]);
      setProfile(me);
      setClasses(sortClasses(list.classes));
    } catch (e) {
      setFailure(teacherFailure(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <TeacherShell title={t("teacher.classes.title")}>
      {profile ? (
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
          <bdi>{t("teacher.shell.signedInAs", { name: profile.teacher.display_name })}</bdi>
          {profile.organization ? (
            <>
              {" · "}
              <bdi>{t("teacher.shell.organization", { name: profile.organization.name })}</bdi>
            </>
          ) : null}
        </p>
      ) : null}
      <p style={{ margin: 0 }}>{t("teacher.classes.intro")}</p>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {failure ? <TeacherState failure={failure} onRetry={() => void load()} /> : null}
        {!failure && !classes ? <Skeleton lines={4} label={t("teacher.classes.loading")} /> : null}
      </div>

      {classes && !failure ? (
        <>
          <section style={{ display: "grid", gap: "var(--space-3)" }} aria-labelledby="classes-title">
            <h2 id="classes-title" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {t("teacher.classes.listTitle")}
            </h2>
            {classes.length === 0 ? <p style={{ margin: 0 }}>{t("teacher.classes.empty")}</p> : null}
            {classes.length > 0 ? (
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-3)" }}>
                {classes.map((c) => (
                  <li key={c.class_id} style={cardStyle}>
                    <h3 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }} dir="auto">
                      <Link href={`/teacher/classes/${encodeURIComponent(c.class_id)}`} style={{ color: "var(--color-action-primary)" }}>
                        {c.name}
                      </Link>
                    </h3>
                    <span style={{ fontSize: "var(--font-size-body-min)" }}>
                      {t("teacher.classes.created", { date: formatDate(c.created_at, locale) })}
                    </span>
                    {c.join_code ? (
                      <span>
                        {t("teacher.code.title")}:{" "}
                        <strong dir="ltr" lang="en" style={{ fontFamily: "var(--font-latin)", letterSpacing: "0.1em" }}>
                          {c.join_code}
                        </strong>
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <CreateClassForm onCreated={(c) => setClasses((prev) => sortClasses([c, ...(prev ?? [])]))} />
        </>
      ) : null}
    </TeacherShell>
  );
}

export default function GuardedClassesPage() {
  return (
    <RequireSession role="teacher" signInPath="/teacher/signin">
      <ClassesPage />
    </RequireSession>
  );
}
