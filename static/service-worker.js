// Service Worker غیرفعال شد - هیچ cache انجام نمی‌شود
self.addEventListener('install', function(event) {
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.map(function(cacheName) {
          return caches.delete(cacheName);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(event) {
  // فقط fetch معمولی، بدون cache
  event.respondWith(fetch(event.request));
});
