// Teacher route group.
//
// Deliberately NOT guarded here: /teacher/signin lives inside this tree and must stay reachable
// when signed out. The pages that need a teacher session guard themselves (RequireSession).
import type { ReactNode } from "react";

export default function TeacherLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
