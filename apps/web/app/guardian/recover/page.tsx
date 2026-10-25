"use client";
// Forgot password: a guardian sets a new one with a recovery code they saved at registration. No
// email is involved (delivery is not available), and none is needed: the code is the proof.
//
// On success the server has signed every other device out and issued a new session; this screen
// says so, says how many codes are left, and nudges a guardian who is running low to make new ones.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthShell, FormNotice } from "@/components/form";
import { RecoverPassphraseForm, type RecoverValues } from "@/components/guardian/RecoverPassphraseForm";
import { Button } from "@/design-system/Button";
import { identityErrorKey } from "@/lib/guardian/errors";
import { RECOVERY_LOW_AT } from "@/lib/guardian/recovery";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { publicIdentityApi } from "@/lib/session/identityApi";
import { sessionStore } from "@/lib/session/store";

import { LanguagePicker } from "../LanguagePicker";

export default function GuardianRecoverPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);

  async function recover(values: RecoverValues) {
    setBusy(true);
    setError(null);
    try {
      const envelope = await publicIdentityApi.recoverGuardian(values);
      sessionStore.adopt(envelope);
      setRemaining(envelope.recovery?.remaining ?? 0);
    } catch (e) {
      setError(identityErrorKey(e, "recover"));
    } finally {
      setBusy(false);
    }
  }

  if (remaining !== null) {
    return (
      <AuthShell title={t("auth.recover.title")}>
        <div aria-live="polite" style={{ display: "grid", gap: "var(--space-3)" }}>
          <FormNotice message={t("auth.recover.afterNote")} />
          <p style={{ margin: 0 }}>
            {remaining <= RECOVERY_LOW_AT
              ? t("auth.recover.remainingLow", { count: remaining })
              : t("auth.recover.remaining", { count: remaining })}
          </p>
        </div>
        <div>
          <Button
            type="button"
            variant="brand"
            label={t("auth.recover.continue")}
            onClick={() => router.replace(remaining <= RECOVERY_LOW_AT ? "/guardian/family#recovery" : "/guardian/family")}
          />
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={t("auth.recover.title")}
      subtitle={t("auth.recover.subtitle")}
      footer={
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("auth.recover.noCodes")}</p>
          <p style={{ margin: 0 }}>
            <Link href="/guardian/signin" style={{ color: "var(--color-action-primary)" }}>
              {t("auth.recover.back")}
            </Link>
          </p>
          <LanguagePicker />
        </div>
      }
    >
      <RecoverPassphraseForm t={t} busy={busy} error={error} onSubmit={(v) => void recover(v)} />
    </AuthShell>
  );
}
