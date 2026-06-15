// Minimal service worker: cache the app shell for offline/installability.
// API calls (cross-origin to Railway) are never cached — always network.
const CACHE = "pf-coach-v1";
const SHELL = [
  "/", "/index.html", "/css/style.css?v=1",
  "/js/config.js?v=1", "/js/api.js?v=1", "/js/ui.js?v=1", "/js/router.js?v=1",
  "/js/views/auth.js?v=1", "/js/views/intake.js?v=1", "/js/views/today.js?v=1",
  "/js/views/plan.js?v=1", "/js/views/session.js?v=1", "/js/views/progress.js?v=1",
  "/js/views/nutrition.js?v=1", "/js/views/more.js?v=1",
  "/manifest.json", "/icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin || e.request.method !== "GET") return; // let API/POST go to network
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).catch(() => caches.match("/index.html")))
  );
});
