"use client";
// Student route group.
//
// Every screen under /student needs a signed-in learner, so the guard lives here rather than being
// repeated in each page. It is a usability guard: the server re-derives the actor from the verified
// token on every request and is the actual boundary. What this does is send a signed-out child to
// the sign-in screen instead of showing them a page full of errors.
import type { ReactNode } from "react";

import { RequireSession } from "@/components/RequireSession";

export default function StudentLayout({ children }: { children: ReactNode }) {
  return (
    <RequireSession role="student" signInPath="/signin">
      {children}
    </RequireSession>
  );
}
