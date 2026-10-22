"use client";
// "Join a class" for one child. Entering a teacher's class code is the guardian's consent act: the
// server records the `progress_sharing` scope for this child, storing the sentence the guardian
// ticked verbatim. The copy says what is shared, with whom, and how to stop (untick that scope in
// the consent form above). Rules: lib/teacher/join.ts and lib/teacher/errors.ts, unit-tested.
import { useId, useState } from "react";

import { FormError, FormNotice, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { familyApi } from "@/lib/guardian/api";
import { scopeCopy } from "@/lib/guardian/consent";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import type { Learner } from "@/lib/session/types";
import { joinClassErrorKey } from "@/lib/teacher/errors";
import { joinAvailability, normaliseClassCode, sharesProgress } from "@/lib/teacher/join";

export function JoinClassForm({ learner, onJoined }: { learner: Learner; onJoined: () => Promise<void> }) {
  const { t } = useLocale();
  const agreeId = useId();
  const name = learner.display_name;
  const [code, setCode] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [fieldError, setFieldError] = useState<MessageKey | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const available = joinAvailability(learner) === "ready";
  const attestation = t("teacher.guardianJoin.agree", { name });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice("");
    const classCode = normaliseClassCode(code);
    setFieldError(classCode ? null : "teacher.guardianJoin.codeInvalid");
    if (!classCode) return;
    if (!agreed) {
      setError("teacher.guardianJoin.agreeRequired");
      return;
    }
    setBusy(true);
    try {
      const result = await familyApi.joinClass({ classCode, studentRef: learner.student_ref, attestation });
      setCode("");
      setAgreed(false);
      setNotice(t("teacher.guardianJoin.done", { name, className: result.class_name }));
      await onJoined();
    } catch (e) {
      setError(joinClassErrorKey(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details>
      <summary style={{ minHeight: "var(--size-touch-min)", display: "flex", alignItems: "center", cursor: "pointer" }}>
        {t("teacher.guardianJoin.title")}
      </summary>
      <div style={{ display: "grid", gap: "var(--space-2)", paddingTop: "var(--space-2)" }}>
        <p style={{ margin: 0 }}>{t("teacher.guardianJoin.intro", { name })}</p>
        <p style={{ margin: 0 }}>{t("teacher.guardianJoin.sharing", { name })}</p>
        <p style={{ margin: 0 }}>
          {t("teacher.guardianJoin.stop", { name, scope: t(scopeCopy("progress_sharing").title) })}
        </p>
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("teacher.guardianJoin.note", { name })}</p>
        {sharesProgress(learner) ? (
          <p style={{ margin: 0, fontWeight: 700 }}>{t("teacher.guardianJoin.sharingNow", { name })}</p>
        ) : null}
        <div aria-live="polite" style={{ display: "grid", gap: "var(--space-2)" }}>
          {error ? <FormError message={t(error)} /> : null}
          {notice ? <FormNotice message={notice} /> : null}
        </div>
        {available ? (
          <form onSubmit={submit} noValidate style={{ display: "grid", gap: "var(--space-3)" }}>
            <TextField
              id={`join-code-${learner.student_ref}`}
              label={t("teacher.guardianJoin.codeLabel")}
              hint={t("teacher.guardianJoin.codeHint")}
              error={fieldError ? t(fieldError) : undefined}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              dir="ltr"
              lang="en"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={16}
              required
            />
            <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "start" }}>
              <input
                id={agreeId}
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                style={{ width: 28, height: 28, marginTop: 2, flexShrink: 0 }}
              />
              <label htmlFor={agreeId}>{attestation}</label>
            </div>
            <div>
              <Button type="submit" variant="brand" label={t("teacher.guardianJoin.submit")} loading={busy} />
            </div>
          </form>
        ) : (
          <p style={{ margin: 0 }}>{t("teacher.guardianJoin.needsLearningConsent", { name })}</p>
        )}
      </div>
    </details>
  );
}
