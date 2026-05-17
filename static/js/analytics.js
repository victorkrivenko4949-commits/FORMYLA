/* FORMYLA — клиентская аналитика поверх Plausible.
 *
 * Все события идут только если Plausible подключён (config.PLAUSIBLE_DOMAIN).
 * Если нет — функции остаются доступны и просто пишут лог в console (dev).
 *
 * Использование:
 *   trackEvent('signup', { method: 'email' });
 *   trackEvent('task_solved', { difficulty: 5 });
 *   trackEvent('subscription_started', { plan: 'pro_monthly', revenue: { amount: 390, currency: 'RUB' } });
 */
(function () {
    'use strict';

    const HAS_PLAUSIBLE = typeof window.plausible === 'function';

    /**
     * Универсальная функция трекинга.
     * @param {string} name - имя события (используется как Goal name в Plausible).
     * @param {Object} [props] - произвольные пропсы (передаются как Custom Properties).
     */
    function trackEvent(name, props) {
        if (!name) return;
        const payload = props ? { props: props } : {};
        if (HAS_PLAUSIBLE) {
            try {
                window.plausible(name, payload);
            } catch (e) {
                /* swallow: Plausible cannot be allowed to break the UX */
            }
        } else if (window.console && console.debug) {
            console.debug('[analytics:dev]', name, props || {});
        }
    }

    /**
     * Готовая обёртка для трекинга outbound кликов на внешние ссылки.
     * Plausible сам ловит outbound из тега `script.outbound-links.js`, но эта
     * функция полезна если нужно явно записать клик с дополнительными пропсами.
     */
    function trackOutbound(url, props) {
        trackEvent('Outbound Link: Click', Object.assign({ url: url }, props || {}));
    }

    /**
     * Авто-трекинг кликов по элементам с data-track="..." атрибутом.
     * Пример: <a href="..." data-track="cta_click" data-track-loc="hero">…</a>
     */
    function bindAutoTracking() {
        document.addEventListener('click', function (ev) {
            const target = ev.target.closest('[data-track]');
            if (!target) return;
            const name = target.getAttribute('data-track');
            if (!name) return;
            const props = {};
            for (const attr of target.attributes) {
                if (attr.name.startsWith('data-track-') && attr.name !== 'data-track') {
                    const key = attr.name.replace('data-track-', '');
                    props[key] = attr.value;
                }
            }
            trackEvent(name, Object.keys(props).length ? props : undefined);
        }, { passive: true });
    }

    // Экспорт в глобал
    window.formylaAnalytics = {
        trackEvent: trackEvent,
        trackOutbound: trackOutbound,
    };
    // Удобный короткий алиас
    window.trackEvent = trackEvent;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindAutoTracking);
    } else {
        bindAutoTracking();
    }
})();
