/**
 * push_notifications.js — Web Push Notifications client.
 *
 * 1. Registers the Service Worker (static/sw.js).
 * 2. On first visit after login, asks for Notification permission.
 * 3. On grant, subscribes via the Push API and sends the subscription
 *    to the server (POST /api/push/subscribe).
 *
 * Dependencies: none (vanilla JS).
 * Loaded from base.html for authenticated users only.
 */
(function () {
    'use strict';
    var VAPID_PUBLIC_KEY = window.__VAPID_PUBLIC_KEY || null;
    var swRegistration = null;

    function _urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - base64String.length % 4) % 4);
        var base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
        return Uint8Array.from(window.atob(base64), function (ch) { return ch.charCodeAt(0); });
    }

    function _sendSubscriptionToServer(subscription) {
        if (!subscription) return;
        var data = subscription.toJSON ? subscription.toJSON() : subscription;
        fetch('/api/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).then(function (resp) {
            if (!resp.ok) console.warn('[Push] Failed to save subscription:', resp.status);
        }).catch(function (err) {
            console.warn('[Push] Error saving subscription:', err);
        });
    }

    function _subscribe(registration) {
        if (!registration || !registration.pushManager) return;
        registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: _urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
        }).then(function (subscription) {
            console.log('[Push] Subscribed successfully');
            _sendSubscriptionToServer(subscription);
        }).catch(function (err) {
            console.warn('[Push] Subscribe failed:', err);
        });
    }

    function _checkExistingSubscription(registration) {
        if (!registration || !registration.pushManager) return;
        registration.pushManager.getSubscription().then(function (subscription) {
            if (subscription) {
                console.log('[Push] Found existing subscription, refreshing on server');
                _sendSubscriptionToServer(subscription);
            }
        });
    }

    function _requestPermission(registration) {
        if (!registration) return;
        if (!('Notification' in window)) { console.log('[Push] Notification API not supported'); return; }
        if (Notification.permission === 'granted') { _checkExistingSubscription(registration); return; }
        if (Notification.permission === 'denied') { console.log('[Push] Permission previously denied'); return; }
        Notification.requestPermission().then(function (permission) {
            if (permission === 'granted') { console.log('[Push] Permission granted'); _subscribe(registration); }
            else { console.log('[Push] Permission denied by user'); }
        });
    }

    function init() {
        if (!VAPID_PUBLIC_KEY) { console.log('[Push] VAPID key not set, skipping'); return; }
        if (!('serviceWorker' in navigator)) { console.log('[Push] Service Workers not supported'); return; }
        navigator.serviceWorker.register('/static/sw.js').then(function (registration) {
            swRegistration = registration;
            console.log('[Push] SW registered');
            _requestPermission(registration);
        }).catch(function (err) {
            console.warn('[Push] SW registration failed:', err);
        });
    }

    init();

})();
