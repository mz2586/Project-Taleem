// Walking-skeleton landing page. Demonstrates the design system only — no product features.
import { Button } from "../design-system/Button";
import { ReadAloud } from "../design-system/ReadAloud";

export default function Home() {
  return (
    <main style={{ padding: "var(--space-6)", maxWidth: 360 }}>
      <h1 style={{ color: "var(--color-brand)" }}>تعلیم</h1>
      <p>
        Project Taleem — M1 walking skeleton. Governance-safe scaffolding only.
        <ReadAloud label="Read this aloud" />
      </p>
      <Button variant="primary" label="Start" />
    </main>
  );
}
