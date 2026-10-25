"use client";
// Guardian sign-in.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthShell, FormError, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { identityErrorKey } from "@/lib/guardian/errors";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { publicIdentityApi } from "@/lib/session/identityApi";
import { sessionStore } from "@/lib/session/store";

import { LanguagePicker } from "../LanguagePicker";

export default function GuardianSignInPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const envelope = await publicIdentityApi.signInGuardian({ email, passphrase });
      sessionStore.adopt(envelope);
      router.replace("/guardian");
    } catch (e) {
      setError(identityErrorKey(e, "guardian-sign-in"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title={t("auth.guardianSignIn.title")}
      footer={
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <p style={{ margin: 0 }}>
            <Link href="/guardian/recover" style={{ color: "var(--color-action-primary)" }}>
              {t("auth.guardianSignIn.forgot")}
            </Link>
          </p>
          <p style={{ margin: 0 }}>
            {t("auth.guardianSignIn.noAccount")}{" "}
            <Link href="/join" style={{ color: "var(--color-action-primary)" }}>
              {t("auth.guardianSignIn.createOne")}
            </Link>
          </p>
          <p style={{ margin: 0 }}>
            {t("auth.guardianSignIn.childPrompt")}{" "}
            <Link href="/signin" style={{ color: "var(--color-action-primary)" }}>
              {t("auth.guardianSignIn.childLink")}
            </Link>
          </p>
          <LanguagePicker />
        </div>
      }
    >
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-4)" }}>
        <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
        <TextField
          id="email"
          label={t("auth.guardianSignIn.email")}
          type="email"
          dir="ltr"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <TextField
          id="passphrase"
          label={t("auth.guardianSignIn.passphrase")}
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" variant="brand" label={t("auth.guardianSignIn.submit")} loading={busy} />
      </form>
    </AuthShell>
  );
}
