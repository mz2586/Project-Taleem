// Guardian route group. Governance-safe: synthetic guardian, dev-stub auth, read-only aggregates of
// a linked child's existing learning data. Production guardian identity + consent-linked children are
// blocked by the Phase-1.5 (M-Gov) gate.
import type { ReactNode } from "react";

export default function GuardianLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
