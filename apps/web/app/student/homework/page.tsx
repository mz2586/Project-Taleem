"use client";
// Homework (HOMEWORK_AND_MARKING_CONTRACT.md §6, the AI-led path; §2 the optional class path). First
// "From your lessons": the written practice of every lesson the child has studied — no teacher needed.
// Then, only if the child is in a class with assignments, "From your class". Exact-answer items are
// checked by Taleem on the spot; open answers are saved (never "marked") and may be compared with an
// example. With nothing yet the screen says practice appears after a lesson and routes to Today.
// Offline, Send queues the answer for offline sync (`homework.submitted`): the item says "Saved on this
// phone — will send when online", the sync badge counts it, and once the server answers the item
// shows the server's result (the list is re-read) or a gentle conflict. Nothing is claimed as sent
// before the server said so. View model: lib/homework/student.ts + lib/homework/offlineQueue.ts.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { HomeworkItemCard } from "@/components/student/HomeworkItemCard";
import { LoadFailure } from "@/components/student/LoadFailure";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { formatDate, isoDateTime } from "@/lib/guardian/format";
import { homeworkApi, type SubmitTarget } from "@/lib/homework/api";
import { localDrafts } from "@/lib/homework/drafts";
import { homeworkDraftKey, homeworkKey, homeworkPayload, homeworkSyncFor } from "@/lib/homework/offlineQueue";
import {
  homeworkGroups,
  homeworkView,
  replaceItem as replaceInList,
  type HomeworkAssignmentView,
  type HomeworkItemView,
} from "@/lib/homework/student";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { watchConnectivity, type HomeworkResultRecord, type QueuedDelta } from "@/lib/offline";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, INSTRUCTION_LOCALE_PREFERENCE, type LoadFailure as Failure } from "@/lib/student/journey";
import { getOfflineClient } from "@/lib/student/offlineClient";

const SYNC_POLL_MS = 3000;

interface HomeworkSync {
  queue: readonly QueuedDelta[];
  results: readonly HomeworkResultRecord[];
  refresh: () => Promise<void>;
}

/** The offline sync queue + homework results (IndexedDB, so they survive a reload), polled. */
function useHomeworkSync(onConfirmed: (at: number) => void): HomeworkSync {
  const [state, setState] = useState<Omit<HomeworkSync, "refresh">>({ queue: [], results: [] });
  const confirmedRef = useRef(onConfirmed);
  confirmedRef.current = onConfirmed;
  const refresh = useCallback(async () => {
    try {
      const client = getOfflineClient();
      const [queue, results] = await Promise.all([client.sync.queue.all(), client.sync.homework.all()]);
      setState({ queue, results });
      const latest = Math.max(0, ...results.filter((r) => r.status !== "conflict").map((r) => r.at));
      if (latest > 0) confirmedRef.current(latest);
    } catch {
      /* no IndexedDB: nothing was queued on this phone */
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), SYNC_POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);
  return useMemo(() => ({ ...state, refresh }), [state, refresh]);
}

function targetOf(a: HomeworkAssignmentView): SubmitTarget {
  return a.source === "self_paced" || !a.assignmentId
    ? { source: "self_paced", objectiveCode: a.objectiveCode }
    : { source: "assignment", assignmentId: a.assignmentId };
}

export default function HomeworkPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, locale } = useLocale();
  const [assignments, setAssignments] = useState<HomeworkAssignmentView[] | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");
  const [online, setOnline] = useState(true);

  useEffect(() => watchConnectivity(setOnline), []);

  const titlePreference = useMemo(() => [locale, ...INSTRUCTION_LOCALE_PREFERENCE], [locale]);

  // When the list was last read: a sync result confirmed after that means the list is stale.
  const loadedAt = useRef(0);
  const load = useCallback(
    async (quiet = false) => {
      if (!ref) return;
      loadedAt.current = Date.now();
      if (!quiet) setStatus("loading");
      try {
        setAssignments(homeworkView(await homeworkApi.list(ref), INSTRUCTION_LOCALE_PREFERENCE, titlePreference));
        setStatus("ready");
      } catch (e) {
        if (!quiet) setStatus(classifyLoadError(e));
      }
    },
    [ref, titlePreference],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // The server answered an answer sent through sync: re-read the list so the item shows its state.
  const onConfirmed = useCallback(
    (at: number) => {
      if (loadedAt.current > 0 && at > loadedAt.current) void load(true);
    },
    [load],
  );
  const sync = useHomeworkSync(onConfirmed);

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
                  <EntrySection key={`${a.source}-${a.assignmentId}`} entry={a} studentRef={ref} online={online} onSent={replaceItem} sync={sync} />
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
  sync,
}: {
  entry: HomeworkAssignmentView;
  studentRef: string;
  online: boolean;
  onSent: (item: HomeworkItemView) => void;
  sync: HomeworkSync;
}) {
  const { t, locale, formatNumber } = useLocale();
  const titleAttrs = a.title ? contentAttrs({ locale: a.title.locale || null, text: a.title.text }) : null;
  const headingId = `hw-${a.source}-${a.assignmentId}`;
  const target = targetOf(a);
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
      {a.items.map((item, index) => {
        const where = { studentRef: ref, target, itemRef: item.itemRef };
        return (
          <HomeworkItemCard
            key={item.itemRef}
            item={item}
            position={index + 1}
            t={t}
            formatNumber={(n) => formatNumber(n)}
            online={online}
            draftKey={homeworkDraftKey(where)}
            drafts={localDrafts}
            send={(body) => homeworkApi.submit(ref, target, item.itemRef, body)}
            queue={async (body) => {
              const client = getOfflineClient();
              await client.sync.queue.enqueueHomework(
                homeworkPayload({ ...where, text: body.text, serverAttempt: item.attempt ?? 0, now: Date.now() }),
              );
              await sync.refresh();
              // Sends at once if a connection is there after all; the badge's auto-drain does the rest.
              void client.sync.drain().then(() => sync.refresh());
            }}
            sync={homeworkSyncFor(homeworkKey(where), sync.queue, sync.results)}
            onSent={onSent}
            contentPreference={INSTRUCTION_LOCALE_PREFERENCE}
          />
        );
      })}
    </section>
  );
}
