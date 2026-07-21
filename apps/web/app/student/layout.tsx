// Student route group. Governance-safe: synthetic pseudonymous learner, dev-stub auth, no child data.
// Child-facing production (real identity/auth, safeguarding, live data) is blocked by the Phase-1.5 gate.
import type { ReactNode } from "react";

export default function StudentLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
