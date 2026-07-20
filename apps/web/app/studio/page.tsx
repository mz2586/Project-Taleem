// Curriculum Studio home — the authoring console (server component renders the client shell).
import { StudioConsole } from "./StudioConsole";

export default function StudioPage() {
  return (
    <main style={{ maxWidth: 900 }}>
      <p style={{ color: "var(--color-text-primary)" }}>
        Author original, NCP-aligned lessons. Draft → validate → 5-gate review → publish (immutable
        version). Never copy copyrighted textbooks — provenance is enforced server-side.
      </p>
      <StudioConsole />
    </main>
  );
}
