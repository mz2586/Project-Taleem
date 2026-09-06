"use client";
// Route guard. Renders its children only for a signed-in session of the expected role.
//
// This is a *usability* guard, not a security boundary — the security boundary is the server, which
// re-derives the actor from the verified token on every request and never trusts a ref from a body.
// What this does is send someone to the right sign-in screen instead of showing them a wall of 403s.
//
// The redirect waits for `status` to leave "loading". Reading localStorage cannot happen during the
// server render, so a guard that redirected on first paint would bounce an already-signed-in child
// straight back to sign-in.

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect } from "react";

import { useSession } from "@/lib/session/useSession";
import type { Role } from "@/lib/session/types";

export function RequireSession({
  role,
  signInPath,
  children,
}: {
  role: Role;
  signInPath: string;
  children: ReactNode;
}) {
  const router = useRouter();
  const { status } = useSession(role);

  useEffect(() => {
    if (status === "signed-out") router.replace(signInPath);
  }, [status, router, signInPath]);

  if (status !== "signed-in") {
    return (
      <main
        aria-busy="true"
        aria-live="polite"
        style={{ padding: "var(--space-6)", textAlign: "center" }}
      >
        <p>…</p>
      </main>
    );
  }
  return <>{children}</>;
}
