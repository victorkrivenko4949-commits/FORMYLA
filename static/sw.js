/**
 * Service Worker FORMYLA.net — PWA_INSTALL_V3 (11.10.2026).
 *
 * 1. Web Push (как и раньше): показывает уведомления и открывает нужную страницу.
 * 2. Офлайн/кэш: даёт сайту право на установку как приложения и показывает
 *    /offline, когда нет сети.
 * 3. Обновления: HTML всегда из сети; JS/CSS — сеть в приоритете (кэш только как
 *    запасной вариант без сети); картинки — из кэша с фоновым обновлением.
 *    Новая версия SW активируется сразу (skipWaiting + SKIP_WAITING-сообщение),
 *    старые кэши удаляются — приложение всегда на той же версии, что и сайт.
 *
 * Отдаётся по адресу /sw.js (routes/pwa.py) со scope «/».
 * При серьёзных изменениях статики поднимите CACHE_VERSION.
 */
var CACHE_VERSION = 'formyla-v3';
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

/* ───────── install / activate / messages ───────── */
self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(function (cache) {
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

self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

/* ───────── fetch ───────── */
function isStaticAsset(url) {
  return url.pathname.indexOf('/static/') === 0;
}
function isCodeAsset(url) {
  return /\.(js|css|mjs)$/i.test(url.pathname);
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
  if (url.origin !== self.location.origin) return;
  if (isBypassed(url)) return;

  // Страницы: только сеть; без сети — офлайн-заглушка.
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

  if (!isStaticAsset(url)) return;
  if (req.headers.has('range')) return;

  // JS/CSS: сеть в приоритете — обновления видны сразу; кэш только без сети.
  if (isCodeAsset(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(function (cache) {
        return fetch(req).then(function (resp) {
          if (resp && resp.status === 200) cache.put(req, resp.clone()).catch(function () {});
          return resp;
        }).catch(function () {
          return cache.match(req).then(function (c) { return c || Response.error(); });
        });
      })
    );
    return;
  }

  // Картинки и прочая статика: из кэша сразу, в фоне обновляем.
  event.respondWith(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.match(req).then(function (cached) {
        var network = fetch(req).then(function (resp) {
          if (resp && resp.status === 200) cache.put(req, resp.clone()).catch(function () {});
          return resp;
        }).catch(function () { return null; });
        return cached || network.then(function (r) { return r || Response.error(); });
      });
    })
  );
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
