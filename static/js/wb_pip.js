// FORMYLA — Picture-in-Picture (PiP) overlay manager.
// Загружается в base.html на ВСЕХ страницах.
// При обнаружении сохранённого состояния конференции в sessionStorage
// показывает плавающее окно в правом нижнем углу и переподключается к комнате.
//
// Ключевая логика:
//   1. При навигации wb_ui.js сохраняет {room, name, user_id} в sessionStorage
//   2. На новой странице wb_pip.js читает sessionStorage и показывает PiP
//   3. Ждёт, пока iframe загрузится и engine/signalling будут готовы
//   4. Ждёт ws-connected от iframe, затем отправляет join
//   5. После joined — показывает локальный видеопоток
(function () {
    "use strict";

    var STORAGE_KEY = "cf_pip_state";
    var PIP_VIDEO_ID = "cf-pip-video";
    var PIP_OVERLAY_ID = "cf-pip-overlay";

    var pipOverlay = null;
    var pipVideo = null;
    var pipActive = false;
    var joinSent = false;
    var wsConnected = false;
    var retryCount = 0;
    var MAX_RETRIES = 40;  // 40 × 500ms = 20 секунд

    // Сохранённое состояние
    var savedState = null;

    // ── Инициализация при загрузке DOM ──
    document.addEventListener("DOMContentLoaded", function () {
        pipOverlay = document.getElementById(PIP_OVERLAY_ID);
        if (!pipOverlay) return;
        pipVideo = document.getElementById(PIP_VIDEO_ID);

        // Если мы на странице /conference — не показываем PiP,
        // там wb_ui.js сам всё поднимет
        if (window.location.pathname === "/conference") {
            // Не удаляем sessionStorage — wb_ui.js его прочитает
            return;
        }

        // Проверяем sessionStorage
        var saved = sessionStorage.getItem(STORAGE_KEY);
        if (!saved) return;

        try {
            savedState = JSON.parse(saved);
        } catch (e) {
            console.warn("[wb_pip] parse error:", e);
            sessionStorage.removeItem(STORAGE_KEY);
            return;
        }

        if (!savedState || !savedState.room) {
            sessionStorage.removeItem(STORAGE_KEY);
            return;
        }

        // Слушаем сообщения от iframe ДО активации PiP
        window.addEventListener("message", _onIframeMessage);

        // Активируем PiP
        _activatePip();
    });

    // ── Активировать PiP ──
    function _activatePip() {
        pipActive = true;
        pipOverlay.style.display = "flex";
        // Добавляем класс для анимации появления
        setTimeout(function () {
            if (pipOverlay) pipOverlay.classList.add("cf-pip-visible");
        }, 50);

        var codeEl = document.getElementById("cf-pip-code");
        if (codeEl) codeEl.textContent = savedState.room || "";

        _setStatus("Подключение...");
        _log("PiP activated for room:", savedState.room);

        // Начинаем ждать готовности iframe
        _waitForIframe();
    }

    // ── Ждём загрузки iframe и готовности engine ──
    function _waitForIframe() {
        if (!pipActive) return;
        retryCount++;

        if (retryCount > MAX_RETRIES) {
            _setStatus("Таймаут подключения");
            _log("iframe wait timeout");
            return;
        }

        var iframe = document.getElementById("wbCallEngine");
        if (!iframe || !iframe.contentWindow) {
            setTimeout(_waitForIframe, 500);
            return;
        }

        try {
            var win = iframe.contentWindow;
            // Проверяем, готов ли engine и signalling
            if (win.__wbEngine && win.__wbSignalling) {
                _log("engine ready, checking WS connection...");
                // Engine готов — проверяем WS соединение
                if (wsConnected) {
                    _doJoin();
                } else {
                    // Ждём ws-connected события (придёт через postMessage)
                    // Но также проверяем напрямую через socket
                    var sig = win.__wbSignalling;
                    if (sig && typeof sig.isConnected === "function" && sig.isConnected()) {
                        wsConnected = true;
                        _doJoin();
                    } else {
                        // Ждём события ws-connected
                        _setStatus("Ожидание сервера...");
                        setTimeout(_waitForIframe, 500);
                    }
                }
            } else {
                // Engine ещё не готов
                setTimeout(_waitForIframe, 500);
            }
        } catch (e) {
            _warn("waitForIframe error:", e);
            setTimeout(_waitForIframe, 500);
        }
    }

    // ── Отправить join в iframe ──
    function _doJoin() {
        if (!pipActive || joinSent || !savedState) return;
        if (!wsConnected) {
            _log("WS not connected yet, waiting...");
            setTimeout(_doJoin, 300);
            return;
        }

        var iframe = document.getElementById("wbCallEngine");
        if (!iframe || !iframe.contentWindow) {
            _warn("iframe not found for join");
            return;
        }

        try {
            var win = iframe.contentWindow;
            if (win.__wbEngine) {
                joinSent = true;
                _log("sending join to room:", savedState.room);
                win.__wbEngine.join(
                    savedState.room,
                    savedState.name || "User",
                    savedState.user_id || null
                );
                _setStatus("Вход в комнату...");
            } else {
                _warn("engine not available for join");
                joinSent = false;
                setTimeout(_doJoin, 500);
            }
        } catch (e) {
            _warn("doJoin error:", e);
            joinSent = false;
            setTimeout(_doJoin, 500);
        }
    }

    // ── Обработка сообщений от iframe ──
    function _onIframeMessage(event) {
        var msg = event.data;
        if (!msg || !msg.type) return;

        switch (msg.type) {
            case "ws-connected":
                _log("WS connected");
                wsConnected = true;
                if (pipActive && !joinSent) {
                    _setStatus("Подключено к серверу...");
                    _doJoin();
                }
                break;

            case "ws-disconnected":
                wsConnected = false;
                joinSent = false;  // Сбрасываем флаг — при реконнекте нужно снова join
                if (pipActive) _setStatus("Нет связи...");
                break;

            case "joined":
                if (pipActive) {
                    _log("joined room, peer:", msg.peer_id);
                    _setStatus("В конференции");
                    // Обновляем код комнаты
                    var codeEl = document.getElementById("cf-pip-code");
                    if (codeEl && savedState && savedState.room) {
                        codeEl.textContent = savedState.room;
                    }
                    // Получаем локальный видеопоток
                    _fetchLocalStream();
                }
                break;

            case "join-error":
                if (pipActive) {
                    _warn("join error:", msg.reason);
                    _setStatus("Ошибка входа");
                    joinSent = false;
                    // Повторяем через 2 секунды
                    setTimeout(function () {
                        if (pipActive && !joinSent) _doJoin();
                    }, 2000);
                }
                break;

            case "kicked":
                if (pipActive) {
                    _setStatus("Вас удалили");
                    setTimeout(_clearPip, 2000);
                }
                break;

            case "room-ended":
                if (pipActive) {
                    _setStatus("Комната закрыта");
                    setTimeout(_clearPip, 2000);
                }
                break;

            case "local-stream-ready":
                // wb_engine.js отправляет это после join
                if (pipActive && pipVideo && msg.stream) {
                    try {
                        pipVideo.srcObject = msg.stream;
                        pipVideo.muted = true;
                        pipVideo.play().catch(function () {});
                        _log("local stream attached from engine event");
                    } catch (e) {
                        _warn("attach local stream error:", e);
                    }
                }
                break;

            case "remote-track":
                // Если локальный поток недоступен — показываем remote
                if (pipActive && pipVideo && !pipVideo.srcObject) {
                    if (msg.streams && msg.streams[0]) {
                        try {
                            pipVideo.srcObject = msg.streams[0];
                            pipVideo.play().catch(function () {});
                            _log("remote stream attached to PiP");
                        } catch (e) {
                            _warn("attach remote stream error:", e);
                        }
                    }
                }
                break;

            case "participant-joined":
                if (pipActive) {
                    var countEl = document.getElementById("cf-pip-count");
                    if (countEl) {
                        var cur = parseInt(countEl.textContent, 10) || 1;
                        countEl.textContent = cur + 1;
                    }
                }
                break;

            case "participant-left":
                if (pipActive) {
                    var countEl2 = document.getElementById("cf-pip-count");
                    if (countEl2) {
                        var cur2 = parseInt(countEl2.textContent, 10) || 1;
                        countEl2.textContent = Math.max(1, cur2 - 1);
                    }
                }
                break;
        }
    }

    // ── Получить локальный видеопоток из iframe ──
    function _fetchLocalStream() {
        if (!pipActive) return;
        var iframe = document.getElementById("wbCallEngine");
        if (!iframe || !iframe.contentWindow) {
            setTimeout(_fetchLocalStream, 500);
            return;
        }

        try {
            var win = iframe.contentWindow;
            if (win.__wbEngine && typeof win.__wbEngine.getLocalStream === "function") {
                var stream = win.__wbEngine.getLocalStream();
                if (stream && pipVideo) {
                    pipVideo.srcObject = stream;
                    pipVideo.muted = true;
                    pipVideo.play().catch(function () {});
                    _log("local stream attached to PiP");
                    return;
                }
            }
        } catch (e) {
            _warn("fetchLocalStream error:", e);
        }

        // Повторяем попытку (поток может ещё не быть готов)
        if (retryCount < MAX_RETRIES) {
            setTimeout(_fetchLocalStream, 800);
        }
    }

    // ── Обновить статус в PiP ──
    function _setStatus(text) {
        var el = document.getElementById("cf-pip-status");
        if (el) el.textContent = text;
    }

    // ── Скрыть PiP (без выхода из комнаты) ──
    function _hidePip() {
        pipActive = false;
        if (pipOverlay) {
            pipOverlay.classList.remove("cf-pip-visible");
            setTimeout(function () {
                if (pipOverlay) pipOverlay.style.display = "none";
            }, 200);
        }
        if (pipVideo) pipVideo.srcObject = null;
    }

    // ── Полный выход из конференции ──
    function _clearPip() {
        pipActive = false;
        joinSent = false;
        wsConnected = false;
        retryCount = 0;
        savedState = null;
        sessionStorage.removeItem(STORAGE_KEY);

        if (pipOverlay) {
            pipOverlay.classList.remove("cf-pip-visible");
            setTimeout(function () {
                if (pipOverlay) pipOverlay.style.display = "none";
            }, 200);
        }
        if (pipVideo) pipVideo.srcObject = null;

        // Отправляем leave в iframe
        var iframe = document.getElementById("wbCallEngine");
        if (iframe && iframe.contentWindow) {
            try {
                if (iframe.contentWindow.__wbEngine) {
                    iframe.contentWindow.__wbEngine.leave();
                } else {
                    iframe.contentWindow.postMessage({ type: "leave" }, "*");
                }
            } catch (e) {
                _warn("leave error:", e);
            }
        }
        _log("PiP cleared");
    }

    // ── Развернуть в полный экран ──
    function _expandConference() {
        // Сохраняем состояние (если ещё не сохранено)
        if (savedState && savedState.room) {
            try {
                sessionStorage.setItem(STORAGE_KEY, JSON.stringify(savedState));
            } catch (e) {}
        }
        var room = savedState ? (savedState.room || "") : "";
        window.location.href = "/conference" + (room ? "?room=" + room : "");
    }

    // ── Логирование ──
    function _log() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_pip]");
        console.log.apply(console, args);
    }
    function _warn() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_pip]");
        console.warn.apply(console, args);
    }

    // ── Публичное API ──
    window.__pipManager = {
        clear: _clearPip,
        hide: _hidePip,
        expand: _expandConference,
        isActive: function () { return pipActive; },
        getRoom: function () {
            return savedState ? (savedState.room || null) : null;
        },
    };
})();
