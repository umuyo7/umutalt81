const CACHE = 'bereket-pos-static-v2';
const STATIC = ['./static/app.css', './static/pos.js', './static/manifest.webmanifest'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => {
  const request = event.request;
  const path = new URL(request.url).pathname;
  // Oturum ve finansal HTML sayfaları hiçbir zaman service-worker cache'ine yazılmaz.
  if (request.method !== 'GET' || !path.includes('/static/')) return;
  event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {
    const copy = response.clone();
    caches.open(CACHE).then(cache => cache.put(request, copy));
    return response;
  })));
});
