"use client";
// React binding for the studio staff session. "loading" until mounted (sessionStorage does not
// exist during the server render), so a signed-in reviewer never sees the sign-in form flash.
import { useEffect, useState } from "react";

import { studioSession, type StudioActor } from "./session";

export type StudioActorState =
  | { status: "loading" }
  | { status: "signed-out" }
  | { status: "signed-in"; actor: StudioActor };

export function useStudioActor(): StudioActorState {
  const [state, setState] = useState<StudioActorState>({ status: "loading" });
  useEffect(() => {
    const apply = (actor: StudioActor | null) =>
      setState(actor ? { status: "signed-in", actor } : { status: "signed-out" });
    apply(studioSession.actor());
    return studioSession.subscribe(apply);
  }, []);
  return state;
}
