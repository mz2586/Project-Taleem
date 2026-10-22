"use client";
// Per-learner progress on one assignment, in plain words: practised or not, answers since it was
// assigned, the engine's understanding estimate, and whether it is past due. Only learners whose
// guardian shares progress right now appear (the server filters live). View model:
// lib/teacher/progress.ts, unit-tested.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { RequireSession } from "@/components/RequireSession";
import { Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { formatDate, isoDateTime } from "@/lib/guardian/format";
import { useLocale } from "@/lib/i18n/useLocale";
import { teacherApi } from "@/lib/teacher/api";
import { teacherFailure, type TeacherFailure } from "@/lib/teacher/errors";
import { progressView } from "@/lib/teacher/progress";
import type { AssignmentProgress } from "@/lib/teacher/types";

import { TeacherShell } from "../../../../TeacherShell";
import { TeacherState } from "../../../../TeacherState";

const cell = {
  padding: "var(--space-2)",
  borderBottom: "1px solid var(--color-focus-ring)",
  textAlign: "start",
  verticalAlign: "top",
} as const;

function ProgressPage() {
  const { t, locale, formatPercent } = useLocale();
  const params = useParams<{ classId: string; assignmentId: string }>();
  const classId = params?.classId ?? "";
  const assignmentId = params?.assignmentId ?? "";
  const [progress, setProgress] = useState<AssignmentProgress | null>(null);
  const [failure, setFailure] = useState<TeacherFailure | null>(null);

  const load = useCallback(async () => {
    setFailure(null);
    try {
      setProgress(await teacherApi.progress(classId, assignmentId));
    } catch (e) {
      setFailure(teacherFailure(e));
    }
  }, [classId, assignmentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const view = useMemo(() => (progress ? progressView(progress) : null), [progress]);
  const title = failure === "not-available" ? t("teacher.state.notAvailableTitle") : t("teacher.progress.title");

  return (
    <TeacherShell title={title}>
      <div>
        <ButtonLink href={`/teacher/classes/${encodeURIComponent(classId)}`} variant="ghost" label={t("teacher.progress.back")} />
      </div>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {failure ? <TeacherState failure={failure} onRetry={() => void load()} /> : null}
        {!failure && !progress ? <Skeleton lines={4} label={t("teacher.progress.loading")} /> : null}
      </div>

      {progress && view && !failure ? (
        <>
          <p style={{ margin: 0 }}>{t("teacher.progress.intro", { code: progress.objective_code })}</p>
          <p style={{ margin: 0 }}>
            <time dateTime={isoDateTime(progress.due_at)}>{t("teacher.progress.due", { date: formatDate(progress.due_at, locale) })}</time>
            {view.overdue ? (
              <>
                {" · "}
                <strong style={{ color: "var(--color-danger)" }}>
                  <span aria-hidden="true">⚠ </span>
                  {t("teacher.progress.overdue")}
                </strong>
              </>
            ) : null}
          </p>

          {view.rows.length === 0 ? (
            <p style={{ margin: 0 }}>{t("teacher.progress.empty")}</p>
          ) : (
            <>
              <p style={{ margin: 0 }}>
                {t("teacher.progress.summary", {
                  practised: view.summary.practised,
                  total: view.summary.total,
                  mastered: view.summary.mastered,
                })}
              </p>
              <div style={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", width: "100%" }}>
                  <caption style={{ textAlign: "start", fontWeight: 700, paddingBottom: "var(--space-2)" }}>
                    {t("teacher.progress.tableCaption")}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" style={cell}>
                        {t("teacher.progress.colLearner")}
                      </th>
                      <th scope="col" style={cell}>
                        {t("teacher.progress.colStatus")}
                      </th>
                      <th scope="col" style={cell}>
                        {t("teacher.progress.colAttempts")}
                      </th>
                      <th scope="col" style={cell}>
                        {t("teacher.progress.colMastery")}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.rows.map((r) => (
                      <tr key={r.ref}>
                        <th scope="row" style={{ ...cell, fontWeight: 400 }}>
                          {r.name ? <bdi>{r.name}</bdi> : t("teacher.detail.unnamed")}
                        </th>
                        <td style={cell}>
                          {r.attention ? (
                            <strong style={{ color: "var(--color-danger)" }}>
                              <span aria-hidden="true">⚠ </span>
                              {t(r.statusKey)}
                            </strong>
                          ) : (
                            t(r.statusKey)
                          )}
                        </td>
                        <td style={cell}>{t("teacher.progress.attemptsValue", { count: r.attempts })}</td>
                        <td style={cell}>
                          {r.mastery === null
                            ? t(r.masteryKey)
                            : t("teacher.progress.masteryPercent", { state: t(r.masteryKey), percent: formatPercent(r.mastery) })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      ) : null}
    </TeacherShell>
  );
}

export default function GuardedProgressPage() {
  return (
    <RequireSession role="teacher" signInPath="/teacher/signin">
      <ProgressPage />
    </RequireSession>
  );
}
