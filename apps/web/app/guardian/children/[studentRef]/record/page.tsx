"use client";
// A child's academic record for their guardian (PROGRESSION_AND_EXAMINATION_CONTRACT §3): the same
// record the child sees, read through the guardian route (own child only — the server decides).
// Read live; offline says the record needs the internet rather than showing stale results.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { RecordSections } from "@/components/progression/RecordSections";
import { RequireSession } from "@/components/RequireSession";
import { EmptyState, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { familyApi } from "@/lib/guardian/api";
import { useLocale } from "@/lib/i18n/useLocale";
import { recordApi } from "@/lib/progression/api";
import { guardianRecordLinks, recordView } from "@/lib/progression/view";
import { academicRecord, type AcademicRecord } from "@/lib/progression/wire";
import { classifyLoadError, INSTRUCTION_LOCALE_PREFERENCE, type LoadFailure } from "@/lib/student/journey";
import { ApiError } from "@/lib/student/types";

import { GuardianLoadFailure } from "../../../GuardianLoadFailure";
import { GuardianShell } from "../../../GuardianShell";

type Status = "loading" | "ready" | "denied" | "empty" | LoadFailure;

function GuardianRecordPage() {
  const params = useParams<{ studentRef: string }>();
  const ref = decodeURIComponent(String(params.studentRef));
  const { t, locale, formatPercent } = useLocale();
  const [record, setRecord] = useState<AcademicRecord | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  const preference = useMemo(() => [locale, ...INSTRUCTION_LOCALE_PREFERENCE], [locale]);

  const load = useCallback(async () => {
    setStatus("loading");
    familyApi
      .me()
      .then((me) => setName(me.learners.find((l) => l.student_ref === ref)?.display_name ?? null))
      .catch(() => setName(null));
    try {
      setRecord(academicRecord(await recordApi.guardian(ref), preference));
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setStatus("denied");
      else if (e instanceof ApiError && e.status === 404) setStatus("empty");
      else setStatus(classifyLoadError(e));
    }
  }, [ref, preference]);

  useEffect(() => {
    void load();
  }, [load]);

  const view = useMemo(
    () => (record ? recordView(record, { t, locale, formatPercent }, guardianRecordLinks(ref)) : null),
    [record, t, locale, formatPercent, ref],
  );
  const title = name ? t("progression.record.guardianTitle", { name }) : t("progression.record.guardianTitleUnnamed");

  return (
    <GuardianShell title={title}>
      <div>
        <ButtonLink href={`/guardian/children/${encodeURIComponent(ref)}`} variant="ghost" label={t("progression.record.backToChild")} />
      </div>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={5} label={t("progression.record.loading")} /> : null}
        {status === "denied" ? <EmptyState title={t("progression.record.deniedTitle")} body={t("progression.record.deniedBody")} /> : null}
        {status === "empty" ? <EmptyState title={t("progression.record.emptyTitle")} body={t("progression.record.emptyBody")} /> : null}
        {status === "offline" || status === "signed-out" || status === "error" ? (
          <GuardianLoadFailure
            failure={status}
            offlineTitle="progression.record.offlineTitle"
            offlineBody="progression.record.offlineBody"
            errorMessage="progression.record.error"
            onRetry={() => void load()}
          />
        ) : null}
      </div>
      {status === "ready" && view ? <RecordSections view={view} t={t} /> : null}
      {status === "ready" ? (
        <div>
          <Button variant="ghost" label={t("progression.record.refresh")} onClick={() => void load()} />
        </div>
      ) : null}
    </GuardianShell>
  );
}

export default function GuardedGuardianRecordPage() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <GuardianRecordPage />
    </RequireSession>
  );
}
