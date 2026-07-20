/*
 * Service worker (offline shell scaffold) — docs/33-offline-architecture.md §3.
 * App-shell cache-first; API GETs network-first with cache fallback. NO generative AI offline
 * (audit AR-C-06). Real offline day-pack + sync queue land in Phase 2. No child data cached here.
 */
const SHELL_CACHE = "taleem-shell-v1";
const SHELL_ASSETS = ["/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return; // never cache writes (sync goes through the queue)
  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).catch(() => cached))
  );
});
