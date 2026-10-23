"use client";
// React binding for the session store.
//
// `status` is three-valued rather than a boolean because the difference matters to what the screen
// renders: "loading" is the moment before localStorage has been read (server render and first
// paint), and showing a sign-in prompt then would flash it at an already-signed-in child.

import { useCallback, useEffect, useState } from "react";

import { sessionStore, type StoredSession } from "./store";
import type { Role } from "./types";

export type SessionStatus = "loading" | "signed-in" | "signed-out";

export interface SessionHandle {
  status: SessionStatus;
  session: StoredSession | null;
  signOut: () => Promise<void>;
}

// Set once the first useSession has mounted, i.e. once the page has hydrated. A component that
// mounts after that (every page under a RequireSession guard, which renders its children only once
// signed in) is client-only, so it may read the store during its first render. Without this, such a
// page saw an empty session on its first render and its mount effects ran with an empty learner
// ref — the browser journey caught /student/session starting a session for student_ref "" (403).
let hydrated = false;

export function useSession(expectedRole?: Role): SessionHandle {
  const [session, setSession] = useState<StoredSession | null>(() =>
    hydrated ? sessionStore.peek() : null,
  );
  const [status, setStatus] = useState<SessionStatus>(() =>
    hydrated ? (sessionStore.peek() ? "signed-in" : "signed-out") : "loading",
  );

  useEffect(() => {
    hydrated = true;
    // Reading localStorage has to happen after mount for the first (hydrating) render: it does not
    // exist during the server render, and reading it then would desynchronise the two.
    const initial = sessionStore.peek();
    setSession(initial);
    setStatus(initial ? "signed-in" : "signed-out");
    return sessionStore.subscribe((next) => {
      setSession(next);
      setStatus(next ? "signed-in" : "signed-out");
    });
  }, []);

  const signOut = useCallback(async () => {
    await sessionStore.signOut();
  }, []);

  // A guardian token on a student screen is not a session for that screen. Treating it as signed
  // out sends the person to the right sign-in rather than showing them an endless 403.
  if (expectedRole && session && session.role !== expectedRole) {
    return { status: "signed-out", session: null, signOut };
  }
  return { status, session, signOut };
}
