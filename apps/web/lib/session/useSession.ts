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

export function useSession(expectedRole?: Role): SessionHandle {
  const [session, setSession] = useState<StoredSession | null>(null);
  const [status, setStatus] = useState<SessionStatus>("loading");

  useEffect(() => {
    // Reading localStorage has to happen after mount: it does not exist during the server render,
    // and reading it in the render body would desynchronise the two.
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
