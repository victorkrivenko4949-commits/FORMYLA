/**
 * api.js — Универсальный fetch-wrapper для FORMYLA
 *
 * Автоматически перехватывает 403 с error='limit_reached'
 * и показывает paywall модалку.
 *
 * Использование:
 *   const resp = await apiRequest('/api/check_adaptive_answer', {
 *       method: 'POST',
 *       headers: { 'Content-Type': 'application/json' },
 *       body: JSON.stringify({ ... })
 *   });
 *   if (!resp) return; // paywall был показан
 *   const data = await resp.json();
 */

/**
 * Выполнить fetch-запрос с автоматической обработкой paywall.
 *
 * @param {string} url
 * @param {RequestInit} options
 * @returns {Response|null} — null если показан paywall, Response иначе
 */
async function apiRequest(url, options = {}) {
    let resp;
    try {
        resp = await fetch(url, options);
    } catch (networkErr) {
        console.error('[apiRequest] Network error:', networkErr);
        throw networkErr;
    }

    if (resp.status === 403) {
        let data;
        try {
            data = await resp.clone().json();
        } catch (e) {
            // Не JSON — возвращаем как есть
            return resp;
        }

        if (data && data.error === 'limit_reached') {
            // Показываем paywall если функция доступна
            if (typeof window.showPaywall === 'function') {
                window.showPaywall(data);
            } else {
                // Fallback: редирект на страницу подписки
                console.warn('[apiRequest] showPaywall not available, redirecting...');
                window.location.href = data.upgrade_url || '/subscribe';
            }
            return null;
        }
    }

    if (resp.status === 401) {
        // Не авторизован — редирект на логин
        console.warn('[apiRequest] 401 Unauthorized, redirecting to login...');
        window.location.href = '/login';
        return null;
    }

    return resp;
}

// Экспортируем глобально
window.apiRequest = apiRequest;
