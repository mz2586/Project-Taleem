// The demo cohort, for display only (docs/03-security-privacy/DEMO_COHORT_CONTRACT.md §2).
//
// Access tokens of the designated synthetic demo accounts carry the claim `cohort: "demo"`. The
// web app decodes it (no signature check — this is never a security decision) solely to show a
// small "Demo account" badge. The server never trusts the claim: it reads a reader's cohort from
// the account, and that is what decides which content they see.

export const DEMO_COHORT = "demo";

function base64UrlDecode(segment: string): string | null {
  try {
    const padded = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(segment.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

/** The token's informational `cohort` claim ("" when absent, unreadable or not a JWT). */
export function tokenCohort(accessToken: string | null | undefined): string {
  if (!accessToken) return "";
  const parts = accessToken.split(".");
  if (parts.length !== 3 || !parts[1]) return "";
  const json = base64UrlDecode(parts[1]);
  if (json === null) return "";
  try {
    const payload: unknown = JSON.parse(json);
    if (payload && typeof payload === "object" && "cohort" in payload) {
      const cohort = (payload as { cohort?: unknown }).cohort;
      return typeof cohort === "string" ? cohort : "";
    }
  } catch {
    /* not JSON: no claim */
  }
  return "";
}

/** True when the session's access token says it belongs to a demo account (display only). */
export function isDemoToken(accessToken: string | null | undefined): boolean {
  return tokenCohort(accessToken) === DEMO_COHORT;
}
