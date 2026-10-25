// Today's "Your ideas" list: one card per objective the learner has met, named by its lesson title.
import { Card, StateBadge } from "@/components/student/ui";
import type { MessageKey } from "@/lib/i18n/messages";
import { masteryStateKey } from "@/lib/student/journey";
import { objectiveName, type ObjectiveTitles } from "@/lib/student/objectiveName";
import type { ObjectiveKnowledge } from "@/lib/student/types";

import { ObjectiveName } from "./ObjectiveName";

export function TodayIdeas({
  objectives,
  titles,
  label,
  t,
}: {
  objectives: [string, ObjectiveKnowledge][];
  titles: ObjectiveTitles;
  label: string;
  t: (key: MessageKey) => string;
}) {
  if (objectives.length === 0) return null;
  return (
    <section aria-label={label} style={{ display: "grid", gap: "var(--space-2)" }}>
      {objectives.slice(0, 8).map(([code, o]) => (
        <Card key={code}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
            <ObjectiveName name={objectiveName(code, titles)} />
            <StateBadge state={o.state} label={t(masteryStateKey(o.state))} />
          </div>
        </Card>
      ))}
    </section>
  );
}
