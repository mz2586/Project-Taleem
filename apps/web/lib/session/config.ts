// Where the API lives. One definition, imported by every client — the student and guardian configs
// re-export it so existing imports keep working.
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
