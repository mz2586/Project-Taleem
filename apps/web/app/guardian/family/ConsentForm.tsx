"use client";
// The consent form for one child. The rules (which scopes, required vs optional, what a change
// sends, and the confirmation step) live in lib/guardian/consent.ts and are unit-tested; this file
// only renders them.
//
// Accessibility, deliberately:
// - one <fieldset>/<legend> per scope group ("needed to learn", "your choice"); every checkbox has a
//   real <label> and its explanation is tied to it with aria-describedby;
// - the required scope is shown ticked and disabled — pretending it is optional would be dishonest;
// - optional scopes start unticked for a child without live consent;
// - each explanation has a Listen button, as the student screens do for instructional text;
// - any withdrawal stops at a confirmation that says what will happen ("your child will be signed
//   out"); focus moves to it, Escape or "No, go back" returns focus to the button that opened it;
// - errors are role="alert", confirmations role="status" (polite).
import { useEffect, useId, useMemo, useReducer, useRef, useState } from "react";

import { ReadAloud } from "@/components/student/ReadAloud";
import { FormError, FormNotice } from "@/components/form";
import { Button } from "@/design-system/Button";
import { familyApi } from "@/lib/guardian/api";
import {
  confirmationCopy,
  consentFlow,
  consentStatusKey,
  consentViewModel,
  doneNotice,
  IDLE,
  planConsentChange,
  planWithdrawAll,
  type ConsentChange,
  type ScopeView,
} from "@/lib/guardian/consent";
import { identityErrorKey } from "@/lib/guardian/errors";
import { useLocale } from "@/lib/i18n/useLocale";
import type { ConsentScope, Learner, PolicyDescriptor } from "@/lib/session/types";

function ScopeRow({
  scope,
  checked,
  disabled,
  onToggle,
  idPrefix,
}: {
  scope: ScopeView;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
  idPrefix: string;
}) {
  const { t } = useLocale();
  const inputId = `${idPrefix}-${scope.key}`;
  const whatId = `${inputId}-what`;
  return (
    <div
      style={{
        display: "grid",
        gap: "var(--space-2)",
        padding: "var(--space-3)",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "start" }}>
        <input
          id={inputId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-describedby={whatId}
          onChange={onToggle}
          style={{ width: 28, height: 28, marginTop: 2, flexShrink: 0 }}
        />
        <label htmlFor={inputId} style={{ display: "grid", gap: "var(--space-1)", flex: 1 }}>
          <strong>
            {t(scope.title)}
            {scope.required ? ` (${t("guardian.consent.requiredTag")})` : ""}
          </strong>
        </label>
      </div>
      <p id={whatId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t(scope.what)}
      </p>
      <div>
        <ReadAloud label={t(scope.title)} />
      </div>
    </div>
  );
}

function Confirmation({
  change,
  childName,
  busy,
  onConfirm,
  onCancel,
}: {
  change: ConsentChange;
  childName: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useLocale();
  const titleId = useId();
  const bodyId = useId();
  const titleRef = useRef<HTMLHeadingElement>(null);
  const copy = confirmationCopy(change);

  useEffect(() => {
    titleRef.current?.focus();
  }, []);

  // Escape backs out, as it would from any dialog. A document listener rather than a handler on the
  // (non-interactive) dialog element, and inert while the request is in flight.
  useEffect(() => {
    if (busy) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <section
      role="alertdialog"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      style={{
        display: "grid",
        gap: "var(--space-3)",
        padding: "var(--space-4)",
        border: "2px solid var(--color-danger)",
        borderRadius: "var(--radius-md)",
      }}
    >
      <h5 id={titleId} ref={titleRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t(copy.title, { name: childName })}
      </h5>
      <div id={bodyId} style={{ display: "grid", gap: "var(--space-2)" }}>
        {copy.scopeLines.length > 0 ? (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
            {copy.scopeLines.map((key) => (
              <li key={key}>{t(key)}</li>
            ))}
          </ul>
        ) : null}
        {copy.lines.map((key) => (
          <p key={key} style={{ margin: 0 }}>
            {t(key)}
          </p>
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        <Button variant="danger" label={t(copy.confirm)} onClick={onConfirm} loading={busy} />
        <Button variant="ghost" label={t("guardian.consent.confirm.cancel")} onClick={onCancel} disabled={busy} />
      </div>
    </section>
  );
}

export function ConsentForm({
  learner,
  policy,
  onChanged,
}: {
  learner: Learner;
  policy: PolicyDescriptor | null;
  onChanged: () => Promise<void>;
}) {
  const { t } = useLocale();
  const idPrefix = useId();
  const vm = useMemo(() => consentViewModel(policy, learner.consent), [policy, learner.consent]);
  const [selected, setSelected] = useState<Set<ConsentScope>>(() => new Set(vm.initialSelection));
  const [flow, dispatch] = useReducer(consentFlow, IDLE);
  const [notice, setNotice] = useState("");
  const returnFocus = useRef<HTMLElement | null>(null);

  // Server state changed (after a save or a reload): start the form from it again.
  useEffect(() => {
    setSelected(new Set(vm.initialSelection));
  }, [vm]);

  // Run the API calls when the flow reaches `submitting`. Withdrawals first: a "no" takes effect
  // before any new "yes".
  useEffect(() => {
    if (flow.phase !== "submitting") return;
    const change = flow.change;
    let cancelled = false;
    void (async () => {
      try {
        const attestation = t("guardian.consent.attestation");
        if (change.withdrawAll) {
          await familyApi.withdrawConsent({ studentRef: learner.student_ref, attestation });
        } else if (change.withdraw) {
          await familyApi.withdrawConsent({ studentRef: learner.student_ref, scopes: change.withdraw, attestation });
        }
        if (change.grant) {
          await familyApi.grantConsent({ studentRef: learner.student_ref, scopes: change.grant, attestation });
        }
        if (cancelled) return;
        dispatch({ type: "succeeded" });
        setNotice(t(doneNotice(change)));
        await onChanged();
      } catch (e) {
        if (!cancelled) dispatch({ type: "failed", error: identityErrorKey(e, "consent") });
      }
    })();
    return () => {
      cancelled = true;
    };
    // `t` changes only with the locale; re-running a submission on a language switch would be wrong.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow]);

  function request(change: ConsentChange, trigger: HTMLElement | null) {
    setNotice(change.kind === "none" ? t("guardian.consent.noChanges") : "");
    returnFocus.current = trigger;
    dispatch({ type: "request", change });
  }

  function cancel() {
    dispatch({ type: "cancel" });
    returnFocus.current?.focus();
  }

  function toggle(scope: ConsentScope) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  }

  const busy = flow.phase === "submitting";
  const locked = busy || flow.phase === "confirming";
  const anyGranted = learner.consent.granted_scopes.length > 0;
  const submitLabel =
    vm.status === "policy-changed"
      ? t("guardian.consent.agreeAgain")
      : vm.permitsSignIn
        ? t("guardian.consent.save")
        : t("guardian.consent.give");

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      <p style={{ margin: 0 }}>
        <strong>{t(consentStatusKey(vm.status))}</strong>
      </p>
      {vm.status === "policy-changed" ? <FormNotice message={t("guardian.consent.policyChanged")} /> : null}
      {vm.unexplained.length > 0 ? <FormError message={t("guardian.consent.unexplained")} /> : null}
      <p style={{ margin: 0 }}>{t("guardian.consent.intro")}</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const submitter = (e.nativeEvent as SubmitEvent).submitter as HTMLElement | null;
          request(planConsentChange(vm, selected), submitter);
        }}
        style={{ display: "grid", gap: "var(--space-3)" }}
      >
        <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
          <legend style={{ fontWeight: 700, marginBottom: "var(--space-2)" }}>{t("guardian.consent.requiredLegend")}</legend>
          {vm.required.map((scope) => (
            <ScopeRow key={scope.key} scope={scope} checked disabled onToggle={() => undefined} idPrefix={idPrefix} />
          ))}
        </fieldset>

        {vm.optional.length > 0 ? (
          <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
            <legend style={{ fontWeight: 700, marginBottom: "var(--space-2)" }}>{t("guardian.consent.optionalLegend")}</legend>
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("guardian.consent.optionalHint")}</p>
            {vm.optional.map((scope) => (
              <ScopeRow
                key={scope.key}
                scope={scope}
                checked={selected.has(scope.key)}
                disabled={locked}
                onToggle={() => toggle(scope.key)}
                idPrefix={idPrefix}
              />
            ))}
          </fieldset>
        ) : null}

        <div style={{ display: "grid", gap: "var(--space-1)" }}>
          <span style={{ fontSize: "var(--font-size-body-min)" }}>{t("guardian.consent.attestationLabel")}</span>
          <p style={{ margin: 0 }}>
            <em>{t("guardian.consent.attestation")}</em>
          </p>
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          <Button type="submit" variant="brand" label={submitLabel} loading={busy} disabled={locked || !vm.canGrant} />
          {anyGranted ? (
            <Button
              type="button"
              variant="danger"
              label={t("guardian.consent.stop")}
              aria-describedby={`${idPrefix}-stop-hint`}
              disabled={locked}
              onClick={(e) => request(planWithdrawAll(vm), e.currentTarget)}
            />
          ) : null}
        </div>
        {anyGranted ? (
          <p id={`${idPrefix}-stop-hint`} style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
            {t("guardian.consent.stopHint")}
          </p>
        ) : null}
      </form>

      {flow.phase === "confirming" || (flow.phase === "submitting" && flow.change.needsConfirmation) ? (
        <Confirmation
          change={flow.change}
          childName={learner.display_name}
          busy={busy}
          onConfirm={() => dispatch({ type: "confirm" })}
          onCancel={cancel}
        />
      ) : null}

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
        {flow.phase === "failed" ? (
          <>
            <FormError message={t(flow.error)} />
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
              <Button variant="ghost" label={t("common.retry")} onClick={() => dispatch({ type: "retry" })} />
              <Button variant="ghost" label={t("guardian.consent.confirm.cancel")} onClick={cancel} />
            </div>
          </>
        ) : null}
        {notice ? <FormNotice message={notice} /> : null}
      </div>
    </div>
  );
}
