/**
 * Service Worker for Formyla Web Push notifications.
 * 
 * This SW listens for push events from the server and displays them
 * as browser notifications. It also handles notification clicks to
 * navigate the user to the relevant page.
 * 
 * Installed & activated at page load via push_notifications.js.
 */

self.addEventListener('install', function(event) {
  // Force activate — don't wait for old SW to be released
  self.skipWaiting();
});

self.addEventListener('activate', function(event) {
  // Claim all clients immediately so the SW is in control
  event.waitUntil(clients.claim());
});

/**
 * Handle incoming push events.
 * The server sends a JSON payload with:
 *   { title, body, icon, badge, data: { url, type, ... } }
 */
self.addEventListener('push', function(event) {
  let data = { title: 'Formyla', body: '', icon: '/static/logo.png', data: {} };

  if (event.data) {
    try {
      const parsed = event.data.json();
      data = { ...data, ...parsed };
    } catch (e) {
      // If not valid JSON, use the raw text as body
      data.body = event.data.text() || data.body;
    }
  }

  const options = {
    body: data.body,
    icon: data.icon || '/static/logo.png',
    badge: data.badge || '/static/favicon-32x32.png',
    vibrate: [200, 100, 200],
    data: data.data || {},
    silent: false,
    requireInteraction: true,  // Stay visible until user interacts
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

/**
 * Handle notification click.
 * Closes the notification and navigates to the target URL if provided.
 */
self.addEventListener('notificationclick', function(event) {
  event.notification.close();

  const targetUrl = event.notification.data && event.notification.data.url;

  if (targetUrl) {
    event.waitUntil(
      clients.matchAll({ type: 'window', includeUncontrolled: true })
        .then(function(clientList) {
          // Try to focus an existing window with the same URL
          for (const client of clientList) {
            if (client.url === targetUrl && 'focus' in client) {
              return client.focus();
            }
          }
          // Otherwise open a new window/tab
          if (clients.openWindow) {
            return clients.openWindow(targetUrl);
          }
        })
    );
  }
});
