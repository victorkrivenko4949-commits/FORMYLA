/**
 * Service Worker FORMYLA.net — PWA_INSTALL_V1 (11.10.2026).
 *
 * 1. Web Push (как и раньше): показывает уведомления и открывает нужную страницу.
 * 2. Офлайн/кэш: даёт сайту право на установку как приложения (Chrome на Android
 *    требует fetch-обработчик) и показывает /offline, когда нет сети.
 *
 * Отдаётся по адресу /sw.js (routes/pwa.py) со scope «/».
 * HTML-страницы НЕ кэшируются (сайт персональный, с логином) — только статика.
 * При серьёзных изменениях статики поднимите CACHE_VERSION.
 */
var CACHE_VERSION = 'formyla-v1';
var STATIC_CACHE = CACHE_VERSION + '-static';
var OFFLINE_URL = '/offline';
var PRECACHE = [
  OFFLINE_URL,
  '/static/style.css',
  '/static/css/nav.css',
  '/static/css/mobile.css',
  '/static/logo.png',
  '/static/android-chrome-192x192.png',
  '/static/android-chrome-512x512.png'
];

/* ───────── install / activate ───────── */
self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(function (cache) {
        // allSettled: если какого-то файла нет — остальные всё равно закэшируются
        return Promise.allSettled(PRECACHE.map(function (u) { return cache.add(u); }));
      })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (k) { return k.indexOf('formyla-') === 0 && k.indexOf(CACHE_VERSION) !== 0; })
            .map(function (k) { return caches.delete(k); })
        );
      })
      .then(function () { return self.clients.claim(); })
  );
});

/* ───────── fetch ───────── */
function isStaticAsset(url) {
  return url.pathname.indexOf('/static/') === 0;
}

function isBypassed(url) {
  var p = url.pathname;
  return p.indexOf('/api/') === 0 || p.indexOf('/socket.io') === 0 || p.indexOf('/ws') === 0 ||
         p.indexOf('/admin') === 0 || p.indexOf('/login') === 0 || p.indexOf('/logout') === 0 ||
         p === '/sw.js' || p === '/site.webmanifest' || p === '/manifest.json';
}

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // CDN (KaTeX, Chart.js и т.п.) — не трогаем
  if (isBypassed(url)) return;

  // Навигация по страницам: только сеть, при её отсутствии — офлайн-заглушка.
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req).catch(function () {
        return caches.match(OFFLINE_URL).then(function (r) {
          return r || new Response('Нет сети', {
            status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' }
          });
        });
      })
    );
    return;
  }

  // Статика: stale-while-revalidate (быстро из кэша, в фоне обновляем).
  if (isStaticAsset(url)) {
    if (req.headers.has('range')) return;  // медиа с Range-запросами (206) не кэшируем
    event.respondWith(
      caches.open(STATIC_CACHE).then(function (cache) {
        return cache.match(req).then(function (cached) {
          var network = fetch(req).then(function (resp) {
            if (resp && resp.status === 200) {
              cache.put(req, resp.clone()).catch(function () {});
            }
            return resp;
          }).catch(function () { return null; });
          return cached || network.then(function (r) { return r || Response.error(); });
        });
      })
    );
  }
});

/* ───────── Web Push (логика прежняя) ───────── */
self.addEventListener('push', function (event) {
  var data = { title: 'Formyla', body: '', icon: '/static/logo.png', data: {} };

  if (event.data) {
    try {
      var parsed = event.data.json();
      data = Object.assign({}, data, parsed);
    } catch (e) {
      data.body = event.data.text() || data.body;
    }
  }

  var options = {
    body: data.body,
    icon: data.icon || '/static/logo.png',
    badge: data.badge || '/static/favicon-32x32.png',
    vibrate: [200, 100, 200],
    data: data.data || {},
    silent: false,
    requireInteraction: true
  };

  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var targetUrl = event.notification.data && event.notification.data.url;
  if (!targetUrl) return;

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
      for (var i = 0; i < clientList.length; i++) {
        var client = clientList[i];
        if (client.url === targetUrl && 'focus' in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
