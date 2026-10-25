"use client";
// Dashboard "Today" — answers "what should I do now?" with one clear action, plus encouraging
// progress. The journey rules (including "no published lessons yet") live in lib/student/journey.ts;
// this page renders `todayModel`.
//
// The Start action is shown only once we know it leads somewhere: while no lesson is published the
// screen says there is nothing to learn yet, instead of offering a button into an empty session.
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { ReadAloud } from "@/components/student/ReadAloud";
import { ObjectiveName } from "@/components/student/ObjectiveName";
import { TodayIdeas } from "@/components/student/TodayIdeas";
import { Card, EmptyState, ProgressRing, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";
import { aiTeacherApi, learningApi } from "@/lib/student/api";
import { whyNextModel, type WhyNextModel } from "@/lib/student/aiTeacher";
import { objectiveName, type ObjectiveTitles } from "@/lib/student/objectiveName";
import { placementEntry, type PlacementEntry } from "@/lib/student/placement";
import {
  classifyLoadError,
  emptyKnowledge,
  orOnNotFound,
  TODAY_EMPTY_COPY,
  todayModel,
  type LoadFailure as Failure,
  type TodayModel,
} from "@/lib/student/journey";

/**
 * "Why this next?" — the AI Teacher's plan in plain words (lib/student/aiTeacher.ts `whyNextModel`).
 * Loaded only when opened: a native disclosure, so it is keyboard- and screen-reader-operable.
 */
function WhyNext({ studentRef, titles }: { studentRef: string; titles: ObjectiveTitles }) {
  const { t, locale } = useLocale();
  const [open, setOpen] = useState(false);
  const [model, setModel] = useState<WhyNextModel | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open || model) return;
    let live = true;
    setFailed(false);
    aiTeacherApi
      .plan(studentRef)
      .then((plan) => live && setModel(whyNextModel(plan)))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [open, model, studentRef]);

  const spoken = model
    ? [t("student.whyNext.chose", { choice: t(model.choice) }), ...model.reasons.map((r) => t(r.key, r.params)), t(model.certainty)].join(" ")
    : "";

  return (
    <details onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary style={{ minHeight: "var(--size-touch-min)", display: "flex", alignItems: "center", cursor: "pointer" }}>
        {t("student.whyNext.open")}
      </summary>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
        {open && !model && !failed ? <Skeleton lines={2} label={t("student.whyNext.loading")} /> : null}
        {failed ? <p style={{ margin: 0 }}>{t("student.whyNext.error")}</p> : null}
        {model ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                <h3 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.whyNext.title")}</h3>
                {/* Interface text, so it is read in the interface locale. */}
                <ReadAloud label={t("student.whyNext.title")} text={spoken} lang={locale} />
              </div>
              <p style={{ margin: 0 }}>
                {t("student.whyNext.chose", { choice: t(model.choice) })}
                {model.objective ? (
                  <>
                    {" · "}
                    <ObjectiveName name={objectiveName(model.objective, titles)} />
                  </>
                ) : null}
              </p>
              <span>{t("student.whyNext.becauseLabel")}</span>
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {model.reasons.map((r) => (
                  <li key={r.key}>{t(r.key, r.params)}</li>
                ))}
              </ul>
              <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t(model.certainty)}</p>
            </div>
          </Card>
        ) : null}
      </div>
    </details>
  );
}

export default function TodayPage() {
  const { studentRef: ref, band, displayName } = useLearner();
  const { t, locale, formatPercent } = useLocale();
  const [model, setModel] = useState<TodayModel | null>(null);
  const [entry, setEntry] = useState<PlacementEntry | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [today, knowledge, progress] = await Promise.all([
        // An older server without the aggregate: carry on without it (journey.ts handles null).
        orOnNotFound(learningApi.today(ref), null),
        // A brand-new learner has no knowledge record yet: that is empty, not an error.
        orOnNotFound(learningApi.knowledge(ref), emptyKnowledge(ref)),
        orOnNotFound(learningApi.progress(ref), null),
      ]);
      setModel(todayModel({ today, knowledge, progress }));
      setStatus("ready");
      // "Find your starting point" — offered only when a placement is possible for this learner
      // (lib/student/placement.ts). It never blocks Today: any failure simply hides the entry.
      learningApi
        .placement(ref)
        .then((p) => setEntry(placementEntry(p)))
        .catch(() => setEntry(null));
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const greeting = displayName ? t("student.today.greeting", { name: displayName }) : t("student.today.greetingNoName");

  return (
    <AppShell title={t("common.appName")} band={band}>
      <section style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)" }}>
        <div>
          <h2 style={{ margin: 0 }}>{greeting}</h2>
          <p style={{ margin: 0 }}>{t("student.today.subtitle")}</p>
        </div>
        {/* Interface text, so it is read in the interface locale. */}
        <ReadAloud
          label={t("student.today.greetingAudio")}
          text={`${greeting} ${t("student.today.subtitle")}`}
          lang={locale}
        />
      </section>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={4} label={t("common.loading")} /> : null}

        {status !== "loading" && status !== "ready" ? (
          <LoadFailure
            failure={status}
            offlineTitle="student.today.offlineTitle"
            offlineBody="student.today.offlineBody"
            errorMessage="student.today.error"
            onRetry={() => void load()}
          />
        ) : null}

        {status === "ready" && model ? (
          <>
            {entry ? (
              <Card>
                <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
                  <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t(entry.title)}</h2>
                  <p style={{ margin: 0 }}>{t(entry.body)}</p>
                  <ButtonLink href={entry.href} variant="brand" label={t(entry.action)} icon={<span aria-hidden="true">🧭</span>} />
                </div>
              </Card>
            ) : null}

            {model.canStart ? (
              // The one clear action — largest, first in reading order.
              <Card>
                <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
                  <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.today.startTitle")}</h2>
                  <p style={{ margin: 0 }}>{t("student.today.startBody")}</p>
                  <ButtonLink
                    href="/student/session"
                    variant="brand"
                    label={t("student.today.start")}
                    icon={<span aria-hidden="true">▶</span>}
                  />
                </div>
              </Card>
            ) : null}

            {model.canStart && ref ? <WhyNext studentRef={ref} titles={model.titles} /> : null}

            {model.kind === "learning" ? (
              <>
                <section style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", flexWrap: "wrap" }}>
                  <ProgressRing value={model.masteryValue} label={t("common.mastery.label")} formatPercent={formatPercent} />
                  <div style={{ display: "grid", gap: "var(--space-1)" }}>
                    <span>{t("student.today.masteredOf", { mastered: model.mastered, total: model.total })}</span>
                    <span>
                      {model.dueCount > 0
                        ? t("student.today.reviewsDue", { count: model.dueCount })
                        : t("student.today.noReviews")}
                    </span>
                    {model.accuracy !== null ? (
                      <span>{t("student.today.accuracy", { value: formatPercent(model.accuracy) })}</span>
                    ) : null}
                  </div>
                </section>
                <TodayIdeas objectives={model.objectives} titles={model.titles} label={t("student.today.ideasLabel")} t={t} />
              </>
            ) : (
              <EmptyState title={t(TODAY_EMPTY_COPY[model.kind].title)} body={t(TODAY_EMPTY_COPY[model.kind].body)} />
            )}
          </>
        ) : null}

        {/* Always reachable — including offline, when Today itself cannot load. */}
        <section style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
          <p style={{ margin: 0 }}>{t("student.offline.entryBody")}</p>
          <ButtonLink href="/student/offline" variant="ghost" label={t("student.offline.entry")} icon={<span aria-hidden="true">📥</span>} />
        </section>
      </div>
    </AppShell>
  );
}
