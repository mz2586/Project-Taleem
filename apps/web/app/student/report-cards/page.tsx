"use client";
// "My report cards" (REPORT_CARD_CONTRACT.md §3): the learner's own cards, newest first, read-only.
// Same live consent gate as every learner surface. Not cached on the device: offline says so.
import { useCallback, useEffect, useState } from "react";

import { ReportCardList } from "@/components/reporting/ReportCardList";
import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { learnerReportApi } from "@/lib/reporting/api";
import { cardListView, namePreference } from "@/lib/reporting/view";
import { cardList, reportCard, type ReportCard } from "@/lib/reporting/wire";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, type LoadFailure as Failure } from "@/lib/student/journey";

export default function StudentReportCardsPage() {
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

  const items = cards ? cardListView(cards, { t, locale }) : [];

  return (
    <AppShell title={t("student.reportCards.title")} band={band}>
      <div>
        <ButtonLink href="/student/progress" variant="ghost" label={t("student.progress.title")} />
      </div>
      <p style={{ margin: 0 }}>{t("student.reportCards.intro")}</p>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {!failure && !cards ? <Skeleton lines={3} label={t("student.reportCards.loading")} /> : null}
        {failure ? (
          <LoadFailure
            failure={failure}
            offlineTitle="student.reportCards.offlineTitle"
            offlineBody="student.reportCards.offlineBody"
            errorMessage="student.reportCards.error"
            onRetry={() => void load()}
          />
        ) : null}
        {cards && items.length === 0 ? (
          <EmptyState title={t("student.reportCards.emptyTitle")} body={t("student.reportCards.emptyBody")} />
        ) : null}
      </div>
      {items.length > 0 ? (
        <ReportCardList
          items={items}
          hrefFor={(id) => `/student/report-cards/${encodeURIComponent(id)}`}
          label={t("student.reportCards.listLabel")}
          newestLabel={t("student.reportCards.newest")}
          supersededLabel={t("student.reportCards.superseded")}
          unverifiedLabel={t("common.reportCard.listUnverified")}
        />
      ) : null}
    </AppShell>
  );
}
