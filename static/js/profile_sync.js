/**
 * FORMYLA Profile Sync — персистентные никнеймы и результаты тестов
 * 
 * Функции:
 * 1. Очередь синхронизации результатов (offline-first)
 * 2. Миграция данных из localStorage в БД
 * 3. Управление никнеймом
 * 4. Загрузка профиля
 */

(function() {
    'use strict';

    const SYNC_QUEUE_KEY = 'formyla_sync_queue';
    const PROFILE_CACHE_KEY = 'formyla_profile_cache';
    const MIGRATED_KEY = 'formyla_data_migrated';

    // ============================================================
    // Утилиты
    // ============================================================

    function getDeviceId() {
        // Читаем из cookie
        const cookies = document.cookie.split(';');
        for (let c of cookies) {
            c = c.trim();
            if (c.startsWith('formyla_device_id=')) {
                return c.substring('formyla_device_id='.length);
            }
        }
        return null;
    }

    function getSyncQueue() {
        try {
            const data = localStorage.getItem(SYNC_QUEUE_KEY);
            return data ? JSON.parse(data) : [];
        } catch (e) {
            return [];
        }
    }

    function saveSyncQueue(queue) {
        try {
            localStorage.setItem(SYNC_QUEUE_KEY, JSON.stringify(queue));
        } catch (e) {
            console.warn('[ProfileSync] Не удалось сохранить очередь:', e);
        }
    }

    // ============================================================
    // Очередь синхронизации результатов
    // ============================================================

    /**
     * Добавить результат теста в очередь и попытаться отправить
     * @param {Object} result — данные результата теста
     */
    function saveTestResult(result) {
        var entry = {
            test_type: result.test_type,
            class_level: result.class_level,
            topic: result.topic,
            task_id: result.task_id,
            difficulty: result.difficulty,
            is_correct: result.is_correct,
            user_answer: result.user_answer,
            time_spent_sec: result.time_spent_sec,
            rating_delta: result.rating_delta,
            rating_after: result.rating_after,
            _queued_at: new Date().toISOString(),
            _attempts: 0
        };

        // Добавляем в очередь
        var queue = getSyncQueue();
        queue.push(entry);
        saveSyncQueue(queue);

        // Пытаемся отправить
        flushSyncQueue();
    }

    /**
     * Отправить все результаты из очереди на сервер
     */
    async function flushSyncQueue() {
        var queue = getSyncQueue();
        if (queue.length === 0) return;

        var remaining = [];

        for (var i = 0; i < queue.length; i++) {
            var entry = queue[i];
            try {
                var response = await fetch('/api/save_test_result', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        test_type: entry.test_type || 'practice',
                        class_level: entry.class_level,
                        topic: entry.topic,
                        task_id: entry.task_id,
                        difficulty: entry.difficulty,
                        is_correct: entry.is_correct,
                        user_answer: entry.user_answer,
                        time_spent_sec: entry.time_spent_sec,
                        rating_delta: entry.rating_delta,
                        rating_after: entry.rating_after
                    })
                });

                if (!response.ok) {
                    entry._attempts = (entry._attempts || 0) + 1;
                    if (entry._attempts < 5) {
                        remaining.push(entry);
                    } else {
                        console.warn('[ProfileSync] Результат отброшен после 5 попыток:', entry);
                    }
                }
                // Успех — не добавляем обратно в очередь
            } catch (e) {
                // Сетевая ошибка — оставляем в очереди
                entry._attempts = (entry._attempts || 0) + 1;
                if (entry._attempts < 10) {
                    remaining.push(entry);
                }
            }
        }

        saveSyncQueue(remaining);
    }

    // ============================================================
    // Профиль
    // ============================================================

    /**
     * Загрузить профиль с сервера
     * @returns {Object|null} данные профиля
     */
    async function loadProfile() {
        try {
            var response = await fetch('/api/profile');
            if (!response.ok) return getCachedProfile();

            var data = await response.json();
            if (data.success) {
                // Кэшируем
                try {
                    localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify({
                        success: data.success,
                        profile: data.profile,
                        progress: data.progress,
                        recent_results: data.recent_results,
                        _cached_at: new Date().toISOString()
                    }));
                } catch (e) { /* ignore — Safari private mode */ }
                return data;
            }
            return getCachedProfile();
        } catch (e) {
            return getCachedProfile();
        }
    }

    function getCachedProfile() {
        try {
            var cached = localStorage.getItem(PROFILE_CACHE_KEY);
            return cached ? JSON.parse(cached) : null;
        } catch (e) {
            return null;
        }
    }

    // ============================================================
    // Никнейм
    // ============================================================

    /**
     * Установить никнейм
     * @param {string} nickname
     * @returns {Object} результат {success, nickname, error}
     */
    async function setNickname(nickname) {
        try {
            var response = await fetch('/api/set_nickname', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nickname: nickname })
            });

            var data = await response.json();
            return data;
        } catch (e) {
            return { error: 'Ошибка сети' };
        }
    }

    // ============================================================
    // Миграция localStorage -> БД
    // ============================================================

    /**
     * Мигрирует старые данные из localStorage в БД (однократно)
     */
    async function migrateLocalStorage() {
        try {
            if (localStorage.getItem(MIGRATED_KEY)) return;
        } catch (e) {
            return; // localStorage недоступен
        }

        var keysToMigrate = [];

        // Ищем ключи с результатами тестов в localStorage
        try {
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);
                if (!key) continue;

                // Типичные паттерны хранения результатов
                if (key.startsWith('adaptive_result_') ||
                    key.startsWith('test_result_') ||
                    key.startsWith('formyla_result_')) {
                    keysToMigrate.push(key);
                }
            }
        } catch (e) {
            console.warn('[ProfileSync] Ошибка чтения localStorage при миграции:', e);
            return;
        }

        if (keysToMigrate.length > 0) {
            console.log('[ProfileSync] Миграция', keysToMigrate.length, 'записей из localStorage');

            for (var j = 0; j < keysToMigrate.length; j++) {
                var mKey = keysToMigrate[j];
                try {
                    var data = JSON.parse(localStorage.getItem(mKey));
                    if (data && typeof data === 'object') {
                        saveTestResult({
                            test_type: data.test_type || 'migrated',
                            class_level: data.class_level || data.grade,
                            topic: data.topic,
                            task_id: data.task_id || data.problem_id,
                            difficulty: data.difficulty || data.level,
                            is_correct: data.is_correct || data.correct || false,
                            user_answer: data.user_answer || data.answer,
                            time_spent_sec: data.time_spent_sec || data.time_spent,
                            rating_delta: data.rating_delta,
                            rating_after: data.rating_after || data.rating
                        });
                    }
                } catch (e) {
                    console.warn('[ProfileSync] Ошибка миграции ключа', mKey, e);
                }
            }
        }

        // Помечаем как мигрированное
        try {
            localStorage.setItem(MIGRATED_KEY, new Date().toISOString());
        } catch (e) { /* ignore */ }
    }

    // ============================================================
    // Периодическая синхронизация
    // ============================================================

    function startPeriodicSync() {
        // Синхронизация каждые 30 секунд
        setInterval(function() {
            flushSyncQueue();
        }, 30000);

        // Синхронизация при восстановлении сети
        window.addEventListener('online', function() {
            console.log('[ProfileSync] Сеть восстановлена, синхронизация...');
            flushSyncQueue();
        });

        // Синхронизация перед закрытием страницы
        window.addEventListener('beforeunload', function() {
            var queue = getSyncQueue();
            if (queue.length > 0) {
                // Используем sendBeacon для надёжной отправки
                for (var i = 0; i < queue.length; i++) {
                    var entry = queue[i];
                    try {
                        navigator.sendBeacon('/api/save_test_result',
                            new Blob([JSON.stringify({
                                test_type: entry.test_type,
                                class_level: entry.class_level,
                                topic: entry.topic,
                                task_id: entry.task_id,
                                difficulty: entry.difficulty,
                                is_correct: entry.is_correct,
                                user_answer: entry.user_answer,
                                time_spent_sec: entry.time_spent_sec,
                                rating_delta: entry.rating_delta,
                                rating_after: entry.rating_after
                            })], { type: 'application/json' })
                        );
                    } catch (e) { /* ignore */ }
                }
            }
        });
    }

    // ============================================================
    // Инициализация
    // ============================================================

    function init() {
        console.log('[ProfileSync] Инициализация...');

        // Запускаем миграцию localStorage
        migrateLocalStorage();

        // Отправляем накопленные результаты
        flushSyncQueue();

        // Запускаем периодическую синхронизацию
        startPeriodicSync();

        console.log('[ProfileSync] Готов. Device ID:', getDeviceId());
    }

    // Запуск при загрузке DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // ============================================================
    // Публичный API (глобальный объект)
    // ============================================================

    window.FormylaSync = {
        saveTestResult: saveTestResult,
        loadProfile: loadProfile,
        setNickname: setNickname,
        flushQueue: flushSyncQueue,
        getDeviceId: getDeviceId,
        getQueueSize: function() { return getSyncQueue().length; }
    };

})();
