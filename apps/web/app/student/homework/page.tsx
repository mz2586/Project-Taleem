"use client";
// Homework (HOMEWORK_AND_MARKING_CONTRACT.md §6, the AI-led path; §2 the optional class path). First
// "From your lessons": the written practice of every lesson the child has studied — no teacher needed.
// Then, only if the child is in a class with assignments, "From your class". Exact-answer items are
// checked by Taleem on the spot; open answers are saved (never "marked") and may be compared with an
// example. With nothing yet the screen says practice appears after a lesson and routes to Today. Sending is online only: offline the screen says so plainly, keeps what the
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
import {
  homeworkGroups,
  homeworkView,
  replaceItem as replaceInList,
  type HomeworkAssignmentView,
  type HomeworkItemView,
} from "@/lib/homework/student";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { watchConnectivity } from "@/lib/offline";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, INSTRUCTION_LOCALE_PREFERENCE, type LoadFailure as Failure } from "@/lib/student/journey";

export default function HomeworkPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, locale } = useLocale();
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
    setAssignments((list) => (list ? replaceInList(list, next) : list));
  }, []);

  const groups = useMemo(() => homeworkGroups(assignments ?? []), [assignments]);
  const empty = status === "ready" && groups.length === 0;

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

      {status === "ready" && groups.length > 0 ? (
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
          {groups.map((group) => {
            const groupId = `hw-group-${group.source}`;
            return (
              <section key={group.source} aria-labelledby={groupId} data-group={group.source} style={{ display: "grid", gap: "var(--space-4)" }}>
                <header style={{ display: "grid", gap: "var(--space-1)" }}>
                  <h2 id={groupId} style={{ margin: 0 }}>
                    {t(group.headingKey)}
                  </h2>
                  <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t(group.introKey)}</p>
                </header>
                {group.entries.map((a) => (
                  <EntrySection key={`${a.source}-${a.assignmentId}`} entry={a} studentRef={ref} online={online} onSent={replaceItem} />
                ))}
              </section>
            );
          })}
        </div>
      ) : null}
    </AppShell>
  );
}

function EntrySection({
  entry: a,
  studentRef: ref,
  online,
  onSent,
}: {
  entry: HomeworkAssignmentView;
  studentRef: string;
  online: boolean;
  onSent: (item: HomeworkItemView) => void;
}) {
  const { t, locale, formatNumber } = useLocale();
  const titleAttrs = a.title ? contentAttrs({ locale: a.title.locale || null, text: a.title.text }) : null;
  const headingId = `hw-${a.source}-${a.assignmentId}`;
  return (
    <section aria-labelledby={headingId} style={{ display: "grid", gap: "var(--space-3)" }}>
      <header style={{ display: "grid", gap: "var(--space-1)" }}>
        <h3 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
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
        </h3>
        {a.dueAt !== null ? (
          <time dateTime={isoDateTime(a.dueAt)}>{t("student.homework.due", { date: formatDate(a.dueAt, locale) })}</time>
        ) : null}
        {a.className ? (
          <span style={{ fontSize: "var(--font-size-body-min)" }}>
            {t("student.homework.classLabel")}: <bdi>{a.className}</bdi>
          </span>
        ) : null}
      </header>
      {a.items.map((item, index) => (
        <HomeworkItemCard
          key={item.itemRef}
          item={item}
          position={index + 1}
          t={t}
          formatNumber={(n) => formatNumber(n)}
          online={online}
          draftKey={draftKey(ref, a.assignmentId || `self-paced:${a.objectiveCode}`, item.itemRef)}
          drafts={localDrafts}
          send={(body) =>
            homeworkApi.submit(
              ref,
              a.source === "self_paced" || !a.assignmentId
                ? { source: "self_paced", objectiveCode: a.objectiveCode }
                : { source: "assignment", assignmentId: a.assignmentId },
              item.itemRef,
              body,
            )
          }
          onSent={onSent}
          contentPreference={INSTRUCTION_LOCALE_PREFERENCE}
        />
      ))}
    </section>
  );
}
