"use client";
// Curriculum Studio chrome: interface-locale direction, the signed-in staff identity, and the
// sign-in gate. Every studio page renders inside it and reads the actor from context.
import { createContext, useContext, useId, useState, type FormEvent, type ReactNode } from "react";

import { TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { studioSession, type StudioActor } from "@/lib/studio/session";
import { useStudioActor } from "@/lib/studio/useStudioActor";

const ActorContext = createContext<StudioActor | null>(null);

/** The signed-in staff member. Only valid inside StudioShell's signed-in branch. */
export function useActor(): StudioActor {
  const actor = useContext(ActorContext);
  if (!actor) throw new Error("useActor outside a signed-in StudioShell");
  return actor;
}

const SIGN_IN_ERRORS: Record<"malformed" | "not-studio-role" | "expired", MessageKey> = {
  malformed: "studio.signIn.errors.malformed",
  "not-studio-role": "studio.signIn.errors.notStudioRole",
  expired: "studio.signIn.errors.expired",
};

function SignIn() {
  const { t } = useLocale();
  const id = useId();
  const [token, setToken] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const result = studioSession.signIn(token);
    setError(result.ok ? null : SIGN_IN_ERRORS[result.reason]);
  };
  return (
    <main style={{ maxWidth: 560, display: "grid", gap: "var(--space-4)" }}>
      <h1 style={{ margin: 0 }}>{t("studio.signIn.heading")}</h1>
      <p style={{ margin: 0 }}>{t("studio.signIn.body")}</p>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: "var(--space-3)", justifyItems: "start" }}>
        <TextField
          id={id}
          label={t("studio.signIn.tokenLabel")}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          dir="ltr"
          error={error ? t(error) : undefined}
        />
        <Button type="submit" variant="brand" label={t("studio.signIn.submit")} />
      </form>
    </main>
  );
}

export function StudioShell({ children }: { children: ReactNode }) {
  const { t, dir, locale } = useLocale();
  const session = useStudioActor();

  return (
    <div lang={locale} dir={dir} style={{ padding: "var(--space-6) var(--space-4)", maxWidth: 1100, margin: "0 auto" }}>
      <a href="#studio-main" className="skip-link">
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
          <strong style={{ color: "var(--color-brand)" }}>{t("studio.title")}</strong>
          <span style={{ marginInlineStart: "var(--space-2)" }}>{t("studio.tagline")}</span>
        </p>
        {session.status === "signed-in" ? (
          <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center", flexWrap: "wrap" }}>
            <span>
              {t("studio.signIn.signedInAs", {
                subject: session.actor.subject,
                role: t(`studio.roles.${session.actor.role}`),
              })}
            </span>
            <Button variant="ghost" label={t("studio.signIn.signOut")} onClick={() => studioSession.clear()} />
          </div>
        ) : null}
      </header>
      <div id="studio-main" tabIndex={-1}>
        {session.status === "loading" ? (
          <p role="status" aria-busy="true">
            {t("common.loading")}
          </p>
        ) : session.status === "signed-out" ? (
          <SignIn />
        ) : (
          <ActorContext.Provider value={session.actor}>{children}</ActorContext.Provider>
        )}
      </div>
    </div>
  );
}

