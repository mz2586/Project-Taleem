// Where a concern came from: the screen (a route-like token) and, inside a lesson, the lesson id.
//
// Only those two are ever sent. A path that carries anything else — a query string, a learner ref, a
// session id — is reduced to nothing rather than forwarded, matching the server's own rule
// (`clean_screen` in contexts/safeguarding/domain/model.py).

const SCREEN = /^[a-z0-9][a-z0-9/_-]{0,63}$/;
const LESSON = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
// A path segment that looks like an identifier, not a screen name (uuid, long hex, a ref).
const ID_SEGMENT = /^(?:[0-9a-f]{8}-[0-9a-f-]{27,}|[0-9a-f]{16,}|[a-z]{2,4}_[A-Za-z0-9_-]+)$/;

export interface ConcernContext {
  screen: string;
  lessonId: string | null;
}

/** `/student/today` -> `student/today`; anything that is not a plain screen name -> "". */
export function screenFromPath(pathname: string): string {
  const path = pathname.split(/[?#]/)[0] ?? "";
  const token = path.replace(/^\/+|\/+$/g, "").toLowerCase();
  if (!SCREEN.test(token)) return "";
  if (token.split("/").some((segment) => ID_SEGMENT.test(segment))) return "";
  return token;
}

export function cleanLessonId(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const id = raw.trim();
  return LESSON.test(id) ? id : null;
}

/** The "Tell a grown-up" link from a screen (and lesson, when inside one). */
export function helpHref(pathname: string, lessonId?: string | null): string {
  const params = new URLSearchParams();
  const screen = screenFromPath(pathname);
  if (screen && screen !== "student/help") params.set("from", screen);
  const lesson = cleanLessonId(lessonId);
  if (lesson) params.set("lesson", lesson);
  const query = params.toString();
  return query ? `/student/help?${query}` : "/student/help";
}

/** Read the context the help page was opened with (`?from=…&lesson=…`), validated again. */
export function readHelpContext(search: string): ConcernContext {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  return {
    screen: screenFromPath(params.get("from") ?? ""),
    lessonId: cleanLessonId(params.get("lesson")),
  };
}
