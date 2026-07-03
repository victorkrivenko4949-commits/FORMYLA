// FORMYLA — WebSocket signalling client (Flask-SocketIO).
//
// Загружается внутри call_engine.html (iframe). Устанавливает постоянное
// SocketIO-соединение с сервером и общается с родительской страницей через
// window.__wbEngine → postMessage.
//
// API (через window.__wbSignalling):
//   connect()         — установить соединение (авто при загрузке)
//   disconnect()      — закрыть соединение
//   join(room, name, user_id) — войти в комнату
//   leave()           — покинуть комнату
//   sendSignal(to, type, data) — отправить сигнал WebRTC (offer/answer/ICE)
//   setMute(kind, state, target?) — mute/unmute
//   kick(target)      — кикнуть участника
//   changeRole(target, role) — сменить роль
//   sendChat(text, to?) — отправить сообщение чата
//   sendReaction(emoji)   — отправить эмодзи
//   setHandRaise(on)  — поднять/опустить руку
//   setScreenShare(on) — начать/остановить демонстрацию
//   setFlag(flag, value) — установить флаг комнаты
//   requestState()    — запросить полное состояние комнаты
//
// События от сервера (пересылаются в родительское окно через postMessage):
//   joined, participant-joined, participant-left, signal, mute-changed,
//   kicked, role-changed, chat-msg, reaction, hand-raise, screen-share,
//   flag-changed, room-state, room-ended

(function () {
    "use strict";

    if (window.__wbSignalling) return; // уже инициализирован

    // --- Состояние ---
    var socket = null;
    var connected = false;
    var reconnectTimer = null;
    var reconnectAttempts = 0;
    var MAX_RECONNECT_DELAY = 30000; // 30 сек макс
    var currentRoom = null;
    var currentName = null;
    var currentUserId = null;

    // --- Callbacks (устанавливаются wb_engine.js) ---
    var _onMessage = null;  // function(event, data) — любой входящий event
    var _onSignal = null;   // function(from, signalType, data) — WebRTC signal

    function _log() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_signalling]");
        console.log.apply(console, args);
    }

    function _warn() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_signalling]");
        console.warn.apply(console, args);
    }

    function _error() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_signalling]");
        console.error.apply(console, args);
    }

    // --- PostMessage в родительское окно ---
    function _postToParent(type, data) {
        if (!window.parent) return;
        var msg = data || {};
        msg.type = type;
        try {
            window.parent.postMessage(msg, "*");
        } catch (e) {
            _warn("postMessage error:", e);
        }
    }

    // --- Обработка входящих событий от SocketIO ---
    function _onServerEvent(eventName) {
        return function () {
            // arguments[0] — данные от сервера
            var data = arguments.length > 0 ? arguments[0] : {};
            _log("server event:", eventName, data);

            // Пересылаем родителю
            _postToParent(eventName, data);

            // Если есть callback от engine
            if (_onMessage) {
                try { _onMessage(eventName, data); } catch (e) { _error("onMessage error:", e); }
            }

            // Специфичная обработка signal (для wb_engine)
            if (eventName === "signal" && data && data.from) {
                if (_onSignal) {
                    try { _onSignal(data.from, data.type || data.signalType, data); } catch (e) { _error("onSignal error:", e); }
                }
            }

            // Сброс счётчика реконнекта при любом успешном событии
            reconnectAttempts = 0;
        };
    }

    // --- Подключение к SocketIO ---
    function _connectSocket() {
        if (socket && socket.connected) return;

        var opts = {
            transports: ["websocket", "polling"],
            reconnection: false, // управляем сами
            timeout: 10000,
            forceNew: true,
        };

        try {
            socket = io("/ws-call", opts); // namespace для звонков
        } catch (e) {
            _error("io() failed:", e);
            _scheduleReconnect();
            return;
        }

        socket.on("connect", function () {
            connected = true;
            reconnectAttempts = 0;
            _log("connected, id=" + socket.id);

            _postToParent("ws-connected", { sid: socket.id });

            // Если есть pending комната — автоматически перезаходим
            if (currentRoom) {
                _doJoin(currentRoom, currentName, currentUserId);
            }
        });

        socket.on("disconnect", function (reason) {
            connected = false;
            _log("disconnected:", reason);
            _postToParent("ws-disconnected", { reason: reason });

            if (reason !== "io client disconnect") {
                _scheduleReconnect();
            }
        });

        socket.on("connect_error", function (err) {
            _error("connect_error:", err.message || err);
            _scheduleReconnect();
        });

        // Регистрируем обработчики событий от сервера
        var serverEvents = [
            "joined", "participant-joined", "participant-left",
            "signal", "mute-changed", "kicked", "role-changed",
            "chat-msg", "reaction", "hand-raise", "screen-share",
            "flag-changed", "room-state", "room-ended", "host-changed",
            "board-selected",
        ];
        for (var i = 0; i < serverEvents.length; i++) {
            socket.on(serverEvents[i], _onServerEvent(serverEvents[i]));
        }
    }

    function _scheduleReconnect() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        reconnectAttempts++;
        var delay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
        _log("reconnect in " + delay + "ms (attempt " + reconnectAttempts + ")");
        reconnectTimer = setTimeout(function () {
            reconnectTimer = null;
            _connectSocket();
        }, delay);
    }

    // --- Join комнаты ---
    function _doJoin(room, name, user_id) {
        if (!socket || !socket.connected) {
            _warn("cannot join: not connected");
            _postToParent("join-error", { reason: "not connected" });
            return;
        }
        currentRoom = room;
        currentName = name;
        currentUserId = user_id;
        socket.emit("join", {
            room: room,
            name: name,
            user_id: user_id || null,
        });
    }

    // --- Публичное API ---

    var api = {
        // Подключиться к WebSocket
        connect: function () {
            _connectSocket();
        },

        // Отключиться
        disconnect: function () {
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            if (socket) {
                socket.disconnect();
                socket = null;
            }
            connected = false;
            currentRoom = null;
        },

        // Присоединиться к комнате
        join: function (room, name, user_id) {
            _doJoin(room, name, user_id);
        },

        // Покинуть комнату
        leave: function () {
            if (socket && socket.connected) {
                socket.emit("leave");
            }
            currentRoom = null;
            currentName = null;
            currentUserId = null;
        },

        // Отправить WebRTC signal (offer/answer/ICE)
        sendSignal: function (to, signalType, data) {
            if (!socket || !socket.connected) return;
            socket.emit("signal", {
                to: to,
                type: signalType,
                data: data,
            });
        },

        // Mute/unmute микрофона или камеры
        setMute: function (kind, state, target) {
            if (!socket || !socket.connected) return;
            var payload = { kind: kind, state: !!state };
            if (target) payload.target = target;
            socket.emit("mute", payload);
        },

        // Кикнуть участника (только host/co-host)
        kick: function (target) {
            if (!socket || !socket.connected) return;
            socket.emit("kick", { target: target });
        },

        // Сменить роль (только host)
        changeRole: function (target, role) {
            if (!socket || !socket.connected) return;
            socket.emit("role-change", { target: target, role: role });
        },

        // Отправить сообщение чата
        sendChat: function (text, to) {
            if (!socket || !socket.connected) return;
            var payload = { text: text };
            if (to) payload.to = to;
            socket.emit("chat-msg", payload);
        },

        // Отправить реакцию (эмодзи)
        sendReaction: function (emoji) {
            if (!socket || !socket.connected) return;
            socket.emit("reaction", { type: "emoji", emoji: emoji || "👍" });
        },

        // Поднять/опустить руку
        setHandRaise: function (on) {
            if (!socket || !socket.connected) return;
            socket.emit("hand-raise", { on: !!on });
        },

        // Начать/остановить демонстрацию экрана
        setScreenShare: function (on) {
            if (!socket || !socket.connected) return;
            socket.emit("screen-share", { action: on ? "start" : "stop" });
        },

        // Выбрать доску для всех участников (только host/co-host)
        selectBoard: function (boardId, boardName) {
            if (!socket || !socket.connected) return;
            socket.emit("board-select", {
                board_id: boardId,
                board_name: boardName || boardId,
            });
        },

        // Установить флаг комнаты (lock, waiting_room, etc)
        setFlag: function (flag, value) {
            if (!socket || !socket.connected) return;
            socket.emit("set-flag", { flag: flag, value: value });
        },

        // Запросить полное состояние комнаты
        requestState: function () {
            if (!socket || !socket.connected) return;
            socket.emit("get-room-state");
        },

        // Получить статус соединения
        isConnected: function () {
            return connected;
        },

        // Установить callback на сообщения от сервера
        onMessage: function (cb) {
            _onMessage = cb;
        },

        // Установить callback на WebRTC signal
        onSignal: function (cb) {
            _onSignal = cb;
        },

        // Получить sid (SocketIO ID)
        getSid: function () {
            return socket ? socket.id : null;
        },
    };

    window.__wbSignalling = api;
    _log("signalling client ready");

    // Автоподключение при загрузке
    api.connect();
})();
