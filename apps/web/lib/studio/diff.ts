// Field-by-field diff of two published lesson bodies (GET .../versions/{n}). Pure; unit-tested.
//
// Bodies are flattened to leaf paths ("worked_examples[0].steps[1].text.ur") and compared. Workflow,
// gate and version bookkeeping are excluded: they change on every publish and are not content.

export type Scalar = string | number | boolean | null;

export interface DiffEntry {
  path: string;
  kind: "added" | "removed" | "changed";
  before: Scalar | undefined;
  after: Scalar | undefined;
}

const NOT_CONTENT = new Set(["workflow", "quality_gate_results", "version", "version_history"]);

export function flatten(value: unknown, prefix = "", out = new Map<string, Scalar>()): Map<string, Scalar> {
  if (value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    out.set(prefix, value);
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => flatten(v, `${prefix}[${i}]`, out));
  } else if (typeof value === "object") {
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (!prefix && NOT_CONTENT.has(k)) continue;
      flatten(v, prefix ? `${prefix}.${k}` : k, out);
    }
  }
  return out;
}

export function diffBodies(older: unknown, newer: unknown): DiffEntry[] {
  const a = flatten(older);
  const b = flatten(newer);
  const out: DiffEntry[] = [];
  for (const path of new Set([...a.keys(), ...b.keys()])) {
    const inA = a.has(path);
    const inB = b.has(path);
    const before = a.get(path);
    const after = b.get(path);
    // An empty string and an absent value read the same to a reviewer.
    if ((before ?? "") === (after ?? "")) continue;
    out.push({ path, kind: !inA || before === "" ? "added" : !inB || after === "" ? "removed" : "changed", before, after });
  }
  return out.sort((x, y) => x.path.localeCompare(y.path));
}

/** The locale a leaf belongs to, when its path ends in `.text.<locale>` (for lang/dir on display). */
export function leafLocale(path: string): string | null {
  const m = /\.text\.([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*)$/.exec(path) ?? /^title\.([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*)$/.exec(path);
  return m ? m[1]! : null;
}
