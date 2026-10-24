"use client";
// "To mark" for one class (HOMEWORK_AND_MARKING_CONTRACT.md §3): the written answers waiting for the
// teacher, oldest first, with a status filter for those sent back and those already marked. Marking
// or sending back removes the row from this view and moves focus to a notice saying what happened.
// A class that is not this teacher's is "not available", as on every teacher screen.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";

import { FormNotice } from "@/components/form";
import { RequireSession } from "@/components/RequireSession";
import { Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { markingApi } from "@/lib/homework/api";
import { QUEUE_STATUS_KEYS, QUEUE_STATUSES, queueView, type SubmissionRowView } from "@/lib/homework/teacher";
import type { QueueStatus } from "@/lib/homework/types";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { INSTRUCTION_LOCALE_PREFERENCE } from "@/lib/student/journey";
import { teacherFailure, type TeacherFailure } from "@/lib/teacher/errors";

import { TeacherShell } from "../../../TeacherShell";
import { TeacherState } from "../../../TeacherState";
import { SubmissionCard, type Decision } from "./SubmissionCard";

const EMPTY_KEYS: Record<QueueStatus, MessageKey> = {
  submitted: "teacher.marking.empty.submitted",
  returned: "teacher.marking.empty.returned",
  marked: "teacher.marking.empty.marked",
};

const filterLabel = {
  display: "inline-flex",
  alignItems: "center",
  gap: "var(--space-2)",
  minHeight: "var(--size-touch-min)",
  padding: "0 var(--space-3)",
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
} as const;

function MarkingPage() {
  const { t, locale, formatNumber } = useLocale();
  const params = useParams<{ classId: string }>();
  const classId = params?.classId ?? "";
  const filterName = useId();
  const [status, setStatus] = useState<QueueStatus>("submitted");
  const [rows, setRows] = useState<SubmissionRowView[] | null>(null);
  const [failure, setFailure] = useState<TeacherFailure | null>(null);
  const [notice, setNotice] = useState<MessageKey | null>(null);
  const noticeRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    setFailure(null);
    setRows(null);
    try {
      const wire = await markingApi.queue(classId, status);
      // Prompts keep their authored language; the interface language is not an input.
      setRows(queueView(wire.submissions ?? [], INSTRUCTION_LOCALE_PREFERENCE));
    } catch (e) {
      setFailure(teacherFailure(e));
    }
  }, [classId, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const decided = useCallback((submissionId: string, decision: Decision) => {
    setRows((list) => (list ? list.filter((r) => r.submissionId !== submissionId) : list));
    setNotice(decision === "marked" ? "teacher.marking.done.marked" : "teacher.marking.done.returned");
    requestAnimationFrame(() => noticeRef.current?.focus());
  }, []);

  const title = failure === "not-available" ? t("teacher.state.notAvailableTitle") : t("teacher.marking.title");

  return (
    <TeacherShell title={title}>
      <div>
        <ButtonLink href={`/teacher/classes/${encodeURIComponent(classId)}`} variant="ghost" label={t("teacher.marking.back")} />
      </div>
      <p style={{ margin: 0 }}>{t("teacher.marking.intro")}</p>

      <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)", minWidth: 0 }}>
        <legend style={{ padding: 0, marginBottom: "var(--space-1)" }}>{t("teacher.marking.filterLabel")}</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          {QUEUE_STATUSES.map((s) => (
            <label key={s} style={{ ...filterLabel, fontWeight: status === s ? 700 : 400 }}>
              <input
                type="radio"
                name={filterName}
                value={s}
                checked={status === s}
                onChange={() => {
                  setNotice(null);
                  setStatus(s);
                }}
              />
              <span>{t(QUEUE_STATUS_KEYS[s])}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div ref={noticeRef} tabIndex={-1}>
        {notice ? <FormNotice message={t(notice)} /> : null}
      </div>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {failure ? <TeacherState failure={failure} onRetry={() => void load()} /> : null}
        {!failure && !rows ? <Skeleton lines={4} label={t("teacher.marking.loading")} /> : null}
        {rows && rows.length === 0 ? <p style={{ margin: 0 }}>{t(EMPTY_KEYS[status])}</p> : null}
        {rows && rows.length > 0 ? (
          <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("teacher.marking.count", { count: formatNumber(rows.length) })}</p>
        ) : null}
      </div>

      {rows && rows.length > 0 ? (
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          {rows.map((row) => (
            <SubmissionCard key={row.submissionId} row={row} t={t} locale={locale} onDecided={decided} />
          ))}
        </div>
      ) : null}

      {rows && notice ? (
        <div>
          <Button variant="ghost" label={t("teacher.marking.reload")} onClick={() => void load()} />
        </div>
      ) : null}
    </TeacherShell>
  );
}

export default function GuardedMarkingPage() {
  return (
    <RequireSession role="teacher" signInPath="/teacher/signin">
      <MarkingPage />
    </RequireSession>
  );
}
