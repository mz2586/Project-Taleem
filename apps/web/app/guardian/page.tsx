"use client";
// Family dashboard — one card per child: name, whether they can sign in, and a learning summary.
// The states (loading, a new guardian with no children, children without progress yet, one service
// down, both down) come from lib/guardian/dashboard.ts, where they are unit-tested.
import { useCallback, useEffect, useState } from "react";

import { RequireSession } from "@/components/RequireSession";

import { Card, EmptyState, ProgressRing, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { guardianApi, familyApi } from "@/lib/guardian/api";
import { familyDashboardModel, familyNudge, type ChildAccess, type ChildRow, type Request } from "@/lib/guardian/dashboard";
import { formatChildSummary } from "@/lib/guardian/progress";
import type { GuardianDashboard } from "@/lib/guardian/types";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import type { GuardianProfile } from "@/lib/session/types";
import { useSession } from "@/lib/session/useSession";

import { GuardianLoadFailure } from "./GuardianLoadFailure";
import { GuardianShell } from "./GuardianShell";

const ACCESS_KEYS: Record<ChildAccess, MessageKey> = {
  given: "guardian.access.given",
  "not-given": "guardian.access.notGiven",
  "policy-changed": "guardian.access.policyChanged",
  withdrawn: "guardian.access.withdrawn",
  locked: "guardian.access.locked",
  suspended: "guardian.access.suspended",
  unknown: "guardian.access.unknown",
};

function AccessBadge({ access }: { access: ChildAccess }) {
  const { t } = useLocale();
  const ok = access === "given";
  return (
    <span style={{ display: "inline-flex", gap: "var(--space-1)", alignItems: "center", color: ok ? "var(--color-brand)" : "var(--color-danger)" }}>
      {/* Shape as well as colour: filled for "can learn", hollow otherwise. */}
      <span aria-hidden="true">{ok ? "●" : "○"}</span>
      <span>{t(ACCESS_KEYS[access])}</span>
    </span>
  );
}

function ChildCard({ child }: { child: ChildRow }) {
  const { t, locale, formatPercent } = useLocale();
  const name = child.name ?? t("guardian.dashboard.unnamedChild");
  const summary = child.progress.kind === "summary" ? formatChildSummary({ locale }, child.progress.summary) : null;
  const href = `/guardian/children/${encodeURIComponent(child.studentRef)}`;

  return (
    <Card>
      <div style={{ display: "grid", gap: "var(--space-3)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "var(--space-2)" }}>
          <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }} dir="auto">
            {name}
          </h2>
          <AccessBadge access={child.access} />
        </div>

        {summary ? (
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--space-4)" }}>
            <ProgressRing value={summary.masteryRatio} label={t("guardian.dashboard.masteryRing")} formatPercent={formatPercent} />
            <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)", flex: 1 }}>
              <li>{summary.mastered}</li>
              <li>{summary.inProgress}</li>
              {summary.accuracy ? <li>{summary.accuracy}</li> : null}
              <li>{summary.streak}</li>
              {summary.achievements ? <li>{summary.achievements}</li> : null}
              <li>
                <span aria-hidden="true">{summary.syncStale ? "⚠ " : "✓ "}</span>
                {summary.sync}
              </li>
              {summary.attention ? <li style={{ color: "var(--color-danger)" }}>{summary.attention}</li> : null}
            </ul>
          </div>
        ) : null}
        {child.progress.kind === "none-yet" ? <p style={{ margin: 0 }}>{t("guardian.dashboard.childNoProgress")}</p> : null}
        {child.progress.kind === "unavailable" ? (
          <p style={{ margin: 0 }}>{t("guardian.dashboard.childProgressUnavailable")}</p>
        ) : null}

        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          {child.progress.kind === "summary" ? (
            <ButtonLink href={href} variant="primary" label={t("guardian.dashboard.viewProgress")} />
          ) : null}
          {child.access === "not-given" || child.access === "policy-changed" ? (
            <ButtonLink href={`/guardian/family#learner-${child.studentRef}`} variant="brand" label={t("guardian.dashboard.givePermission")} />
          ) : (
            <ButtonLink href={`/guardian/family#learner-${child.studentRef}`} variant="ghost" label={t("guardian.dashboard.manage")} />
          )}
        </div>
      </div>
    </Card>
  );
}

function GuardianDashboardPage() {
  const { session } = useSession("guardian");
  const { t } = useLocale();
  const guardianName = session?.guardian?.display_name ?? "";
  const [identity, setIdentity] = useState<Request<GuardianProfile>>({ status: "pending" });
  const [dashboard, setDashboard] = useState<Request<GuardianDashboard>>({ status: "pending" });

  const load = useCallback(async () => {
    setIdentity({ status: "pending" });
    setDashboard({ status: "pending" });
    const [me, dash] = await Promise.allSettled([familyApi.me(), guardianApi.dashboard()]);
    setIdentity(me.status === "fulfilled" ? { status: "ok", value: me.value } : { status: "error", error: me.reason });
    setDashboard(dash.status === "fulfilled" ? { status: "ok", value: dash.value } : { status: "error", error: dash.reason });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const model = familyDashboardModel({ identity, dashboard });
  const nudge = familyNudge(model);

  return (
    <GuardianShell title={t("guardian.dashboard.title")}>
      <section style={{ display: "grid", gap: "var(--space-1)" }}>
        <h2 style={{ margin: 0 }}>
          {guardianName ? t("guardian.dashboard.greeting", { name: guardianName }) : t("guardian.dashboard.greetingNoName")}
        </h2>
        <p style={{ margin: 0 }}>{t("guardian.dashboard.subtitle")}</p>
      </section>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {model.kind === "loading" ? <Skeleton lines={4} label={t("guardian.dashboard.loading")} /> : null}

        {model.kind === "failed" ? (
          <GuardianLoadFailure
            failure={model.failure}
            offlineTitle="guardian.dashboard.offlineTitle"
            offlineBody="guardian.dashboard.offlineBody"
            errorMessage="guardian.dashboard.error"
            onRetry={() => void load()}
          />
        ) : null}

        {model.kind === "no-children" ? (
          <EmptyState
            title={t("guardian.dashboard.noChildrenTitle")}
            body={t("guardian.dashboard.noChildrenBody")}
            action={<ButtonLink href="/guardian/family#enrol" variant="brand" label={t("guardian.dashboard.addChild")} />}
          />
        ) : null}

        {model.kind === "children" ? (
          <>
            {nudge === "give-permission" ? <p role="status" style={{ margin: 0 }}>{t("guardian.dashboard.nudgePermission")}</p> : null}
            {nudge === "unlock" ? <p role="status" style={{ margin: 0 }}>{t("guardian.dashboard.nudgeUnlock")}</p> : null}
            {model.noProgressYet ? (
              <EmptyState title={t("guardian.dashboard.noProgressTitle")} body={t("guardian.dashboard.noProgressBody")} />
            ) : null}
            {model.progressUnavailable ? <p style={{ margin: 0 }}>{t("guardian.dashboard.progressUnavailable")}</p> : null}
            {model.identityUnavailable ? <p style={{ margin: 0 }}>{t("guardian.dashboard.identityUnavailable")}</p> : null}
            {model.children.map((child) => (
              <ChildCard key={child.studentRef} child={child} />
            ))}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", justifyContent: "space-between" }}>
              <ButtonLink href="/guardian/family#enrol" variant="ghost" label={t("guardian.dashboard.addChild")} />
              <Button variant="ghost" label={t("guardian.dashboard.refresh")} onClick={() => void load()} />
            </div>
          </>
        ) : null}
      </div>
    </GuardianShell>
  );
}

export default function GuardedGuardianDashboard() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <GuardianDashboardPage />
    </RequireSession>
  );
}
