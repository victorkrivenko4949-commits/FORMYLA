// FORMYLA — WebRTC engine (mesh topology).
//
// Загружается внутри call_engine.html (iframe). Управляет RTCPeerConnection
// для каждого удалённого пира в mesh-сетке. Использует wb_signalling для
// обмена сигналами через WebSocket.
//
// API через window.__wbEngine (вызывается из call_engine.html):
//   join(room, name, user_id)
//   leave()
//   setMute(kind, state, target?)
//   sendSignal(to, signalType, data)
//   sendChat(text, to?)
//   sendReaction(emoji)
//   setHandRaise(on)
//   setScreenShare(on)
//   requestState()
//
// События в родительское окно (postMessage):
//   joined, participant-joined, participant-left, signal,
//   mute-changed, kicked, role-changed, chat-msg, reaction,
//   hand-raise, screen-share, flag-changed, room-state, room-ended,
//   ws-connected, ws-disconnected, join-error

(function () {
    "use strict";

    if (window.__wbEngine) return;

    var sig = window.__wbSignalling;

    // --- Конфигурация STUN/TURN ---
    var ICE_SERVERS = {
        iceServers: [
            { urls: "stun:stun.l.google.com:19302" },
            { urls: "stun:stun1.l.google.com:19302" },
        ],
    };

    // --- Состояние ---
    var myPeerId = null;
    var myRole = "participant";
    var myName = "User";
    var currentRoom = null;
    var localStream = null;
    var screenStream = null;

    // peerId -> RTCPeerConnection
    var peers = {};

    // peerId -> информация об участнике
    var participants = {};

    // Флаги комнаты
    var roomFlags = {};

    // MediaStreamTrack, которым делимся (для определения muted)
    var localAudioTrack = null;
    var localVideoTrack = null;

    var micMuted = false;
    var camMuted = false;
    var handRaised = false;
    var screenSharing = false;

    // --- Логирование ---
    function _log() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_engine]");
        console.log.apply(console, args);
    }

    function _warn() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_engine]");
        console.warn.apply(console, args);
    }

    function _error() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_engine]");
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

    // --- Получить медиапоток ---
    function _getUserMedia() {
        if (localStream) return Promise.resolve(localStream);

        return navigator.mediaDevices
            .getUserMedia({ audio: true, video: true })
            .then(function (stream) {
                localStream = stream;
                localAudioTrack = stream.getAudioTracks()[0] || null;
                localVideoTrack = stream.getVideoTracks()[0] || null;
                _log("local stream obtained");

                // Слушаем изменения mute/unmute на уровне треков
                if (localAudioTrack) {
                    localAudioTrack.addEventListener("mute", function () {
                        _postToParent("track-muted", { kind: "mic", state: true });
                    });
                    localAudioTrack.addEventListener("unmute", function () {
                        _postToParent("track-muted", { kind: "mic", state: false });
                    });
                }
                if (localVideoTrack) {
                    localVideoTrack.addEventListener("mute", function () {
                        _postToParent("track-muted", { kind: "cam", state: true });
                    });
                    localVideoTrack.addEventListener("unmute", function () {
                        _postToParent("track-muted", { kind: "cam", state: false });
                    });
                }

                // Добавляем треки во все существующие пир-коннекции
                for (var pid in peers) {
                    if (peers.hasOwnProperty(pid)) {
                        _addTracksToPeer(peers[pid], stream);
                    }
                }

                return stream;
            })
            .catch(function (err) {
                _error("getUserMedia error:", err.name, err.message);
                _postToParent("media-error", { error: err.name + ": " + err.message });
                // Продолжаем без локального видео (только приём)
                return null;
            });
    }

    function _addTracksToPeer(pc, stream) {
        if (!pc || !stream) return;
        var tracks = stream.getTracks();
        for (var i = 0; i < tracks.length; i++) {
            try {
                pc.addTrack(tracks[i], stream);
            } catch (e) {
                _warn("addTrack error:", e.message);
            }
        }
    }

    // --- Создание RTCPeerConnection для пира ---
    function _createPeerConnection(peerId) {
        if (peers[peerId]) {
            _warn("peer connection already exists for", peerId);
            return peers[peerId];
        }

        var pc;
        try {
            pc = new RTCPeerConnection(ICE_SERVERS);
        } catch (e) {
            _error("RTCPeerConnection creation failed:", e);
            return null;
        }

        peers[peerId] = pc;

        // Если у нас уже есть локальный поток — добавляем треки
        if (localStream) {
            _addTracksToPeer(pc, localStream);
        }

        // ICE candidate → отправляем пиру
        pc.onicecandidate = function (event) {
            if (event.candidate && sig) {
                sig.sendSignal(peerId, "ice", event.candidate);
            }
        };

        // Состояние ICE
        pc.oniceconnectionstatechange = function () {
            var state = pc.iceConnectionState;
            _log("ICE state for", peerId, ":", state);
            _postToParent("ice-state", { peerId: peerId, state: state });

            if (state === "disconnected" || state === "failed") {
                _removePeer(peerId);
            }
        };

        // Получение удалённого потока
        pc.ontrack = function (event) {
            _log("remote track from", peerId, ":", event.track.kind);
            _postToParent("remote-track", {
                peerId: peerId,
                kind: event.track.kind,
                streams: event.streams,
            });
        };

        // Уведомление о удалённом потоке
        pc.onaddstream = function (event) {
            _log("remote stream from", peerId);
        };

        return pc;
    }

    // --- Удаление пира ---
    function _removePeer(peerId) {
        var pc = peers[peerId];
        if (pc) {
            try {
                pc.close();
            } catch (e) { /* ignore */ }
            delete peers[peerId];
        }
        delete participants[peerId];
    }

    // --- Очистка всех соединений ---
    function _cleanup() {
        for (var pid in peers) {
            if (peers.hasOwnProperty(pid)) {
                _removePeer(pid);
            }
        }

        if (screenStream) {
            screenStream.getTracks().forEach(function (t) { t.stop(); });
            screenStream = null;
        }

        screenSharing = false;
        handRaised = false;
        myPeerId = null;
        myRole = "participant";
        currentRoom = null;
        participants = {};
        roomFlags = {};
    }

    // --- Обработка входящего offer ---
    function _handleOffer(from, data) {
        _log("handling offer from", from);
        var pc = _createPeerConnection(from);
        if (!pc) return;

        pc.setRemoteDescription(new RTCSessionDescription(data))
            .then(function () {
                return pc.createAnswer();
            })
            .then(function (answer) {
                return pc.setLocalDescription(answer);
            })
            .then(function () {
                if (sig) {
                    sig.sendSignal(from, "answer", pc.localDescription);
                }
            })
            .catch(function (err) {
                _error("handleOffer error:", err);
            });
    }

    // --- Обработка входящего answer ---
    function _handleAnswer(from, data) {
        var pc = peers[from];
        if (!pc) {
            _warn("no peer connection for answer from", from);
            return;
        }
        pc.setRemoteDescription(new RTCSessionDescription(data))
            .catch(function (err) {
                _error("handleAnswer error:", err);
            });
    }

    // --- Обработка ICE candidate ---
    function _handleIce(from, data) {
        var pc = peers[from];
        if (!pc) {
            _warn("no peer connection for ICE from", from);
            return;
        }
        try {
            pc.addIceCandidate(new RTCIceCandidate(data));
        } catch (e) {
            _warn("addIceCandidate error:", e.message);
        }
    }

    // --- Инициировать соединение с новым участником ---
    function _initiateConnection(peerId) {
        var pc = _createPeerConnection(peerId);
        if (!pc) return;

        pc.createOffer()
            .then(function (offer) {
                return pc.setLocalDescription(offer);
            })
            .then(function () {
                if (sig) {
                    sig.sendSignal(peerId, "offer", pc.localDescription);
                }
            })
            .catch(function (err) {
                _error("createOffer error:", err);
            });
    }

    // --- Обработка сигналов от signalling ---
    function _onSignal(from, signalType, data) {
        _log("signal from", from, "type:", signalType);

        if (signalType === "offer") {
            _handleOffer(from, data.data || data);
        } else if (signalType === "answer") {
            _handleAnswer(from, data.data || data);
        } else if (signalType === "ice") {
            _handleIce(from, data.data || data);
        }
    }

    // --- Обработка сообщений от signalling ---
    function _onMessage(eventName, data) {
        switch (eventName) {
            case "joined":
                myPeerId = data.peer_id;
                myRole = data.role || "participant";
                participants = {};
                if (data.participants) {
                    for (var i = 0; i < data.participants.length; i++) {
                        var p = data.participants[i];
                        participants[p.peer_id] = p;
                    }
                }
                roomFlags = data.flags || {};
                _log("joined room as", myPeerId, "role:", myRole);
                // После join — отправляем локальный поток родителю для PiP
                if (localStream) {
                    _postToParent("local-stream-ready", { stream: localStream });
                }
                break;

            case "participant-joined":
                if (data.peer_id && data.peer_id !== myPeerId) {
                    participants[data.peer_id] = data;
                    // Инициируем WebRTC-соединение с новым участником
                    _initiateConnection(data.peer_id);
                }
                break;

            case "participant-left":
                if (data.peer_id) {
                    _removePeer(data.peer_id);
                }
                break;

            case "mute-changed":
                // Обновляем состояние в participants
                if (data.target && participants[data.target]) {
                    if (data.kind === "mic") {
                        participants[data.target].mic_on = !data.state;
                    } else if (data.kind === "cam") {
                        participants[data.target].cam_on = !data.state;
                    }
                }
                break;

            case "role-changed":
                if (data.target && participants[data.target]) {
                    participants[data.target].role = data.role;
                }
                if (data.target === myPeerId) {
                    myRole = data.role;
                }
                break;

            case "hand-raise":
                if (data.peer_id && participants[data.peer_id]) {
                    participants[data.peer_id].hand_raised = data.on;
                }
                break;

            case "screen-share":
                if (data.peer_id && participants[data.peer_id]) {
                    participants[data.peer_id].screen_sharing = data.on;
                }
                break;

            case "board-selected":
                // Пробрасываем событие выбора доски в родительское окно
                _postToParent("board-selected", {
                    board_id: data.board_id,
                    board_name: data.board_name,
                    selected_by: data.selected_by,
                });
                break;

            case "flag-changed":
                if (data.flag && data.value !== undefined) {
                    roomFlags[data.flag] = data.value;
                }
                break;

            case "room-state":
                if (data.participants) {
                    participants = {};
                    for (var j = 0; j < data.participants.length; j++) {
                        var pp = data.participants[j];
                        participants[pp.peer_id] = pp;
                    }
                }
                roomFlags = data.flags || {};
                break;

            case "kicked":
                _cleanup();
                break;

            case "room-ended":
                _cleanup();
                break;
        }
    }

    // --- Публичное API (window.__wbEngine) ---

    var engine = {
        // Присоединиться к комнате
        join: function (room, name, user_id) {
            _log("join:", room, name);
            currentRoom = room;
            myName = name || "User";

            // Получаем медиа
            _getUserMedia().then(function () {
                if (sig) {
                    sig.join(room, myName, user_id);
                }
            });
        },

        // Покинуть комнату
        leave: function () {
            _log("leave");
            if (sig) sig.leave();
            _cleanup();
        },

        // Mute/unmute
        setMute: function (kind, state, target) {
            _log("setMute:", kind, state, target || "self");

            if (!target || target === myPeerId) {
                // Свой mute
                if (kind === "mic") {
                    micMuted = !!state;
                    if (localAudioTrack) {
                        localAudioTrack.enabled = !micMuted;
                    }
                } else if (kind === "cam") {
                    camMuted = !!state;
                    if (localVideoTrack) {
                        localVideoTrack.enabled = !camMuted;
                    }
                }
            }

            if (sig) {
                sig.setMute(kind, state, target);
            }
        },

        // Отправить WebRTC сигнал
        sendSignal: function (to, signalType, data) {
            if (sig) {
                sig.sendSignal(to, signalType, data);
            }
        },

        // Отправить сообщение чата
        sendChat: function (text, to) {
            if (sig) sig.sendChat(text, to);
        },

        // Реакция
        sendReaction: function (emoji) {
            if (sig) sig.sendReaction(emoji);
        },

        // Рука
        setHandRaise: function (on) {
            handRaised = !!on;
            if (sig) sig.setHandRaise(on);
        },

        // Демонстрация экрана
        setScreenShare: function (on) {
            if (on && !screenSharing) {
                _startScreenShare();
            } else if (!on && screenSharing) {
                _stopScreenShare();
            }
        },

        // Запросить состояние
        requestState: function () {
            if (sig) sig.requestState();
        },

        // Получить участников
        getParticipants: function () {
            return participants;
        },

        // Получить свой peer_id
        getPeerId: function () {
            return myPeerId;
        },

        // Получить свою роль
        getRole: function () {
            return myRole;
        },

        // Получить флаги комнаты
        getRoomFlags: function () {
            return roomFlags;
        },

        // Кикнуть участника
        kick: function (targetPeerId) {
            if (sig) sig.kick(targetPeerId);
        },

        // Сменить роль
        changeRole: function (targetPeerId, role) {
            if (sig) sig.changeRole(targetPeerId, role);
        },

        // Выбрать доску для всех участников
        selectBoard: function (boardId, boardName) {
            if (sig) sig.selectBoard(boardId, boardName);
        },

        // Установить флаг комнаты
        setFlag: function (flag, value) {
            if (sig) sig.setFlag(flag, value);
        },

        // Получить локальный MediaStream (для PiP в родительском окне)
        getLocalStream: function () {
            return localStream;
        },
    };

    // --- Демонстрация экрана ---
    function _startScreenShare() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
            _warn("screen share not supported");
            return;
        }

        navigator.mediaDevices
            .getDisplayMedia({ video: true, audio: true })
            .then(function (stream) {
                screenStream = stream;
                screenSharing = true;

                // Заменяем video track на screen track во всех пир-коннекциях
                var screenTrack = stream.getVideoTracks()[0];
                for (var pid in peers) {
                    if (peers.hasOwnProperty(pid)) {
                        var pc = peers[pid];
                        var sender = pc.getSenders().find(function (s) {
                            return s.track && s.track.kind === "video";
                        });
                        if (sender) {
                            sender.replaceTrack(screenTrack);
                        }
                    }
                }

                if (sig) sig.setScreenShare(true);

                // Когда пользователь завершит демонстрацию через системный UI
                screenTrack.onended = function () {
                    _stopScreenShare();
                };

                _postToParent("screen-share-started", {});
            })
            .catch(function (err) {
                _error("getDisplayMedia error:", err);
                _postToParent("screen-share-error", { error: err.message });
            });
    }

    function _stopScreenShare() {
        if (screenStream) {
            screenStream.getTracks().forEach(function (t) { t.stop(); });
            screenStream = null;
        }
        screenSharing = false;

        // Возвращаем обычную video track
        if (localVideoTrack) {
            for (var pid in peers) {
                if (peers.hasOwnProperty(pid)) {
                    var pc = peers[pid];
                    var sender = pc.getSenders().find(function (s) {
                        return s.track && s.track.kind === "video";
                    });
                    if (sender) {
                        sender.replaceTrack(localVideoTrack);
                    }
                }
            }
        }

        if (sig) sig.setScreenShare(false);
        _postToParent("screen-share-stopped", {});
    }

    // --- Регистрируем callbacks в signalling ---
    if (sig) {
        sig.onMessage(_onMessage);
        sig.onSignal(_onSignal);
    }

    window.__wbEngine = engine;
    _log("engine ready");
})();
