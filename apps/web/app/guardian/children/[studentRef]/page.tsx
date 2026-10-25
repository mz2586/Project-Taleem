"use client";
// One child's progress — every section of GET /v1/guardian/children/{ref}, read-only, in the
// guardian's language. The presentation (weekly digest, honest "no progress yet", objective codes
// and server text marked with their own direction) is lib/guardian/progress.ts, unit-tested.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { RecommendationList } from "@/components/RecommendationList";
import { RequireSession } from "@/components/RequireSession";
import { Card, EmptyState, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { familyApi, guardianApi } from "@/lib/guardian/api";
import { childDetailModel, type DetailItem, type ForeignText } from "@/lib/guardian/progress";
import type { ChildOverview } from "@/lib/guardian/types";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { recommendationViews } from "@/lib/learning/rationale";
import { guardianReportApi } from "@/lib/reporting/api";
import { feedBadge } from "@/lib/reporting/view";
import { feed, type Feed } from "@/lib/reporting/wire";
import { classifyLoadError, type LoadFailure } from "@/lib/student/journey";
import { ApiError } from "@/lib/student/types";

import { GuardianLoadFailure } from "../../GuardianLoadFailure";
import { GuardianShell } from "../../GuardianShell";

type Status = "loading" | "ready" | "no-data" | "denied" | LoadFailure;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <h2 style={{ marginTop: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{title}</h2>
      {children}
    </Card>
  );
}

/** Curriculum codes and server text: marked with their own lang/dir, isolated from the interface. */
function Foreign({ value }: { value: ForeignText }) {
  const attrs = contentAttrs({ locale: value.locale ?? null, text: value.text });
  return (
    <bdi {...attrs} style={{ fontFamily: attrs.dir === "ltr" ? "var(--font-latin)" : undefined }}>
      {value.text}
    </bdi>
  );
}

function ItemList({ items, empty }: { items: DetailItem[]; empty: string }) {
  if (items.length === 0) return <p style={{ margin: 0 }}>{empty}</p>;
  return (
    <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
      {items.map((item, i) => (
        <li key={i}>
          {item.text}
          {item.extra ? (
            <>
              {" — "}
              <Foreign value={item.extra} />
            </>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function GuardianChildPage() {
  const params = useParams<{ studentRef: string }>();
  const ref = decodeURIComponent(String(params.studentRef));
  const { t, locale } = useLocale();
  const [data, setData] = useState<ChildOverview | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [reports, setReports] = useState<Feed | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    // The name is a nicety from the identity service; its failure never blocks the progress view.
    familyApi
      .me()
      .then((me) => setName(me.learners.find((l) => l.student_ref === ref)?.display_name ?? null))
      .catch(() => setName(null));
    // The report-card feed only adds a "new report" badge; its failure hides the badge, nothing else.
    guardianReportApi
      .notifications(ref)
      .then((wire) => setReports(feed(wire)))
      .catch(() => setReports(null));
    try {
      setData(await guardianApi.child(ref));
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setStatus("denied");
      // The guardian service answers 404 for a linked child with no learning data yet.
      else if (e instanceof ApiError && e.status === 404) setStatus("no-data");
      else setStatus(classifyLoadError(e));
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const model = status === "ready" && data ? childDetailModel({ locale }, data) : null;
  const explained = status === "ready" && data ? recommendationViews(data.recommendation_explanations) : [];
  const title = name ? t("guardian.child.title", { name }) : t("guardian.child.titleUnnamed");
  const badge = feedBadge(reports, t);

  return (
    <GuardianShell title={title}>
      <div>
        <ButtonLink href="/guardian" variant="ghost" label={t("guardian.child.backToChildren")} />
      </div>
      {status !== "denied" ? (
        <Card>
          <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
            <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("guardian.child.reportCards")}</h2>
            {badge ? (
              <p data-new-reports="" style={{ margin: 0, fontWeight: 700 }}>
                <span aria-hidden="true">● </span>
                {badge}
              </p>
            ) : null}
            <p style={{ margin: 0 }}>{t("guardian.child.reportCardsIntro")}</p>
            <ButtonLink
              href={`/guardian/children/${encodeURIComponent(ref)}/report-cards`}
              variant="primary"
              label={t("guardian.child.reportCards")}
            />
          </div>
        </Card>
      ) : null}
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={6} label={t("guardian.child.loading")} /> : null}
        {status === "denied" ? <EmptyState title={t("guardian.child.deniedTitle")} body={t("guardian.child.deniedBody")} /> : null}
        {status === "no-data" ? <EmptyState title={t("guardian.child.noDataTitle")} body={t("guardian.child.noDataBody")} /> : null}
        {status === "offline" || status === "signed-out" || status === "error" ? (
          <GuardianLoadFailure
            failure={status}
            offlineTitle="guardian.child.offlineTitle"
            offlineBody="guardian.child.offlineBody"
            errorMessage="guardian.child.error"
            onRetry={() => void load()}
          />
        ) : null}

        {model && !model.hasProgress ? (
          <EmptyState title={t("guardian.child.noDataTitle")} body={t("guardian.child.noDataBody")} />
        ) : null}

        {/* Why the AI teacher recommends each step — shown even before practice (e.g. after the
            starting questions), because the reasons rest on the child's own answers. */}
        {model && explained.length > 0 ? (
          <Section title={t("guardian.child.whyTitle")}>
            <RecommendationList items={explained} empty={t("guardian.child.whyEmpty")} />
            <p style={{ margin: 0, marginTop: "var(--space-2)", fontSize: "var(--font-size-body-min)" }}>
              {t("guardian.child.whyNote")}
            </p>
          </Section>
        ) : null}

        {model && model.hasProgress ? (
          <>
            <Section title={t("guardian.weekly.title")}>
              {model.weekly.kind === "quiet" ? (
                <p style={{ margin: 0 }}>{model.weekly.text}</p>
              ) : (
                <div style={{ display: "grid", gap: "var(--space-2)" }}>
                  <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                    {model.weekly.lines.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                  <p style={{ margin: 0 }}>{model.weekly.encouragement}</p>
                </div>
              )}
            </Section>

            <Section title={t("guardian.child.overview")}>
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {model.overview.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </Section>

            <Section title={t("guardian.child.attentionTitle")}>
              <ItemList items={model.attention} empty={t("guardian.child.attentionEmpty")} />
            </Section>

            <Section title={t("guardian.child.recommendationsTitle")}>
              <ItemList items={model.recommendations} empty={t("guardian.child.recommendationsEmpty")} />
            </Section>

            {model.nextStep ? (
              <Section title={t("guardian.child.nextStepTitle")}>
                <ItemList items={[model.nextStep]} empty="" />
                <p style={{ margin: 0, marginTop: "var(--space-2)", fontSize: "var(--font-size-body-min)" }}>
                  {t("guardian.child.aiNote")}
                </p>
              </Section>
            ) : null}

            <Section title={t("guardian.child.streakTitle")}>
              <p style={{ margin: 0 }}>{model.streak}</p>
              <p style={{ margin: 0 }}>{model.attendance}</p>
            </Section>

            <Section title={t("guardian.child.knowledgeTitle")}>
              {model.knowledge.length === 0 ? (
                <p style={{ margin: 0 }}>{t("guardian.child.knowledgeEmpty")}</p>
              ) : (
                <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                  {model.knowledge.map((k, i) => (
                    <li key={i}>
                      <Foreign value={k.objective} />: {k.value}
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title={t("guardian.child.timelineTitle")}>
              <ItemList items={model.timeline} empty={t("guardian.child.timelineEmpty")} />
            </Section>

            <Section title={t("guardian.child.assessmentsTitle")}>
              <ItemList items={model.assessments} empty={t("guardian.child.assessmentsEmpty")} />
            </Section>

            <Section title={t("guardian.child.achievementsTitle")}>
              <ItemList items={model.achievements} empty={t("guardian.child.achievementsEmpty")} />
            </Section>

            <Section title={t("guardian.child.syncTitle")}>
              <p style={{ margin: 0 }}>
                <span aria-hidden="true">{model.sync.stale ? "⚠ " : "✓ "}</span>
                {model.sync.text}
              </p>
              {model.sync.lastSync ? <p style={{ margin: 0 }}>{model.sync.lastSync}</p> : null}
              <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("guardian.sync.deviceNote")}</p>
            </Section>
          </>
        ) : null}

        {status === "ready" ? (
          <div>
            <Button variant="ghost" label={t("guardian.child.refresh")} onClick={() => void load()} />
          </div>
        ) : null}
      </div>
    </GuardianShell>
  );
}

export default function GuardedGuardianChildPage() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <GuardianChildPage />
    </RequireSession>
  );
}
