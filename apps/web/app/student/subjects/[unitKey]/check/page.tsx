"use client";
// A unit check (PROGRESSION_AND_EXAMINATION_CONTRACT §2): "Taleem unit check — not a certificate".
//
// - Start → one question at a time ("Question n of N"), every kind answered through the same
//   interaction components as lessons, no per-question right/wrong — the result comes at the end.
// - Resumable: the sitting id is kept in session storage (guarded; the check works without it) and
//   the server may also report the open sitting, so a reload carries on where the child stopped.
//   A sitting that ran out is "not finished", never failed.
// - Online only: offline, the screen says plainly that a check needs the internet and that saved
//   answers are safe; nothing is queued or claimed as sent.
// - Finish → score, passed / "not yet", the per-idea breakdown, ideas to practise, and the retake rule.
// The rules are pure and unit-tested in lib/progression/{wire,view,sitting}.ts.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CheckQuestion } from "@/components/progression/CheckQuestion";
import { CheckResultPanel } from "@/components/progression/CheckResultPanel";
import { ClaimLine, LocalText, Notice } from "@/components/progression/parts";
import { AppShell } from "@/components/student/AppShell";
import { ErrorBanner, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { watchConnectivity } from "@/lib/offline";
import { checkAnswerBody, pathApi, unitCheckApi } from "@/lib/progression/api";
import { browserSessionStore, forgetSitting, readStoredSitting, rememberSitting, resumePlan } from "@/lib/progression/sitting";
import {
  checkFailure,
  checkOfflineMessage,
  pct,
  questionOf,
  resultView,
  retakeRule,
  titleOr,
  type CheckFailure,
} from "@/lib/progression/view";
import { afterAnswer, checkResult, findUnit, pathView, sittingView, type CheckResult, type SittingView, type UnitView } from "@/lib/progression/wire";
import { useLearner } from "@/lib/session/useLearner";
import { INSTRUCTION_LOCALE_PREFERENCE } from "@/lib/student/journey";
import type { AnswerBody } from "@/lib/student/itemAnswer";

type Phase =
  | { kind: "loading" }
  | { kind: "intro"; expired?: boolean }
  | { kind: "sitting"; sitting: SittingView; resumed: boolean }
  | { kind: "result"; result: CheckResult }
  | { kind: "blocked"; failure: CheckFailure };

const nowSeconds = () => Math.floor(Date.now() / 1000);

export default function UnitCheckPage() {
  const params = useParams<{ unitKey: string }>();
  const unitKey = decodeURIComponent(String(params.unitKey));
  const { studentRef: ref, band } = useLearner();
  const { t, locale, formatNumber, formatPercent } = useLocale();
  const [online, setOnline] = useState(true);
  const [unit, setUnit] = useState<UnitView | null>(null);
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => watchConnectivity(setOnline), []);

  const preference = useMemo(() => [locale, ...INSTRUCTION_LOCALE_PREFERENCE], [locale]);
  const ctx = useMemo(() => ({ t, locale, formatPercent }), [t, locale, formatPercent]);

  const open = useCallback(async () => {
    if (!ref) return;
    setPhase({ kind: "loading" });
    setError(null);
    const store = browserSessionStore();
    try {
      const found = findUnit(pathView(await pathApi.path(ref), preference), unitKey);
      setUnit(found);
      const plan = resumePlan(readStoredSitting(store, ref, unitKey), found?.check.openSittingId ?? null, nowSeconds());
      if (plan.kind === "expired") {
        forgetSitting(store, ref, unitKey);
        setPhase({ kind: "intro", expired: true });
        return;
      }
      if (plan.kind === "resume") {
        try {
          const sitting = sittingView(await unitCheckApi.sitting(ref, unitKey, plan.sittingId), unitKey, preference);
          if (sitting.state === "open" && (sitting.expiresAt === null || sitting.expiresAt > nowSeconds())) {
            rememberSitting(store, ref, unitKey, { sittingId: sitting.sittingId, expiresAt: sitting.expiresAt });
            setPhase({ kind: "sitting", sitting, resumed: true });
            return;
          }
          forgetSitting(store, ref, unitKey);
          setPhase({ kind: "intro", expired: sitting.state === "incomplete" || sitting.state === "open" });
          return;
        } catch (e) {
          const failure = checkFailure(e);
          if (failure === "offline" || failure === "signed-out") throw e;
          forgetSitting(store, ref, unitKey);
          setPhase({ kind: "intro", expired: failure === "expired" });
          return;
        }
      }
      setPhase(found && found.check.available ? { kind: "intro" } : { kind: "blocked", failure: "not_available" });
    } catch (e) {
      setPhase({ kind: "blocked", failure: checkFailure(e) });
    }
  }, [ref, unitKey, preference]);

  useEffect(() => {
    void open();
  }, [open]);

  const focusHeading = () => requestAnimationFrame(() => headingRef.current?.focus());

  async function start() {
    if (!online || busy) return;
    setBusy(true);
    setError(null);
    try {
      const sitting = sittingView(await unitCheckApi.start(ref, unitKey), unitKey, preference);
      rememberSitting(browserSessionStore(), ref, unitKey, { sittingId: sitting.sittingId, expiresAt: sitting.expiresAt });
      setPhase({ kind: "sitting", sitting, resumed: false });
      focusHeading();
    } catch (e) {
      const failure = checkFailure(e);
      if (failure === "retake_not_yet" || failure === "not_available") setPhase({ kind: "blocked", failure });
      else setError(t(failure === "offline" ? "progression.check.offlineBodyStart" : "progression.check.startError"));
    } finally {
      setBusy(false);
    }
  }

  async function answer(sitting: SittingView, body: AnswerBody) {
    if (!online || busy || !sitting.item) return;
    setBusy(true);
    setError(null);
    try {
      // §2: an item is answered once per sitting and a repeat is idempotent, so a retry after a
      // dropped connection is safe.
      const wire = await unitCheckApi.answer(ref, unitKey, sitting.sittingId, checkAnswerBody(sitting.item.item_ref, body));
      setPhase({ kind: "sitting", sitting: afterAnswer(sitting, wire, preference), resumed: false });
      focusHeading();
    } catch (e) {
      const failure = checkFailure(e);
      if (failure === "expired") {
        forgetSitting(browserSessionStore(), ref, unitKey);
        setPhase({ kind: "intro", expired: true });
      } else setError(t("progression.check.answerError"));
    } finally {
      setBusy(false);
    }
  }

  async function finish(sitting: SittingView) {
    if (!online || busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = checkResult(await unitCheckApi.finish(ref, unitKey, sitting.sittingId), preference);
      forgetSitting(browserSessionStore(), ref, unitKey);
      setPhase({ kind: "result", result });
      focusHeading();
    } catch (e) {
      const failure = checkFailure(e);
      if (failure === "expired") {
        forgetSitting(browserSessionStore(), ref, unitKey);
        setPhase({ kind: "intro", expired: true });
      } else setError(t("progression.check.finishError"));
    } finally {
      setBusy(false);
    }
  }

  const unitTitle = unit ? titleOr(unit.title, t("progression.path.untitledUnit")) : null;
  const inSitting = phase.kind === "sitting";
  const offline = checkOfflineMessage(inSitting, t);

  return (
    <AppShell title={t("progression.check.title")} band={band}>
      <div style={{ display: "grid", gap: "var(--space-4)", minWidth: 0 }}>
        <header style={{ display: "grid", gap: "var(--space-1)" }}>
          <h2 ref={headingRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            {unitTitle ? <LocalText value={unitTitle} /> : t("progression.check.title")}
          </h2>
          <ClaimLine text={t("progression.check.claim")} />
        </header>

        {!online && phase.kind !== "result" ? (
          <div data-offline="" style={{ display: "grid", gap: "var(--space-1)" }}>
            <Notice>
              <strong>{offline.title}</strong> {offline.body}
            </Notice>
          </div>
        ) : null}

        {error ? <ErrorBanner message={error} /> : null}

        {phase.kind === "loading" ? <Skeleton lines={4} label={t("progression.check.loading")} /> : null}

        {phase.kind === "blocked" ? (
          <section style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
            <p style={{ margin: 0 }}>
              {phase.failure === "retake_not_yet" && unit
                ? retakeRule(unit.check, ctx)
                : phase.failure === "retake_not_yet"
                  ? t("progression.check.retakeRule")
                  : phase.failure === "not_available" || phase.failure === "gone"
                    ? t("progression.check.notAvailable")
                    : phase.failure === "offline"
                      ? offline.body
                      : phase.failure === "signed-out"
                        ? t("common.signedOut")
                        : t("progression.check.startError")}
            </p>
            {phase.failure === "offline" || phase.failure === "error" ? (
              <Button variant="ghost" label={t("common.tryAgain")} onClick={() => void open()} />
            ) : null}
            {phase.failure === "signed-out" ? <ButtonLink href="/signin" variant="brand" label={t("common.signInAgain")} /> : null}
          </section>
        ) : null}

        {phase.kind === "intro" ? (
          <section style={{ display: "grid", gap: "var(--space-3)", justifyItems: "start" }}>
            {phase.expired ? (
              <Notice>
                <strong>{t("progression.check.expiredTitle")}</strong> {t("progression.check.expiredBody")}
              </Notice>
            ) : null}
            <p style={{ margin: 0 }}>
              {unit?.check.itemCount
                ? t("progression.check.intro", { count: unit.check.itemCount })
                : t("progression.check.introNoCount")}
            </p>
            <p style={{ margin: 0 }}>{t("progression.check.passMarkNote", { mark: pct(ctx, unit?.check.passMark ?? 70) })}</p>
            <p style={{ margin: 0 }}>{t("progression.check.noFeedbackNote")}</p>
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("progression.check.onlineOnly")}</p>
            <Button
              variant="brand"
              label={t("progression.check.start")}
              icon={<span aria-hidden="true">▶</span>}
              loading={busy}
              disabled={!online}
              onClick={() => void start()}
            />
          </section>
        ) : null}

        {phase.kind === "sitting" ? (
          <div aria-live="polite" style={{ display: "grid", gap: "var(--space-3)", minWidth: 0 }}>
            {phase.resumed ? <Notice>{t("progression.check.resumeNote")}</Notice> : null}
            {phase.sitting.item ? (
              <CheckQuestion
                key={phase.sitting.item.item_ref}
                item={phase.sitting.item}
                t={t}
                formatNumber={(n) => formatNumber(n)}
                progress={questionOf(phase.sitting.answered, phase.sitting.total, t)}
                disabled={busy || !online}
                onAnswer={(body) => void answer(phase.sitting, body)}
              />
            ) : (
              <section style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
                <p style={{ margin: 0 }}>{t("progression.check.allAnswered", { total: phase.sitting.total || phase.sitting.answered })}</p>
                <Button
                  variant="brand"
                  label={t("progression.check.finish")}
                  loading={busy}
                  disabled={!online}
                  onClick={() => void finish(phase.sitting)}
                />
              </section>
            )}
          </div>
        ) : null}

        {phase.kind === "result" ? <CheckResultPanel view={resultView(phase.result, ctx)} t={t} /> : null}

        {phase.kind !== "result" ? (
          <div>
            <ButtonLink href="/student/subjects" variant="ghost" label={t("progression.check.backToLearn")} />
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
