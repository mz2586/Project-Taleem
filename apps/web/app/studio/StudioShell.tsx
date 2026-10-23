"use client";
// Curriculum Studio chrome: interface-locale direction, the signed-in staff identity, and the
// staff sign-in gate (operator-provisioned accounts via /v1/identity/staff:signin). Every studio page renders inside it and reads the actor from context.
import { createContext, useContext, type ReactNode } from "react";

import { Button } from "@/design-system/Button";
import { useLocale } from "@/lib/i18n/useLocale";
import { type StudioActor } from "@/lib/studio/session";
import { signOutStaff } from "@/lib/studio/sessionSignIn";
import { useStudioActor } from "@/lib/studio/useStudioActor";

import { StaffSignInForm } from "./signin/StaffSignInForm";

const ActorContext = createContext<StudioActor | null>(null);

/** The signed-in staff member. Only valid inside StudioShell's signed-in branch. */
export function useActor(): StudioActor {
  const actor = useContext(ActorContext);
  if (!actor) throw new Error("useActor outside a signed-in StudioShell");
  return actor;
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
            <Button variant="ghost" label={t("studio.signIn.signOut")} onClick={() => void signOutStaff()} />
          </div>
        ) : null}
      </header>
      <div id="studio-main" tabIndex={-1}>
        {session.status === "loading" ? (
          <p role="status" aria-busy="true">
            {t("common.loading")}
          </p>
        ) : session.status === "signed-out" ? (
          <StaffSignInForm />
        ) : (
          <ActorContext.Provider value={session.actor}>{children}</ActorContext.Provider>
        )}
      </div>
    </div>
  );
}

