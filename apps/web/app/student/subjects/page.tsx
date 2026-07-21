"use client";
// Subjects (Learn) — browse subjects & topics. Scaffolded here; the full subject browser depends on
// the eligibility + curriculum-read endpoints (STUDENT_API_REQUIREMENTS §2.4/§2.6, not yet built).
import { AppShell } from "@/components/student/AppShell";
import { EmptyState } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import Link from "next/link";
import { DEV_LEARNER } from "@/lib/student/config";

export default function SubjectsPage() {
  return (
    <AppShell title="Learn" band={DEV_LEARNER.grade_band}>
      <EmptyState
        title="Guided learning is the best way to start"
        body="Tap Start on Today and your AI teacher will pick the right next lesson. Browsing subjects arrives with the next milestone."
        action={
          <Link href="/student/today" style={{ textDecoration: "none" }}>
            <Button variant="brand" label="Go to Today" />
          </Link>
        }
      />
    </AppShell>
  );
}
