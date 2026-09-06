// Guardian route group.
//
// Deliberately NOT guarded here: /guardian/signin lives inside this tree and must stay reachable to
// a signed-out adult. The pages that need a session guard themselves.
import type { ReactNode } from "react";

export default function GuardianLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
