"use client";
// One of the learner's own report cards — the same card view a guardian sees, read-only (no
// acknowledge). The contract gives the learner a list read only, so the card is picked from it.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ReportCardActions } from "@/components/reporting/ReportCardActions";
import { ReportCardView } from "@/components/reporting/ReportCardView";
import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { learnerReportApi } from "@/lib/reporting/api";
import { cardView, namePreference, supersededIds } from "@/lib/reporting/view";
import { cardList, reportCard, type ReportCard } from "@/lib/reporting/wire";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, type LoadFailure as Failure } from "@/lib/student/journey";

export default function StudentReportCardPage() {
  const params = useParams<{ cardId: string }>();
  const cardId = decodeURIComponent(String(params.cardId));
  const { studentRef: ref, band } = useLearner();
  const { t, locale } = useLocale();
  const [cards, setCards] = useState<ReportCard[] | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  const load = useCallback(async () => {
    if (!ref) return;
    setFailure(null);
    setCards(null);
    try {
      setCards(cardList(await learnerReportApi.list(ref)).map((c) => reportCard(c, namePreference(locale))));
    } catch (e) {
      setFailure(classifyLoadError(e));
    }
  }, [ref, locale]);

  useEffect(() => {
    void load();
  }, [load]);

  const card = cards?.find((c) => c.cardId === cardId) ?? null;
  const view = card && cards ? cardView(card, { t, locale }, { supersededIds: supersededIds(cards) }) : null;
  const newer = view?.superseded ? (view.supersededBy ?? cards?.find((c) => c.supersedes === cardId)?.cardId ?? null) : null;

  return (
    <AppShell title={t("student.reportCards.cardTitle")} band={band}>
      <div data-print="hide">
        <ButtonLink href="/student/report-cards" variant="ghost" label={t("student.reportCards.back")} />
      </div>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {!failure && !cards ? <Skeleton lines={6} label={t("student.reportCards.loading")} /> : null}
        {failure ? (
          <LoadFailure
            failure={failure}
            offlineTitle="student.reportCards.offlineTitle"
            offlineBody="student.reportCards.offlineBody"
            errorMessage="student.reportCards.error"
            onRetry={() => void load()}
          />
        ) : null}
        {cards && !card ? <EmptyState title={t("student.reportCards.notFound")} body={t("student.reportCards.emptyBody")} /> : null}
      </div>
      {view ? (
        <>
          <ReportCardView view={view} t={t} newerHref={newer ? `/student/report-cards/${encodeURIComponent(newer)}` : null} />
          <ReportCardActions t={t} onPrint={() => window.print()} />
        </>
      ) : null}
    </AppShell>
  );
}
