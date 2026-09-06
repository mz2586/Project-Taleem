"use client";
// The signed-in learner, for student screens.
//
// Every student page used to read a synthetic learner constant compiled into the bundle. They now
// read this, which returns the learner the server issued a token for — so a screen physically
// cannot render a ref the signed-in child does not own.

import { useSession } from "./useSession";
import type { GradeBand, Learner } from "./types";

export interface LearnerHandle {
  status: "loading" | "signed-in" | "signed-out";
  learner: Learner | null;
  studentRef: string;
  band: GradeBand;
  displayName: string;
}

export function useLearner(): LearnerHandle {
  const { status, session } = useSession("student");
  const learner = session?.learner ?? null;
  return {
    status,
    learner,
    // The token's subject is the authority on which learner this is; `learner` is the cached
    // profile that came with it and may be absent if storage was trimmed.
    studentRef: session?.subject ?? "",
    band: learner?.grade_band ?? "middle",
    displayName: learner?.display_name ?? "",
  };
}
