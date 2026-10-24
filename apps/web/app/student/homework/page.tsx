"use client";
// Homework (HOMEWORK_AND_MARKING_CONTRACT.md §2): every assignment of every class the child is in,
// with its written items. The child writes an answer and sends it to the teacher; the teacher's note
// and mark come back here. With no homework the screen keeps its honest empty state and routes back
// to guided learning. Sending is online only: offline the screen says so plainly, keeps what the
// child typed on this phone, and never claims anything was sent. View model: lib/homework/student.ts.
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { HomeworkItemCard } from "@/components/student/HomeworkItemCard";
import { LoadFailure } from "@/components/student/LoadFailure";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { formatDate, isoDateTime } from "@/lib/guardian/format";
import { homeworkApi } from "@/lib/homework/api";
import { draftKey, localDrafts } from "@/lib/homework/drafts";
import { homeworkView, type HomeworkAssignmentView, type HomeworkItemView } from "@/lib/homework/student";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { watchConnectivity } from "@/lib/offline";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, INSTRUCTION_LOCALE_PREFERENCE, type LoadFailure as Failure } from "@/lib/student/journey";

export default function HomeworkPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, locale, formatNumber } = useLocale();
  const [assignments, setAssignments] = useState<HomeworkAssignmentView[] | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");
  const [online, setOnline] = useState(true);

  useEffect(() => watchConnectivity(setOnline), []);

  const titlePreference = useMemo(() => [locale, ...INSTRUCTION_LOCALE_PREFERENCE], [locale]);

  const load = useCallback(async () => {
    if (!ref) return;
    setStatus("loading");
    try {
      setAssignments(homeworkView(await homeworkApi.list(ref), INSTRUCTION_LOCALE_PREFERENCE, titlePreference));
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref, titlePreference]);

  useEffect(() => {
    void load();
  }, [load]);

  const replaceItem = useCallback((next: HomeworkItemView) => {
    setAssignments((list) =>
      list
        ? list.map((a) =>
            a.assignmentId !== next.assignmentId
              ? a
              : { ...a, items: a.items.map((i) => (i.itemRef === next.itemRef ? next : i)) },
          )
        : list,
    );
  }, []);

  const empty = status === "ready" && (assignments?.length ?? 0) === 0;

  return (
    <AppShell title={t("student.homework.title")} band={band}>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={4} label={t("student.homework.loading")} /> : null}
        {status !== "loading" && status !== "ready" ? (
          <LoadFailure
            failure={status}
            offlineTitle="student.homework.offlineTitle"
            offlineBody="student.homework.offlineBody"
            errorMessage="student.homework.error"
            onRetry={() => void load()}
          />
        ) : null}
        {empty ? (
          <EmptyState
            title={t("student.homework.emptyTitle")}
            body={t("student.homework.emptyBody")}
            action={<ButtonLink href="/student/today" variant="brand" label={t("common.goToToday")} />}
          />
        ) : null}
      </div>

      {status === "ready" && assignments && assignments.length > 0 ? (
        <div style={{ display: "grid", gap: "var(--space-4)" }}>
          <p style={{ margin: 0 }}>{t("student.homework.intro")}</p>
          {!online ? (
            <p
              role="status"
              style={{
                margin: 0,
                padding: "var(--space-3)",
                border: "2px solid var(--color-action-primary)",
                borderRadius: "var(--radius-md)",
              }}
            >
              <span aria-hidden="true">⚠ </span>
              {t("student.homework.offlineNotice")}
            </p>
          ) : null}
          {assignments.map((a) => {
            const titleAttrs = a.title ? contentAttrs({ locale: a.title.locale || null, text: a.title.text }) : null;
            const headingId = `hw-${a.assignmentId}`;
            return (
              <section key={a.assignmentId} aria-labelledby={headingId} style={{ display: "grid", gap: "var(--space-3)" }}>
                <header style={{ display: "grid", gap: "var(--space-1)" }}>
                  <h2 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                    {a.title && titleAttrs ? (
                      <span lang={titleAttrs.lang} dir={titleAttrs.dir}>
                        {a.title.text}
                      </span>
                    ) : (
                      <>
                        {t("student.homework.lessonLabel")}:{" "}
                        <bdi dir="ltr" style={{ fontFamily: "var(--font-latin)" }}>
                          {a.objectiveCode}
                        </bdi>
                      </>
                    )}
                  </h2>
                  <time dateTime={isoDateTime(a.dueAt)}>{t("student.homework.due", { date: formatDate(a.dueAt, locale) })}</time>
                  {a.className ? (
                    <span style={{ fontSize: "var(--font-size-body-min)" }}>
                      {t("student.homework.classLabel")}: <bdi>{a.className}</bdi>
                    </span>
                  ) : null}
                </header>
                {a.items.map((item, index) => {
                  const key = draftKey(ref, a.assignmentId, item.itemRef);
                  return (
                    <HomeworkItemCard
                      key={item.itemRef}
                      item={item}
                      position={index + 1}
                      t={t}
                      formatNumber={(n) => formatNumber(n)}
                      online={online}
                      draftKey={key}
                      drafts={localDrafts}
                      send={(body) => homeworkApi.submit(ref, a.assignmentId, item.itemRef, body)}
                      onSent={replaceItem}
                    />
                  );
                })}
              </section>
            );
          })}
        </div>
      ) : null}
    </AppShell>
  );
}
