/*
 * FORMYLA — лёгкий клиент для собственной аналитики /api/track.
 *
 * Что делает:
 *   1) Авто-логирует `landing_view` на загрузке страницы, если location.pathname
 *      ∈ {'/', '/welcome'} (как требует ТЗ).
 *   2) Делегированно ловит клики по [data-track="cta"] → пишет `cta_click`.
 *
 * НЕ зависит от Plausible (см. analytics.js — оно про внешнюю аналитику).
 * Обе системы могут жить параллельно.
 */
(function () {
  'use strict';

  function track(event, meta) {
    try {
      var body = JSON.stringify({
        event: event,
        meta: meta || {},
        path: location.pathname + location.search,
      });
      // Используем fetch с keepalive, чтобы запрос ушёл даже при unload.
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: 'application/json' });
        navigator.sendBeacon('/api/track', blob);
      } else {
        fetch('/api/track', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: body,
          keepalive: true,
        }).catch(function () { /* swallow */ });
      }
    } catch (e) { /* swallow */ }
  }
  // Экспорт для ручных вызовов: window.fmTrack('foo', {bar:1})
  window.fmTrack = track;

  // --- 1. Landing view -----------------------------------------------------
  function maybeLandingView() {
    var p = location.pathname;
    if (p === '/' || p === '/welcome' || p === '/index') {
      var page = (p === '/welcome') ? 'welcome' : 'home';
      track('landing_view', { page: page });
    }
  }

  // --- 2. Click-delegation для data-track="cta" ----------------------------
  function bindCtaClicks() {
    document.addEventListener('click', function (ev) {
      var el = ev.target && ev.target.closest && ev.target.closest('[data-track="cta"]');
      if (!el) return;
      track('cta_click', {
        cta_id: el.getAttribute('data-cta-id') || '',
        href: el.getAttribute('href') || '',
        page: location.pathname,
        text: (el.innerText || '').slice(0, 64).trim(),
      });
    }, true); // capture, чтобы поймать клики до preventDefault и т.п.
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      maybeLandingView();
      bindCtaClicks();
    });
  } else {
    maybeLandingView();
    bindCtaClicks();
  }
})();
