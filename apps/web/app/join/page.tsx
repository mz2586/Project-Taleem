"use client";
// Guardian registration. The first screen an adult meets, and the one that decides whether a family
// ever gets started, so it asks for exactly three things and explains what each is for.
//
// The family code is shown immediately afterwards rather than emailed: this product is used by
// families who may not have reliable email, and the code is what their child needs to sign in.
//
// The account is created in the language the guardian is reading this screen in, so the portal
// stays in that language on their other devices.
//
// Then the recovery codes: the server returns them in the registration response and never again,
// so they are shown here, before the guardian moves on, with copy/print and an "I saved them" tick.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { LanguagePicker } from "@/app/guardian/LanguagePicker";
import { AuthShell, FormError, TextField } from "@/components/form";
import { RecoveryCodesPanel } from "@/components/guardian/RecoveryCodesPanel";
import { Button } from "@/design-system/Button";
import { identityErrorKey } from "@/lib/guardian/errors";
import { formatDateTime } from "@/lib/guardian/format";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { publicIdentityApi } from "@/lib/session/identityApi";
import { sessionStore } from "@/lib/session/store";

export default function JoinPage() {
  const router = useRouter();
  const { t, locale } = useLocale();
  const [codes, setCodes] = useState<{ codes: string[]; email: string; at: number } | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const envelope = await publicIdentityApi.registerGuardian({ email, passphrase, displayName, locale });
      sessionStore.adopt(envelope);
      if (envelope.recovery_codes?.length) {
        setCodes({
          codes: envelope.recovery_codes,
          email: envelope.guardian?.email ?? email,
          at: envelope.recovery?.generated_at ?? Date.now() / 1000,
        });
        setPassphrase("");
      } else {
        router.replace("/guardian/family");
      }
    } catch (e) {
      setError(identityErrorKey(e, "register"));
    } finally {
      setBusy(false);
    }
  }

  if (codes) {
    return (
      <AuthShell title={t("guardian.recovery.title")} subtitle={t("auth.join.codesIntro")}>
        <RecoveryCodesPanel
          codes={codes.codes}
          t={t}
          email={codes.email}
          madeAt={formatDateTime(codes.at, locale)}
          doneLabel={t("guardian.recovery.continue")}
          onDone={() => router.replace("/guardian/family")}
        />
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={t("auth.join.title")}
      subtitle={t("auth.join.subtitle")}
      footer={
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <p style={{ margin: 0 }}>
            {t("auth.join.haveAccount")}{" "}
            <Link href="/guardian/signin" style={{ color: "var(--color-action-primary)" }}>
              {t("auth.join.signIn")}
            </Link>
          </p>
          <LanguagePicker />
        </div>
      }
    >
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-4)" }}>
        <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
        <TextField
          id="display-name"
          label={t("auth.join.name")}
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          autoComplete="name"
          dir="auto"
          maxLength={60}
          required
        />
        <TextField
          id="email"
          label={t("auth.join.email")}
          hint={t("auth.join.emailHint")}
          type="email"
          dir="ltr"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <TextField
          id="passphrase"
          label={t("auth.join.passphrase")}
          hint={t("auth.join.passphraseHint")}
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="new-password"
          minLength={10}
          required
        />
        <Button type="submit" variant="brand" label={t("auth.join.submit")} loading={busy} />
      </form>
    </AuthShell>
  );
}
