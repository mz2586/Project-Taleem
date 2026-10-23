"use client";
// React binding for the safeguarding lead session. "loading" until mounted (sessionStorage does not
// exist during the server render), so a signed-in lead never sees the sign-in form flash.
import { useEffect, useState } from "react";

import { leadSession, type LeadActor } from "./session";

export type LeadActorState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "signed-in"; actor: LeadActor };

export function useLeadActor(): LeadActorState {
  const [state, setState] = useState<LeadActorState>({ status: "loading" });
  useEffect(() => {
    const apply = (actor: LeadActor | null) =>
      setState(actor ? { status: "signed-in", actor } : { status: "signed-out" });
    apply(leadSession.actor());
    return leadSession.subscribe(apply);
  }, []);
  return state;
}
