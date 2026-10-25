"use client";
// My record (PROGRESSION_AND_EXAMINATION_CONTRACT §3): grade, units, every unit-check sitting with the
// best result, lessons mastered and links to report cards — all derived by the server from stored
// sittings and evidence, nothing typed in. Read live; offline says the record needs the internet.
import { useCallback, useEffect, useMemo, useState } from "react";

import { RecordSections } from "@/components/progression/RecordSections";
import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { recordApi } from "@/lib/progression/api";
import { LEARNER_RECORD_LINKS, recordView } from "@/lib/progression/view";
import { academicRecord, type AcademicRecord } from "@/lib/progression/wire";
import { useLearner } from "@/lib/session/useLearner";
import { classifyLoadError, INSTRUCTION_LOCALE_PREFERENCE, type LoadFailure as Failure } from "@/lib/student/journey";

export default function MyRecordPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, locale, formatPercent } = useLocale();
  const [record, setRecord] = useState<AcademicRecord | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");

  const preference = useMemo(() => [locale, ...INSTRUCTION_LOCALE_PREFERENCE], [locale]);

  const load = useCallback(async () => {
    if (!ref) return;
    setStatus("loading");
    try {
      setRecord(academicRecord(await recordApi.learner(ref), preference));
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref, preference]);

  useEffect(() => {
    void load();
  }, [load]);

  const view = useMemo(
    () => (record ? recordView(record, { t, locale, formatPercent }, LEARNER_RECORD_LINKS) : null),
    [record, t, locale, formatPercent],
  );

  return (
    <AppShell title={t("progression.record.title")} band={band}>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={5} label={t("progression.record.loading")} /> : null}
        {status !== "loading" && status !== "ready" ? (
          <LoadFailure
            failure={status}
            offlineTitle="progression.record.offlineTitle"
            offlineBody="progression.record.offlineBody"
            errorMessage="progression.record.error"
            onRetry={() => void load()}
          />
        ) : null}
      </div>
      {status === "ready" && view ? <RecordSections view={view} t={t} /> : null}
      <div>
        <ButtonLink href="/student/subjects" variant="ghost" label={t("progression.check.backToLearn")} />
      </div>
    </AppShell>
  );
}
