"use client";
// One child's report cards (REPORT_CARD_CONTRACT.md §3), newest first, replaced cards marked, and
// "Get a report": the guardian asks Taleem to issue a card for a closed period
// (lib/reporting/generate.ts). On success the new card opens; when a card for exactly those dates
// already exists (409 REPORT_CARD_EXISTS) that card opens instead — it is not an error. Read live:
// report cards are not cached on the device, so offline says a connection is needed rather than
// showing something that may be out of date.
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { GenerateReport, type GenerateMessage } from "@/components/reporting/GenerateReport";
import { ReportCardList } from "@/components/reporting/ReportCardList";
import { RequireSession } from "@/components/RequireSession";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { familyApi } from "@/lib/guardian/api";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { guardianReportApi } from "@/lib/reporting/api";
import {
  chosenPeriod,
  failedResult,
  generateBody,
  generatedResult,
  generateFailure,
  generateMessage,
  periodOptions,
  type GenerateResult,
  type PeriodChoice,
} from "@/lib/reporting/generate";
import { defaultPeriod, type PeriodInputs } from "@/lib/reporting/teacher";
import { cardListView, namePreference, readFailure, type ReadFailure } from "@/lib/reporting/view";
import { cardList, reportCard, type ReportCard } from "@/lib/reporting/wire";
import { localDateInput } from "@/lib/teacher/assignments";

import { GuardianLoadFailure } from "../../../GuardianLoadFailure";
import { GuardianShell } from "../../../GuardianShell";

const nowSeconds = () => Math.floor(Date.now() / 1000);

function GuardianReportCardsPage() {
  const params = useParams<{ studentRef: string }>();
  const ref = decodeURIComponent(String(params.studentRef));
  const router = useRouter();
  const { t, locale } = useLocale();
  const [cards, setCards] = useState<ReportCard[] | null>(null);
  const [failure, setFailure] = useState<ReadFailure | null>(null);
  const [name, setName] = useState<string | null>(null);

  const [choice, setChoice] = useState<PeriodChoice>("last_month");
  const [custom, setCustom] = useState<PeriodInputs>(() => defaultPeriod(nowSeconds()));
  const [problems, setProblems] = useState<{ start?: MessageKey; end?: MessageKey }>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<GenerateMessage | null>(null);
  const sending = useRef(false);

  const load = useCallback(async () => {
    setFailure(null);
    setCards(null);
    familyApi
      .me()
      .then((me) => setName(me.learners.find((l) => l.student_ref === ref)?.display_name ?? null))
      .catch(() => setName(null));
    try {
      const wire = await guardianReportApi.list(ref);
      setCards(cardList(wire).map((c) => reportCard(c, namePreference(locale))));
    } catch (e) {
      setFailure(readFailure(e));
    }
  }, [ref, locale]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = cards ? cardListView(cards, { t, locale }) : [];
  const base = `/guardian/children/${encodeURIComponent(ref)}/report-cards`;

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    setMessage(null);
    const period = chosenPeriod(choice, custom, nowSeconds());
    if (!period.ok) {
      setProblems(period.problems);
      return;
    }
    setProblems({});
    sending.current = true;
    setBusy(true);
    let result: GenerateResult;
    try {
      const wire = await guardianReportApi.generate(ref, generateBody(period));
      result = generatedResult(reportCard(wire, namePreference(locale)));
    } catch (e) {
      const why = generateFailure(e);
      let fresh: ReportCard[] | null = null;
      if (why === "exists") {
        // The card for exactly these dates is already there: find it and open it.
        try {
          fresh = cardList(await guardianReportApi.list(ref)).map((c) => reportCard(c, namePreference(locale)));
          setCards(fresh);
        } catch {
          fresh = null;
        }
      }
      result = failedResult(why, period, fresh);
    } finally {
      sending.current = false;
      setBusy(false);
    }
    if (result.kind === "open") {
      router.push(`${base}/${encodeURIComponent(result.cardId)}`);
      return;
    }
    setMessage(generateMessage(result, t));
  }

  return (
    <GuardianShell title={name ? t("guardian.reportCards.title", { name }) : t("guardian.reportCards.titleUnnamed")}>
      <div data-print="hide">
        <ButtonLink href={`/guardian/children/${encodeURIComponent(ref)}`} variant="ghost" label={t("guardian.reportCards.backToChild")} />
      </div>
      <p style={{ margin: 0 }}>{t("guardian.reportCards.intro")}</p>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {!failure && !cards ? <Skeleton lines={3} label={t("guardian.reportCards.loading")} /> : null}
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
        {cards && items.length === 0 ? (
          <EmptyState title={t("guardian.reportCards.emptyTitle")} body={t("guardian.reportCards.emptyBody")} />
        ) : null}
      </div>
      {!failure || failure === "error" || failure === "offline" ? (
        <GenerateReport
          t={t}
          options={periodOptions(nowSeconds(), { t, locale })}
          choice={choice}
          onChoice={(next) => {
            setChoice(next);
            setProblems({});
          }}
          custom={custom}
          onCustom={setCustom}
          problems={problems}
          maxDate={localDateInput(nowSeconds())}
          busy={busy}
          message={message}
          onSubmit={(e) => void generate(e)}
        />
      ) : null}
      {items.length > 0 ? (
        <ReportCardList
          items={items}
          hrefFor={(id) => `${base}/${encodeURIComponent(id)}`}
          label={t("guardian.reportCards.listLabel")}
          newestLabel={t("guardian.reportCards.newest")}
          supersededLabel={t("guardian.reportCards.superseded")}
          seenLabels={[t("guardian.reportCards.seen"), t("guardian.reportCards.notSeen")]}
          unverifiedLabel={t("common.reportCard.listUnverified")}
        />
      ) : null}
    </GuardianShell>
  );
}

export default function GuardedGuardianReportCardsPage() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <GuardianReportCardsPage />
    </RequireSession>
  );
}
