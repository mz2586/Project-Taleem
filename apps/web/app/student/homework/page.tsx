"use client";
// Homework — scaffolded. The homework list/submit endpoints (STUDENT_API_REQUIREMENTS §2.7) are not
// yet built; this milestone shows a governance-safe empty state that routes back to guided learning.
import Link from "next/link";

import { AppShell } from "@/components/student/AppShell";
import { EmptyState } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { DEV_LEARNER } from "@/lib/student/config";

export default function HomeworkPage() {
  return (
    <AppShell title="Homework" band={DEV_LEARNER.grade_band}>
      <EmptyState
        title="No homework right now"
        body="When your teacher sets practice, it will appear here. For now, keep learning from Today."
        action={
          <Link href="/student/today" style={{ textDecoration: "none" }}>
            <Button variant="brand" label="Go to Today" />
          </Link>
        }
      />
    </AppShell>
  );
}
