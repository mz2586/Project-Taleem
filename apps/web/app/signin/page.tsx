"use client";
// Learner sign-in. Two steps, because a child should never face more than one question at a time.
//
// Step 1 asks the guardian's family code — typed once per device, then remembered, so a child does
// not meet it again. Step 2 shows the family's names as large buttons and asks for a PIN.
//
// Why a roster of names rather than a text field: a six-year-old learning to read Urdu cannot
// reliably type their own name, and requiring it would exclude exactly the children this product
// exists for. The disclosure is bounded — the caller must already hold a ~40-bit family code, the
// server rate-limits the lookup, an unknown code returns an empty list indistinguishable from an
// empty family, and only display names come back. The PIN and the consent gate still stand behind it.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AuthShell, FormError, PinField, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { deviceId } from "@/lib/session/device";
import { publicIdentityApi } from "@/lib/session/identityApi";
import { sessionStore } from "@/lib/session/store";
import type { RosterEntry } from "@/lib/session/types";
import { identityErrorKey } from "@/lib/guardian/errors";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { LanguagePicker } from "@/app/guardian/LanguagePicker";

// Remembering the family code is a convenience for the child, not a credential store: it is not a
// secret to the family that owns it, and it alone signs nobody in.
const FAMILY_CODE_KEY = "taleem.familyCode.v1";

function rememberedCode(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(FAMILY_CODE_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberCode(code: string): void {
  try {
    window.localStorage.setItem(FAMILY_CODE_KEY, code);
  } catch {
    /* storage unavailable: the child types the code again next time */
  }
}

export default function SignInPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [step, setStep] = useState<"code" | "who">("code");
  const [familyCode, setFamilyCode] = useState("");
  const [roster, setRoster] = useState<RosterEntry[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  const loadRoster = useCallback(async (code: string) => {
    setBusy(true);
    setError(null);
    try {
      const { learners } = await publicIdentityApi.roster(code);
      if (learners.length === 0) {
        // An unknown code and a family with nobody enrolled are the same answer from the server, so
        // this message covers both without implying which.
        setError("auth.learner.noNames");
        return;
      }
      setRoster(learners);
      rememberCode(code);
      setStep("who");
      if (learners.length === 1) setChosen(learners[0]!.display_name);
    } catch (e) {
      setError(identityErrorKey(e, "roster"));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const saved = rememberedCode();
    if (saved) {
      setFamilyCode(saved);
      void loadRoster(saved);
    }
  }, [loadRoster]);

  async function submitCode(event: React.FormEvent) {
    event.preventDefault();
    await loadRoster(familyCode);
  }

  async function submitPin(event: React.FormEvent) {
    event.preventDefault();
    if (!chosen) return;
    setBusy(true);
    setError(null);
    try {
      const envelope = await publicIdentityApi.signInLearner({
        familyCode,
        displayName: chosen,
        pin,
        deviceId: deviceId(),
      });
      sessionStore.adopt(envelope);
      router.replace("/student/today");
    } catch (e) {
      setError(identityErrorKey(e, "learner-sign-in"));
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  if (step === "code") {
    return (
      <AuthShell
        title={t("auth.learner.codeTitle")}
        subtitle={t("auth.learner.codeSubtitle")}
        footer={
          <p style={{ margin: 0 }}>
            {t("auth.learner.guardianPrompt")}{" "}
            <Link href="/guardian/signin" style={{ color: "var(--color-action-primary)" }}>
              {t("auth.learner.guardianLink")}
            </Link>
          </p>
        }
      >
        <LanguagePicker />
        <form onSubmit={submitCode} style={{ display: "grid", gap: "var(--space-4)" }}>
          <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
          <TextField
            id="family-code"
            label={t("auth.learner.familyCode")}
            hint={t("auth.learner.familyCodeHint")}
            dir="ltr"
            value={familyCode}
            onChange={(e) => setFamilyCode(e.target.value)}
            autoComplete="off"
            autoCapitalize="characters"
            spellCheck={false}
            required
          />
          <Button type="submit" variant="brand" label={t("auth.learner.next")} loading={busy} />
        </form>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={t("auth.learner.whoTitle")}
      subtitle={t("auth.learner.whoSubtitle")}
      footer={
        <Button
          variant="ghost"
          label={t("auth.learner.changeCode")}
          onClick={() => {
            setStep("code");
            setChosen(null);
            setPin("");
            setError(null);
          }}
        />
      }
    >
      <ul
        aria-label={t("auth.learner.rosterLabel")}
        style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}
      >
        {roster.map((entry) => {
          const selected = chosen === entry.display_name;
          return (
            <li key={entry.display_name}>
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => {
                  setChosen(entry.display_name);
                  setPin("");
                  setError(null);
                }}
                style={{
                  width: "100%",
                  minHeight: "var(--size-touch-min)",
                  padding: "var(--space-4)",
                  textAlign: "start",
                  borderRadius: "var(--radius-md)",
                  // Selection is carried by the border weight and a tick, not by colour alone.
                  border: selected
                    ? "3px solid var(--color-brand)"
                    : "1px solid var(--color-focus-ring)",
                  background: "var(--color-bg-canvas)",
                  color: "var(--color-text-primary)",
                  font: "inherit",
                  fontSize: "var(--font-size-body-min-urdu)",
                  cursor: "pointer",
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "var(--space-2)",
                }}
              >
                <bdi>{entry.display_name}</bdi>
                <span aria-hidden="true">{selected ? "✓" : "›"}</span>
              </button>
            </li>
          );
        })}
      </ul>

      {chosen ? (
        <form onSubmit={submitPin} style={{ display: "grid", gap: "var(--space-4)" }}>
          <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
          <PinField
            id="pin"
            label={t("auth.learner.pinLabel", { name: chosen })}
            hint={t("auth.learner.pinHint")}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
            required
          />
          <Button
            type="submit"
            variant="brand"
            label={t("auth.learner.start")}
            loading={busy}
            disabled={pin.length < 4}
          />
        </form>
      ) : null}
    </AuthShell>
  );
}
