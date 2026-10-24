"use client";
// One report card for a guardian (REPORT_CARD_CONTRACT.md §3): the card in plain words and pictures,
// the teacher's note, "I have seen this" (once — the button is gone after it is recorded), and a
// print button. The print stylesheet (design-system/print.css) leaves the portal header, navigation
// and buttons off the page, so the card prints on A4 or saves as a PDF on its own.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { ReportCardActions } from "@/components/reporting/ReportCardActions";
import { ReportCardView } from "@/components/reporting/ReportCardView";
import { RequireSession } from "@/components/RequireSession";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { formatDate } from "@/lib/guardian/format";
import { useLocale } from "@/lib/i18n/useLocale";
import { guardianReportApi } from "@/lib/reporting/api";
import {
  acknowledgedAt,
  ackReducer,
  canAcknowledge,
  cardView,
  initialAck,
  namePreference,
  readFailure,
  showAcknowledge,
  type AckState,
  type ReadFailure,
} from "@/lib/reporting/view";
import { reportCard, type ReportCard } from "@/lib/reporting/wire";

import { GuardianLoadFailure } from "../../../../GuardianLoadFailure";
import { GuardianShell } from "../../../../GuardianShell";

const nowSeconds = () => Math.floor(Date.now() / 1000);

function GuardianReportCardPage() {
  const params = useParams<{ studentRef: string; cardId: string }>();
  const ref = decodeURIComponent(String(params.studentRef));
  const cardId = decodeURIComponent(String(params.cardId));
  const { t, locale } = useLocale();
  const [card, setCard] = useState<ReportCard | null>(null);
  const [failure, setFailure] = useState<ReadFailure | null>(null);
  const [state, dispatch] = useReducer(ackReducer, { status: "unseen" } as AckState);
  const statusRef = useRef<HTMLDivElement | null>(null);
  const sending = useRef(false);

  const load = useCallback(async () => {
    setFailure(null);
    setCard(null);
    try {
      const loaded = reportCard(await guardianReportApi.card(cardId), namePreference(locale));
      setCard(loaded);
      dispatch({ type: "loaded", state: initialAck(loaded) });
    } catch (e) {
      setFailure(readFailure(e));
    }
  }, [cardId, locale]);

  useEffect(() => {
    void load();
  }, [load]);

  const acknowledge = useCallback(async () => {
    if (!canAcknowledge(state) || sending.current) return;
    sending.current = true;
    dispatch({ type: "send" });
    try {
      const body = await guardianReportApi.acknowledge(cardId);
      dispatch({ type: "done", at: acknowledgedAt(body, nowSeconds()) });
    } catch (e) {
      dispatch({ type: "failed", error: e, now: nowSeconds() });
    } finally {
      sending.current = false;
      requestAnimationFrame(() => statusRef.current?.focus());
    }
  }, [cardId, state]);

  const view = card ? cardView(card, { t, locale }) : null;
  const list = `/guardian/children/${encodeURIComponent(ref)}/report-cards`;
  const newerHref = view?.supersededBy ? `${list}/${encodeURIComponent(view.supersededBy)}` : null;

  return (
    <GuardianShell title={t("guardian.reportCards.cardTitle")}>
      <div data-print="hide">
        <ButtonLink href={list} variant="ghost" label={t("guardian.reportCards.back")} />
      </div>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {!failure && !card ? <Skeleton lines={6} label={t("guardian.reportCards.loading")} /> : null}
        {failure === "not-available" || failure === "consent" ? (
          <EmptyState title={t("guardian.reportCards.notAvailableTitle")} body={t("guardian.reportCards.notAvailableBody")} />
        ) : null}
        {failure === "offline" || failure === "signed-out" || failure === "error" ? (
          <GuardianLoadFailure
            failure={failure}
            offlineTitle="guardian.reportCards.offlineTitle"
            offlineBody="guardian.reportCards.offlineBody"
            errorMessage="guardian.reportCards.error"
            onRetry={() => void load()}
          />
        ) : null}
      </div>
      {view ? (
        <>
          <ReportCardView view={view} t={t} newerHref={newerHref} />
          <ReportCardActions
            t={t}
            ack={showAcknowledge(view) ? state : null}
            seenDate={state.status === "seen" ? formatDate(state.at, locale) : null}
            onAcknowledge={() => void acknowledge()}
            onPrint={() => window.print()}
            statusRef={statusRef}
          />
        </>
      ) : null}
    </GuardianShell>
  );
}

export default function GuardedGuardianReportCardPage() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <GuardianReportCardPage />
    </RequireSession>
  );
}
