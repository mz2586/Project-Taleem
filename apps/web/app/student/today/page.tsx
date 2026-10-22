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
import { Card, EmptyState, ProgressRing, Skeleton, StateBadge } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";
import { learningApi } from "@/lib/student/api";
import {
  classifyLoadError,
  emptyKnowledge,
  masteryStateKey,
  orOnNotFound,
  TODAY_EMPTY_COPY,
  todayModel,
  type LoadFailure as Failure,
  type TodayModel,
} from "@/lib/student/journey";

export default function TodayPage() {
  const { studentRef: ref, band, displayName } = useLearner();
  const { t, locale, formatPercent } = useLocale();
  const [model, setModel] = useState<TodayModel | null>(null);
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

        {status === "offline" || status === "signed-out" || status === "error" ? (
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
                {model.objectives.length > 0 ? (
                  <section aria-label={t("student.today.ideasLabel")} style={{ display: "grid", gap: "var(--space-2)" }}>
                    {model.objectives.slice(0, 8).map(([code, o]) => (
                      <Card key={code}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                          <span dir="auto">{code}</span>
                          <StateBadge state={o.state} label={t(masteryStateKey(o.state))} />
                        </div>
                      </Card>
                    ))}
                  </section>
                ) : null}
              </>
            ) : (
              <EmptyState title={t(TODAY_EMPTY_COPY[model.kind].title)} body={t(TODAY_EMPTY_COPY[model.kind].body)} />
            )}
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
