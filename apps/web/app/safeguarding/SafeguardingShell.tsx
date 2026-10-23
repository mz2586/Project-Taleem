"use client";
// Safeguarding console chrome: interface-locale direction, the signed-in lead, the standing
// "not approved or staffed" notice, and the sign-in gate (operator-provisioned staff account with
// role safeguarding_lead, via /v1/identity/staff:signin — the same flow as the Studio).
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { FormError, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { identityErrorKey } from "@/lib/guardian/errors";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { signInLead, signOutLead } from "@/lib/safeguarding/session";
import { useLeadActor } from "@/lib/safeguarding/useLeadActor";

function LeadSignInForm() {
  const { t } = useLocale();
  const emailId = useId();
  const passphraseId = useId();
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await signInLead(email, passphrase);
      if (!result.ok) {
        setError(result.reason === "not-lead" ? "safeguarding.console.notLead" : "auth.errors.generic");
        return;
      }
      setPassphrase("");
    } catch (e) {
      setError(identityErrorKey(e, "guardian-sign-in"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 560, display: "grid", gap: "var(--space-4)" }}>
      <h1 style={{ margin: 0 }}>{t("safeguarding.console.signInHeading")}</h1>
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-3)" }}>
        <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
        <TextField
          id={emailId}
          label={t("auth.guardianSignIn.email")}
          type="email"
          dir="ltr"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
        <TextField
          id={passphraseId}
          label={t("auth.guardianSignIn.passphrase")}
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" variant="brand" label={t("safeguarding.console.signIn")} loading={busy} />
      </form>
    </main>
  );
}

export function SafeguardingShell({ children }: { children: ReactNode }) {
  const { t, dir, locale } = useLocale();
  const session = useLeadActor();

  return (
    <div lang={locale} dir={dir} style={{ padding: "var(--space-6) var(--space-4)", maxWidth: 1100, margin: "0 auto" }}>
      <a href="#safeguarding-main" className="skip-link">
        {t("common.skipToContent")}
      </a>
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-3)",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--color-focus-ring)",
          paddingBottom: "var(--space-3)",
          marginBottom: "var(--space-4)",
        }}
      >
        <p style={{ margin: 0 }}>
          <strong style={{ color: "var(--color-brand)" }}>{t("safeguarding.console.title")}</strong>
          <span style={{ marginInlineStart: "var(--space-2)" }}>{t("safeguarding.console.tagline")}</span>
        </p>
        {session.status === "signed-in" ? (
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
            <span>
              {t("safeguarding.console.signedInAs", { subject: session.actor.subject })}
            </span>
            <Button variant="ghost" label={t("safeguarding.console.signOut")} onClick={() => void signOutLead()} />
          </div>
        ) : null}
      </header>
      <p
        style={{ margin: "0 0 var(--space-4)", padding: "var(--space-3)", border: "1px solid var(--color-focus-ring)", borderRadius: "var(--radius-md)" }}
      >
        {t("safeguarding.console.notApproved")}
      </p>
      <div id="safeguarding-main" tabIndex={-1}>
        {session.status === "loading" ? (
          <p role="status" aria-busy="true">
            {t("common.loading")}
          </p>
        ) : session.status === "signed-out" ? (
          <LeadSignInForm />
        ) : (
          children
        )}
      </div>
    </div>
  );
}
