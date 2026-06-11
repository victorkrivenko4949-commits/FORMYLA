// FORMYLA — Conference UI module.
//
// Загружается на странице конференции (templates/conference.html).
// Управляет UI: лобби, видеосетка, тулбар, панели участников и чата, реакции.
// Общается с iframe-движком (call_engine.html) через postMessage.
//
// postMessage protocol defined in call_engine.html.
//
// API:
//   window.__conferenceUI.init(containerEl) — инициализировать UI
//   window.__conferenceUI.destroy() — очистить

(function () {
    "use strict";

    if (window.__conferenceUI) return;
    window.__conferenceUI = { init: _init, destroy: _destroy };

    var IFrameId = "wbCallEngine";

    // ── State ──────────────────────────────────────────────────────────
    var st = {
        inCall: false,
        roomCode: null,
        peerId: null,
        myRole: "participant",
        myName: null,
        myUserId: null,
        participants: {},
        flags: {},
        micOn: true,
        camOn: true,
        screenSharing: false,
        handRaised: false,
        connected: false,
        joinInProgress: false,
    };

    var _container = null;
    var _lobbyEl = null;
    var _roomEl = null;
    var _videoGrid = null;
    var _toolbar = {};
    var _panels = {};
    var _chatMessages = [];
    var _reactionTimer = null;
    var _reactionQueue = [];

    // ── Helpers ────────────────────────────────────────────────────────

    function $id(id) { return document.getElementById(id); }

    function _el(tag, attrs, children) {
        var e = document.createElement(tag);
        if (attrs) {
            for (var k in attrs) {
                if (attrs.hasOwnProperty(k)) {
                    var v = attrs[k];
                    if (k === "className") {
                        e.className = v;
                    } else if (k === "style" && typeof v === "object") {
                        for (var sk in v) {
                            if (v.hasOwnProperty(sk)) e.style[sk] = v[sk];
                        }
                    } else if (k === "dataset" && typeof v === "object") {
                        for (var dk in v) {
                            if (v.hasOwnProperty(dk)) e.dataset[dk] = v[dk];
                        }
                    } else if (k.indexOf("on") === 0 && typeof v === "function") {
                        e.addEventListener(k.slice(2).toLowerCase(), v);
                    } else {
                        e.setAttribute(k, v);
                    }
                }
            }
        }
        if (children) {
            for (var i = 0; i < children.length; i++) {
                var c = children[i];
                if (typeof c === "string") {
                    e.appendChild(document.createTextNode(c));
                } else if (c) {
                    e.appendChild(c);
                }
            }
        }
        return e;
    }

    function _text(t) { return document.createTextNode(t); }

    function _empty(el) {
        while (el.firstChild) el.removeChild(el.firstChild);
    }

    function _toggleClass(el, cls, force) {
        if (!el) return;
        el.classList.toggle(cls, force);
    }

    function _getIframe() {
        var ifr = document.getElementById(IFrameId);
        if (!ifr) {
            ifr = document.querySelector("iframe[src*='call_engine']");
        }
        return ifr;
    }

    function _postToIframe(msg) {
        var ifr = _getIframe();
        if (ifr && ifr.contentWindow) {
            try {
                ifr.contentWindow.postMessage(msg, "*");
            } catch (e) {
                console.warn("[wb_ui] postMessage error:", e);
            }
        }
    }

    function _log() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_ui]");
        console.log.apply(console, args);
    }

    function _warn() {
        var args = Array.prototype.slice.call(arguments);
        args.unshift("[wb_ui]");
        console.warn.apply(console, args);
    }

    // ── postMessage listener (from iframe) ────────────────────────────

    function _onIframeMessage(event) {
        var msg = event.data;
        if (!msg || !msg.type) return;

        switch (msg.type) {
            case "ws-connected":
                st.connected = true;
                _updateConnectionStatus();
                // Если join был в ожидании (joinInProgress) — повторяем
                if (st.joinInProgress && st.roomCode && !st.inCall) {
                    _log("ws-connected: retrying pending join for room", st.roomCode);
                    setTimeout(function () {
                        if (st.joinInProgress && !st.inCall) {
                            _postToIframe({
                                type: "join",
                                room: st.roomCode,
                                name: st.myName || "User",
                                user_id: st.myUserId || null,
                            });
                        }
                    }, 100);
                }
                break;

            case "ws-disconnected":
                st.connected = false;
                _updateConnectionStatus();
                break;

            case "joined":
                st.peerId = msg.peer_id;
                st.myRole = msg.role || "participant";
                st.participants = {};
                if (msg.participants) {
                    for (var i = 0; i < msg.participants.length; i++) {
                        var p = msg.participants[i];
                        st.participants[p.peer_id] = p;
                    }
                }
                st.flags = msg.flags || {};
                st.joinInProgress = false;
                st.inCall = true;
                _onJoined();
                break;

            case "join-error":
                st.joinInProgress = false;
                _showError("\u041E\u0448\u0438\u0431\u043A\u0430 \u0432\u0445\u043E\u0434\u0430: " + (msg.reason || "\u043D\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043D\u0430\u044F \u043E\u0448\u0438\u0431\u043A\u0430"));
                break;

            case "participant-joined":
                if (msg.peer_id) {
                    st.participants[msg.peer_id] = msg;
                    _onParticipantJoined(msg);
                }
                break;

            case "participant-left":
                if (msg.peer_id) {
                    delete st.participants[msg.peer_id];
                    _onParticipantLeft(msg.peer_id);
                }
                break;

            case "signal":
                break;

            case "remote-track":
                _onRemoteTrack(msg.peerId, msg.kind, msg.streams);
                break;

            case "mute-changed":
                if (msg.target && st.participants[msg.target]) {
                    if (msg.kind === "mic") {
                        st.participants[msg.target].mic_on = !msg.state;
                    } else if (msg.kind === "cam") {
                        st.participants[msg.target].cam_on = !msg.state;
                    }
                    _updateParticipantTile(msg.target);
                }
                break;

            case "ice-state":
                if (msg.peerId) {
                    _updateTileState(msg.peerId, msg.state);
                }
                break;

            case "kicked":
                _onKicked();
                break;

            case "role-changed":
                if (msg.target) {
                    if (st.participants[msg.target]) {
                        st.participants[msg.target].role = msg.role;
                    }
                    if (msg.target === st.peerId) {
                        st.myRole = msg.role;
                    }
                    _updateParticipantTile(msg.target);
                    _updateToolbar();
                    _updateParticipantPanel();
                }
                break;

            case "host-changed":
                if (msg.new_host) {
                    st.flags.host_id = msg.new_host;
                    if (st.participants[msg.new_host]) {
                        st.participants[msg.new_host].role = "host";
                    }
                    if (msg.old_host && st.participants[msg.old_host]) {
                        st.participants[msg.old_host].role = "participant";
                    }
                    _updateParticipantPanel();
                }
                break;

            case "chat-msg":
                _onChatMessage(msg);
                break;

            case "reaction":
                _onReaction(msg);
                break;

            case "hand-raise":
                if (msg.peer_id && st.participants[msg.peer_id]) {
                    st.participants[msg.peer_id].hand_raised = msg.on;
                    _updateParticipantTile(msg.peer_id);
                    _updateParticipantPanel();
                }
                break;

            case "screen-share":
                if (msg.peer_id && st.participants[msg.peer_id]) {
                    st.participants[msg.peer_id].screen_sharing = msg.on;
                    _updateParticipantTile(msg.peer_id);
                }
                if (msg.peer_id === st.peerId) {
                    st.screenSharing = !!msg.on;
                    _updateToolbar();
                }
                break;

            case "flag-changed":
                if (msg.flag !== undefined) {
                    st.flags[msg.flag] = msg.value;
                }
                break;

            case "room-state":
                st.participants = {};
                if (msg.participants) {
                    for (var j = 0; j < msg.participants.length; j++) {
                        var pp = msg.participants[j];
                        st.participants[pp.peer_id] = pp;
                    }
                }
                st.flags = msg.flags || {};
                _rebuildVideoGrid();
                _updateParticipantPanel();
                break;

            case "room-ended":
                _onRoomEnded();
                break;

            case "media-error":
                _showError("\u041E\u0448\u0438\u0431\u043A\u0430 \u0434\u043E\u0441\u0442\u0443\u043F\u0430 \u043A \u043C\u0438\u043A\u0440\u043E\u0444\u043E\u043D\u0443/\u043A\u0430\u043C\u0435\u0440\u0435");
                break;

            case "screen-share-started":
                st.screenSharing = true;
                _updateToolbar();
                _showToast("\u0414\u0435\u043C\u043E\u043D\u0441\u0442\u0440\u0430\u0446\u0438\u044F \u044D\u043A\u0440\u0430\u043D\u0430 \u0437\u0430\u043F\u0443\u0449\u0435\u043D\u0430");
                break;

            case "screen-share-stopped":
                st.screenSharing = false;
                _updateToolbar();
                break;

            case "screen-share-error":
                _showError("\u041E\u0448\u0438\u0431\u043A\u0430 \u0434\u0435\u043C\u043E\u043D\u0441\u0442\u0440\u0430\u0446\u0438\u0438 \u044D\u043A\u0440\u0430\u043D\u0430");
                break;

            case "local-stream-ready":
                // Engine сообщает что локальный поток готов — прикрепляем к local tile
                if (msg.stream) {
                    var localVid = document.getElementById("cf-video-local");
                    if (localVid && !localVid.srcObject) {
                        try {
                            localVid.srcObject = msg.stream;
                            localVid.play().catch(function () {});
                            _log("local stream attached from engine event");
                        } catch (e) {
                            _warn("attach local stream error:", e);
                        }
                    }
                }
                break;
        }
    }

    // ── Connection status ─────────────────────────────────────────────

    function _updateConnectionStatus() {
        var el = $id("cf-status");
        if (!el) return;
        if (st.connected) {
            el.textContent = "\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u043E";
            el.className = "cf-status cf-status--connected";
        } else {
            el.textContent = "\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435...";
            el.className = "cf-status cf-status--connecting";
        }
    }

    // ── Lobby ─────────────────────────────────────────────────────────

    function _buildLobby() {
        _lobbyEl = _el("div", { className: "cf-lobby" }, [
            _el("div", { className: "cf-lobby-card" }, [
                _el("h1", { className: "cf-lobby-title" }, ["\u041A\u043E\u043D\u0444\u0435\u0440\u0435\u043D\u0446\u0438\u044F"]),
                _el("p", { className: "cf-lobby-sub" }, ["\u0421\u043E\u0437\u0434\u0430\u0439\u0442\u0435 \u043A\u043E\u043C\u043D\u0430\u0442\u0443 \u0438\u043B\u0438 \u0432\u043E\u0439\u0434\u0438\u0442\u0435 \u043F\u043E \u043A\u043E\u0434\u0443"]),
                _el("div", { className: "cf-lobby-row" }, [
                    _el("input", { className: "cf-input", id: "cf-name-input", type: "text", placeholder: "\u0412\u0430\u0448\u0435 \u0438\u043C\u044F", maxLength: "32" }),
                ]),
                _el("div", { className: "cf-lobby-row" }, [
                    _el("button", { className: "cf-btn cf-btn--primary", id: "cf-create-btn", onClick: _onCreateRoom }, ["\u0421\u043E\u0437\u0434\u0430\u0442\u044C \u043A\u043E\u043C\u043D\u0430\u0442\u0443"]),
                ]),
                _el("div", { className: "cf-lobby-divider" }, [
                    _el("span", {}, ["\u0438\u043B\u0438"]),
                ]),
                _el("div", { className: "cf-lobby-row" }, [
                    _el("input", { className: "cf-input cf-input--code", id: "cf-code-input", type: "text", placeholder: "\u041A\u043E\u0434 \u043A\u043E\u043C\u043D\u0430\u0442\u044B", maxLength: "6", pattern: "[0-9]*", inputMode: "numeric" }),
                    _el("button", { className: "cf-btn cf-btn--secondary", id: "cf-join-btn", onClick: _onJoinRoom }, ["\u0412\u043E\u0439\u0442\u0438"]),
                ]),
                _el("div", { className: "cf-lobby-error", id: "cf-lobby-error", style: { display: "none" } }),
                _el("div", { className: "cf-lobby-status", id: "cf-status" }),
            ]),
        ]);
        _container.appendChild(_lobbyEl);

        // Auto-fill name from localStorage
        var savedName = localStorage.getItem("cf_username") || "";
        if (savedName) {
            $id("cf-name-input").value = savedName;
        }
    }

    function _onCreateRoom() {
        var name = ($id("cf-name-input").value || "").trim();
        if (!name) {
            _showLobbyError("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0438\u043C\u044F");
            return;
        }
        localStorage.setItem("cf_username", name);

        // Call HTTP API to create room
        var xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/conference/create-room", true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.onload = function () {
            if (xhr.status === 200) {
                var resp;
                try { resp = JSON.parse(xhr.responseText); } catch (e) { resp = null; }
                if (resp && resp.room) {
                    _joinRoom(resp.room, name);
                } else {
                    _showLobbyError("\u041E\u0448\u0438\u0431\u043A\u0430 \u0441\u043E\u0437\u0434\u0430\u043D\u0438\u044F \u043A\u043E\u043C\u043D\u0430\u0442\u044B");
                }
            } else {
                _showLobbyError("\u041E\u0448\u0438\u0431\u043A\u0430 \u0441\u0435\u0440\u0432\u0435\u0440\u0430");
            }
        };
        xhr.onerror = function () {
            _showLobbyError("\u041D\u0435\u0442 \u0441\u0432\u044F\u0437\u0438 \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u043E\u043C");
        };
        xhr.send(JSON.stringify({}));
    }

    function _onJoinRoom() {
        var name = ($id("cf-name-input").value || "").trim();
        var code = ($id("cf-code-input").value || "").trim();
        if (!name) {
            _showLobbyError("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u0438\u043C\u044F");
            return;
        }
        if (!code || code.length < 4) {
            _showLobbyError("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043A\u043E\u0434 \u043A\u043E\u043C\u043D\u0430\u0442\u044B");
            return;
        }
        localStorage.setItem("cf_username", name);
        _joinRoom(code, name);
    }

    function _joinRoom(roomCode, name) {
        st.roomCode = roomCode;
        st.myName = name;
        st.joinInProgress = true;

        // Get user_id from meta tag or session
        var userId = null;
        var meta = document.querySelector("meta[name='user-id']");
        if (meta) userId = meta.getAttribute("content");
        st.myUserId = userId;

        _postToIframe({ type: "join", room: roomCode, name: name, user_id: userId });
        _showLobbyError(""); // clear error
        _updateLobbyJoinState(true);
    }

    function _updateLobbyJoinState(joining) {
        var btn = $id("cf-create-btn");
        var btn2 = $id("cf-join-btn");
        if (joining) {
            if (btn) btn.disabled = true;
            if (btn2) btn2.disabled = true;
            _showLobbyError("\u041F\u043E\u0434\u043A\u043B\u044E\u0447\u0435\u043D\u0438\u0435...");
        } else {
            if (btn) btn.disabled = false;
            if (btn2) btn2.disabled = false;
        }
    }

    function _showLobbyError(msg) {
        var el = $id("cf-lobby-error");
        if (!el) return;
        if (msg) {
            el.textContent = msg;
            el.style.display = "";
        } else {
            el.style.display = "none";
        }
    }

    // ── On joined (show in-call UI) ────────────────────────────────────

    function _onJoined() {
        _log("joined room:", st.roomCode, "as", st.peerId, "role:", st.myRole);

        // Remove lobby, show in-call UI
        if (_lobbyEl) {
            _lobbyEl.style.display = "none";
        }

        _buildInCallUI();
        _updateToolbar();
        _updateParticipantPanel();
        _updateConnectionStatus();

        // Add existing participants to grid
        for (var pid in st.participants) {
            if (st.participants.hasOwnProperty(pid) && pid !== st.peerId) {
                _addVideoTile(pid, st.participants[pid]);
            }
        }
    }

    // ── In-Call UI ────────────────────────────────────────────────────

    function _buildInCallUI() {
        if (_roomEl) {
            _roomEl.style.display = "";
            return;
        }

        _roomEl = _el("div", { className: "cf-room" }, [
            // Header
            _el("div", { className: "cf-header" }, [
                _el("div", { className: "cf-header-left" }, [
                    _el("div", { className: "cf-room-code", id: "cf-room-code" }, [
                        _el("span", { className: "cf-room-code-label" }, ["\u041A\u043E\u043C\u043D\u0430\u0442\u0430: "]),
                        _el("span", { className: "cf-room-code-value", id: "cf-room-code-value" }),
                        _el("button", { className: "cf-icon-btn cf-icon-btn--small", onClick: _copyRoomCode, title: "\u041A\u043E\u043F\u0438\u0440\u043E\u0432\u0430\u0442\u044C \u043A\u043E\u0434" }, ["\uD83D\uDCCB"]),
                    ]),
                    _el("span", { className: "cf-connection-status", id: "cf-status" }),
                ]),
                _el("div", { className: "cf-header-right" }, [
                    _el("span", { className: "cf-timer", id: "cf-timer" }),
                ]),
            ]),
            // Video grid
            _el("div", { className: "cf-video-grid", id: "cf-video-grid" }, [
                // Local video tile (self)
            ]),
            // Bottom toolbar
            _el("div", { className: "cf-toolbar", id: "cf-toolbar" }, [
                _el("div", { className: "cf-toolbar-left" }, [
                    _el("button", { className: "cf-tb-btn cf-tb-btn--mic", id: "cf-tb-mic", onClick: _toggleMic, title: "\u041C\u0438\u043A\u0440\u043E\u0444\u043E\u043D" }, [
                        _el("span", { className: "cf-tb-icon", id: "cf-tb-mic-icon" }, ["\uD83C\uDF99"]),
                    ]),
                    _el("button", { className: "cf-tb-btn cf-tb-btn--cam", id: "cf-tb-cam", onClick: _toggleCam, title: "\u041A\u0430\u043C\u0435\u0440\u0430" }, [
                        _el("span", { className: "cf-tb-icon", id: "cf-tb-cam-icon" }, ["\uD83D\uDCF7"]),
                    ]),
                    _el("button", { className: "cf-tb-btn", id: "cf-tb-screen", onClick: _toggleScreenShare, title: "\u0414\u0435\u043C\u043E\u043D\u0441\u0442\u0440\u0430\u0446\u0438\u044F" }, [
                        _el("span", { className: "cf-tb-icon" }, ["\uD83D\uDDA5"]),
                    ]),
                ]),
                _el("div", { className: "cf-toolbar-center" }, [
                    _el("button", { className: "cf-tb-btn cf-tb-btn--hand", id: "cf-tb-hand", onClick: _toggleHandRaise, title: "\u041F\u043E\u0434\u043D\u044F\u0442\u044C \u0440\u0443\u043A\u0443" }, [
                        _el("span", { className: "cf-tb-icon" }, ["\u270B"]),
                    ]),
                    _el("button", { className: "cf-tb-btn cf-tb-btn--reactions", id: "cf-tb-reactions", onClick: _showReactionPicker, title: "\u0420\u0435\u0430\u043A\u0446\u0438\u0438" }, [
                        _el("span", { className: "cf-tb-icon" }, ["\uD83D\uDE0A"]),
                    ]),
                ]),
                _el("div", { className: "cf-toolbar-right" }, [
                    _el("button", { className: "cf-tb-btn cf-tb-btn--participants", id: "cf-tb-participants", onClick: _toggleParticipantsPanel, title: "\u0423\u0447\u0430\u0441\u0442\u043D\u0438\u043A\u0438" }, [
                        _el("span", { className: "cf-tb-icon" }, ["\uD83D\uDC65"]),
                        _el("span", { className: "cf-tb-badge", id: "cf-tb-pcount" }),
                    ]),
                    _el("button", { className: "cf-tb-btn cf-tb-btn--chat", id: "cf-tb-chat", onClick: _toggleChatPanel, title: "\u0427\u0430\u0442" }, [
                        _el("span", { className: "cf-tb-icon" }, ["\uD83D\uDCAC"]),
                        _el("span", { className: "cf-tb-badge cf-tb-badge--unread", id: "cf-tb-chat-unread", style: { display: "none" } }),
                    ]),
                    _el("button", { className: "cf-tb-btn cf-tb-btn--end", id: "cf-tb-end", onClick: _endCall, title: "\u0417\u0430\u0432\u0435\u0440\u0448\u0438\u0442\u044C" }, [
                        _el("span", { className: "cf-tb-icon" }, ["\uD83D\uDCDE"]),
                    ]),
                ]),
            ]),
            // Side panels
            _el("div", { className: "cf-panels-overlay", id: "cf-panels-overlay", onClick: _closePanels }),
            _el("div", { className: "cf-panel cf-panel--participants", id: "cf-panel-participants" }, [
                _el("div", { className: "cf-panel-header" }, [
                    _el("span", { className: "cf-panel-title" }, ["\u0423\u0447\u0430\u0441\u0442\u043D\u0438\u043A\u0438"]),
                    _el("button", { className: "cf-icon-btn", onClick: _toggleParticipantsPanel }, ["\u2716"]),
                ]),
                _el("div", { className: "cf-panel-body", id: "cf-participant-list" }),
            ]),
            _el("div", { className: "cf-panel cf-panel--chat", id: "cf-panel-chat" }, [
                _el("div", { className: "cf-panel-header" }, [
                    _el("span", { className: "cf-panel-title" }, ["\u0427\u0430\u0442"]),
                    _el("button", { className: "cf-icon-btn", onClick: _toggleChatPanel }, ["\u2716"]),
                ]),
                _el("div", { className: "cf-panel-body cf-chat-messages", id: "cf-chat-messages" }),
                _el("div", { className: "cf-chat-input-row" }, [
                    _el("input", { className: "cf-input cf-chat-input", id: "cf-chat-input", type: "text", placeholder: "\u041D\u0430\u043F\u0438\u0448\u0438\u0442\u0435 \u0441\u043E\u043E\u0431\u0449\u0435\u043D\u0438\u0435...", onKeydown: _onChatKeydown }),
                    _el("button", { className: "cf-btn cf-btn--small", onClick: _sendChat }, ["\u2192"]),
                ]),
            ]),
            // Reaction overlay
            _el("div", { className: "cf-reactions-overlay", id: "cf-reactions-overlay" }),
            // Reaction picker (hidden by default)
            _el("div", { className: "cf-reaction-picker", id: "cf-reaction-picker", style: { display: "none" } }),
            // Toast container
            _el("div", { className: "cf-toast-container", id: "cf-toast-container" }),
        ]);

        _container.appendChild(_roomEl);
        $id("cf-room-code-value").textContent = st.roomCode;
        _addLocalTile();
    }

    // ── Local video tile ──────────────────────────────────────────────

    function _addLocalTile() {
        var grid = $id("cf-video-grid");
        if (!grid) return;

        // Check if local tile already exists
        if ($id("cf-tile-local")) return;

        var name = localStorage.getItem("cf_username") || "\u042F";
        var tile = _el("div", { className: "cf-video-tile cf-video-tile--local", id: "cf-tile-local" }, [
            _el("video", { className: "cf-video-el", id: "cf-video-local", autoplay: true, muted: true, playsInline: true }),
            _el("div", { className: "cf-tile-info" }, [
                _el("span", { className: "cf-tile-name" }, [name]),
                _el("span", { className: "cf-tile-status", id: "cf-tile-local-status" }),
            ]),
            _el("div", { className: "cf-tile-mic-off", id: "cf-tile-local-mic-off", style: { display: "none" } }, ["\uD83C\uDF99\uFE0B"]),
        ]);

        // Insert local tile first
        if (grid.firstChild) {
            grid.insertBefore(tile, grid.firstChild);
        } else {
            grid.appendChild(tile);
        }

        // Get local stream from iframe
        _requestLocalStream();
    }

    function _requestLocalStream() {
        // Try to get local stream directly from iframe engine
        var ifr = _getIframe();
        if (ifr && ifr.contentWindow && ifr.contentWindow.__wbEngine) {
            try {
                var stream = ifr.contentWindow.__wbEngine.getLocalStream();
                if (stream) {
                    var localVid = document.getElementById("cf-video-local");
                    if (localVid) {
                        localVid.srcObject = stream;
                        localVid.play().catch(function () {});
                        _log("local stream attached directly");
                        return;
                    }
                }
            } catch (e) {
                _warn("direct stream access error:", e);
            }
        }
        // Fallback: request via postMessage
        _postToIframe({ type: "get-local-stream" });
        // Retry after a short delay
        setTimeout(function () {
            var ifr2 = _getIframe();
            if (ifr2 && ifr2.contentWindow && ifr2.contentWindow.__wbEngine) {
                try {
                    var s = ifr2.contentWindow.__wbEngine.getLocalStream();
                    if (s) {
                        var lv = document.getElementById("cf-video-local");
                        if (lv && !lv.srcObject) {
                            lv.srcObject = s;
                            lv.play().catch(function () {});
                        }
                    }
                } catch (e) {}
            }
        }, 1000);
    }

    // ── Remote video tiles ────────────────────────────────────────────

    function _addVideoTile(peerId, participant) {
        var grid = $id("cf-video-grid");
        if (!grid) return;

        var existing = $id("cf-tile-" + peerId);
        if (existing) return;

        var name = participant.name || peerId;
        var tile = _el("div", { className: "cf-video-tile", id: "cf-tile-" + peerId, dataset: { peerId: peerId } }, [
            _el("video", { className: "cf-video-el", id: "cf-video-" + peerId, autoplay: true, playsInline: true }),
            _el("div", { className: "cf-tile-info" }, [
                _el("span", { className: "cf-tile-name" }, [name]),
                _el("span", { className: "cf-tile-role-badge", id: "cf-role-" + peerId, style: { display: "none" } }),
            ]),
            _el("div", { className: "cf-tile-status-icons", id: "cf-icons-" + peerId }),
            _el("div", { className: "cf-tile-hand-raised", id: "cf-hand-" + peerId, style: { display: "none" } }, ["\u270B"]),
        ]);

        grid.appendChild(tile);
        _updateParticipantTile(peerId);
    }

    function _removeVideoTile(peerId) {
        var tile = $id("cf-tile-" + peerId);
        if (tile && tile.parentNode) {
            tile.parentNode.removeChild(tile);
        }
    }

    function _updateParticipantTile(peerId) {
        var p = st.participants[peerId];
        if (!p) return;

        var roleEl = $id("cf-role-" + peerId);
        if (roleEl) {
            if (p.role === "host") {
                roleEl.textContent = "\u041E\u0440\u0433\u0430\u043D\u0438\u0437\u0430\u0442\u043E\u0440";
                roleEl.style.display = "";
            } else if (p.role === "co-host") {
                roleEl.textContent = "\u0421\u043E\u043E\u0440\u0433.";
                roleEl.style.display = "";
            } else {
                roleEl.style.display = "none";
            }
        }

        var iconsEl = $id("cf-icons-" + peerId);
        if (iconsEl) {
            var icons = [];
            if (!p.mic_on) icons.push("\uD83C\uDF99\uFE0B");
            if (!p.cam_on) icons.push("\uD83D\uDCF7\uFE0B");
            if (p.screen_sharing) icons.push("\uD83D\uDDA5\uFE0F");
            iconsEl.textContent = icons.join(" ") || "";
        }

        var handEl = $id("cf-hand-" + peerId);
        if (handEl) {
            handEl.style.display = p.hand_raised ? "" : "none";
        }
    }

    function _updateTileState(peerId, state) {
        var tile = $id("cf-tile-" + peerId);
        if (!tile) return;

        // Remove all state classes
        tile.className = tile.className.replace(/cf-video-tile--\w+/g, "").trim();
        if (state === "connected") {
            tile.classList.add("cf-video-tile--connected");
        } else if (state === "checking" || state === "new") {
            tile.classList.add("cf-video-tile--connecting");
        } else if (state === "disconnected" || state === "failed") {
            tile.classList.add("cf-video-tile--disconnected");
        }
    }

    function _rebuildVideoGrid() {
        var grid = $id("cf-video-grid");
        if (!grid) return;

        // Remove all remote tiles
        var tiles = grid.querySelectorAll(".cf-video-tile");
        for (var i = tiles.length - 1; i >= 0; i--) {
            var tile = tiles[i];
            if (tile.id !== "cf-tile-local") {
                tile.parentNode.removeChild(tile);
            }
        }

        // Re-add remote tiles
        for (var pid in st.participants) {
            if (st.participants.hasOwnProperty(pid) && pid !== st.peerId) {
                _addVideoTile(pid, st.participants[pid]);
            }
        }
    }

    // ── Remote track handling ─────────────────────────────────────────

    function _onRemoteTrack(peerId, kind, streams) {
        var videoEl = $id("cf-video-" + peerId);
        if (!videoEl) {
            // Tile might not exist yet, try again after a short delay
            setTimeout(function () {
                var ve = $id("cf-video-" + peerId);
                if (ve && streams && streams[0]) {
                    _attachStream(ve, streams[0]);
                }
            }, 200);
            return;
        }
        if (streams && streams[0]) {
            _attachStream(videoEl, streams[0]);
        }
    }

    function _attachStream(videoEl, stream) {
        if (!videoEl || !stream) return;
        try {
            videoEl.srcObject = stream;
        } catch (e) {
            // Fallback for older browsers
            videoEl.src = URL.createObjectURL(stream);
        }
    }

    // ── Participant joining/leaving ────────────────────────────────────

    function _onParticipantJoined(data) {
        _log("participant joined:", data.peer_id, data.name);
        _addVideoTile(data.peer_id, data);
        _updateParticipantPanel();
        _showToast((data.name || "\u0423\u0447\u0430\u0441\u0442\u043D\u0438\u043A") + " \u0432\u043E\u0448\u0435\u043B");
    }

    function _onParticipantLeft(peerId) {
        _log("participant left:", peerId);
        _removeVideoTile(peerId);
        _updateParticipantPanel();
        var name = peerId; // fallback
        _showToast("\u0423\u0447\u0430\u0441\u0442\u043D\u0438\u043A \u0432\u044B\u0448\u0435\u043B");
    }

    // ── Toolbar actions ───────────────────────────────────────────────

    function _toggleMic() {
        st.micOn = !st.micOn;
        _postToIframe({ type: "mute", kind: "mic", state: !st.micOn });
        _updateToolbar();
        _updateLocalTileStatus();
    }

    function _toggleCam() {
        st.camOn = !st.camOn;
        _postToIframe({ type: "mute", kind: "cam", state: !st.camOn });
        _updateToolbar();
        _updateLocalTileStatus();
    }

    function _toggleScreenShare() {
        if (st.screenSharing) {
            _postToIframe({ type: "screen-share", action: "stop" });
        } else {
            _postToIframe({ type: "screen-share", action: "start" });
        }
    }

    function _toggleHandRaise() {
        st.handRaised = !st.handRaised;
        _postToIframe({ type: "hand-raise", on: st.handRaised });
        _updateToolbar();
    }

    function _updateToolbar() {
        var micBtn = $id("cf-tb-mic");
        var camBtn = $id("cf-tb-cam");
        var handBtn = $id("cf-tb-hand");

        if (micBtn) _toggleClass(micBtn, "cf-tb-btn--off", !st.micOn);
        if (camBtn) _toggleClass(camBtn, "cf-tb-btn--off", !st.camOn);
        if (handBtn) _toggleClass(handBtn, "cf-tb-btn--active", st.handRaised);

        var micIcon = $id("cf-tb-mic-icon");
        if (micIcon) micIcon.textContent = st.micOn ? "\uD83C\uDF99" : "\uD83C\uDF99\uFE0B";
        var camIcon = $id("cf-tb-cam-icon");
        if (camIcon) camIcon.textContent = st.camOn ? "\uD83D\uDCF7" : "\uD83D\uDCF7\uFE0B";

        // Update participant count
        var countEl = $id("cf-tb-pcount");
        if (countEl) {
            var count = Object.keys(st.participants).length + 1; // +1 for self
            countEl.textContent = count;
        }
    }

    function _updateLocalTileStatus() {
        var statusEl = $id("cf-tile-local-status");
        if (statusEl) {
            var parts = [];
            if (!st.micOn) parts.push("\u043C\u0438\u043A \u0432\u044B\u043A\u043B");
            if (!st.camOn) parts.push("\u043A\u0430\u043C \u0432\u044B\u043A\u043B");
            statusEl.textContent = parts.join(", ");
        }
        var micOffEl = $id("cf-tile-local-mic-off");
        if (micOffEl) {
            micOffEl.style.display = st.micOn ? "none" : "";
        }
    }

    // ── Participant panel ─────────────────────────────────────────────

    function _toggleParticipantsPanel() {
        var panel = $id("cf-panel-participants");
        var overlay = $id("cf-panels-overlay");
        if (!panel) return;
        var isOpen = panel.classList.contains("cf-panel--open");
        _closePanels();
        if (!isOpen) {
            panel.classList.add("cf-panel--open");
            if (overlay) overlay.style.display = "";
            _updateParticipantPanel();
        }
    }

    function _updateParticipantPanel() {
        var list = $id("cf-participant-list");
        if (!list) return;

        _empty(list);

        // Sort: hosts first, then co-hosts, then participants
        var items = [];
        for (var pid in st.participants) {
            if (st.participants.hasOwnProperty(pid)) {
                items.push(st.participants[pid]);
            }
        }
        // Add self
        var myName = localStorage.getItem("cf_username") || "\u042F";
        items.push({ peer_id: st.peerId, name: myName, role: st.myRole, mic_on: st.micOn, cam_on: st.camOn, hand_raised: st.handRaised, screen_sharing: st.screenSharing });

        items.sort(function (a, b) {
            var order = { host: 0, "co-host": 1, participant: 2 };
            return (order[a.role] || 2) - (order[b.role] || 2);
        });

        for (var i = 0; i < items.length; i++) {
            var p = items[i];
            var isMe = p.peer_id === st.peerId;
            var row = _buildParticipantRow(p, isMe);
            list.appendChild(row);
        }
    }

    function _buildParticipantRow(p, isMe) {
        var nameText = p.name || p.peer_id || "?";
        if (isMe) nameText += " (\u042F)";

        var roleLabel = "";
        if (p.role === "host") roleLabel = "\u041E\u0440\u0433.";
        else if (p.role === "co-host") roleLabel = "\u0421\u043E\u043E\u0440\u0433.";

        var statusIcons = [];
        if (!p.mic_on) statusIcons.push("\uD83C\uDF99\uFE0B");
        if (!p.cam_on) statusIcons.push("\uD83D\uDCF7\uFE0B");
        if (p.screen_sharing) statusIcons.push("\uD83D\uDDA5\uFE0F");
        if (p.hand_raised) statusIcons.push("\u270B");

        var children = [
            _el("span", { className: "cf-participant-name" }, [nameText]),
        ];

        if (roleLabel) {
            children.push(_el("span", { className: "cf-participant-role" }, [roleLabel]));
        }

        if (statusIcons.length) {
            children.push(_el("span", { className: "cf-participant-status" }, [statusIcons.join(" ")]));
        }

        // Admin controls (only for host/co-host viewing non-self participants)
        if (!isMe && (st.myRole === "host" || st.myRole === "co-host")) {
            var adminBtns = [];
            adminBtns.push(_el("button", {
                className: "cf-admin-btn",
                title: "\u0417\u0430\u0433\u043B\u0443\u0448\u0438\u0442\u044C \u043C\u0438\u043A",
                onClick: (function (pid) { return function () { _postToIframe({ type: "mute", kind: "mic", state: true, target: pid }); }; })(p.peer_id)
            }, ["\uD83C\uDF99\uFE0B"]));

            adminBtns.push(_el("button", {
                className: "cf-admin-btn",
                title: "\u041E\u0442\u043A\u043B\u044E\u0447\u0438\u0442\u044C \u043A\u0430\u043C\u0435\u0440\u0443",
                onClick: (function (pid) { return function () { _postToIframe({ type: "mute", kind: "cam", state: true, target: pid }); }; })(p.peer_id)
            }, ["\uD83D\uDCF7\uFE0B"]));

            // Kick (host/co-host)
            if (st.myRole === "host" || (st.myRole === "co-host" && p.role !== "host")) {
                adminBtns.push(_el("button", {
                    className: "cf-admin-btn cf-admin-btn--danger",
                    title: "\u0423\u0434\u0430\u043B\u0438\u0442\u044C",
                    onClick: (function (pid) { return function () {
                        if (confirm("\u0423\u0434\u0430\u043B\u0438\u0442\u044C \u0443\u0447\u0430\u0441\u0442\u043D\u0438\u043A\u0430?")) {
                            _postToIframe({ type: "kick", target: pid });
                        }
                    }; })(p.peer_id)
                }, ["\u2716"]));
            }

            // Assign co-host (host only)
            if (st.myRole === "host" && p.role === "participant") {
                adminBtns.push(_el("button", {
                    className: "cf-admin-btn",
                    title: "\u041D\u0430\u0437\u043D\u0430\u0447\u0438\u0442\u044C \u0441\u043E\u043E\u0440\u0433\u0430\u043D\u0438\u0437\u0430\u0442\u043E\u0440\u043E\u043C",
                    onClick: (function (pid) { return function () {
                        _postToIframe({ type: "role-change", target: pid, role: "co-host" });
                    }; })(p.peer_id)
                }, ["\u2B50"]));
            }

            children.push(_el("div", { className: "cf-participant-admin" }, adminBtns));
        }

        return _el("div", { className: "cf-participant-row" + (isMe ? " cf-participant-row--me" : "") }, children);
    }

    // ── Chat ──────────────────────────────────────────────────────────

    function _toggleChatPanel() {
        var panel = $id("cf-panel-chat");
        var overlay = $id("cf-panels-overlay");
        if (!panel) return;
        var isOpen = panel.classList.contains("cf-panel--open");
        _closePanels();
        if (!isOpen) {
            panel.classList.add("cf-panel--open");
            if (overlay) overlay.style.display = "";
            var unread = $id("cf-tb-chat-unread");
            if (unread) unread.style.display = "none";
            // Focus input
            var input = $id("cf-chat-input");
            if (input) input.focus();
        }
    }

    function _onChatMessage(msg) {
        _chatMessages.push(msg);
        _appendChatMessage(msg, false);

        // Show unread badge if chat panel is closed
        var panel = $id("cf-panel-chat");
        if (panel && !panel.classList.contains("cf-panel--open")) {
            var unread = $id("cf-tb-chat-unread");
            if (unread) {
                var count = parseInt(unread.textContent || "0", 10) + 1;
                unread.textContent = count > 9 ? "9+" : count;
                unread.style.display = "";
            }
        }
    }

    function _appendChatMessage(msg, isSelf) {
        var container = $id("cf-chat-messages");
        if (!container) return;

        var name = isSelf ? "\u042F" : (msg.name || msg.from || "\u0423\u0447\u0430\u0441\u0442\u043D\u0438\u043A");
        var time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

        var bubble = _el("div", { className: "cf-chat-msg" + (isSelf ? " cf-chat-msg--self" : "") }, [
            _el("div", { className: "cf-chat-msg-header" }, [
                _el("span", { className: "cf-chat-msg-name" }, [name]),
                _el("span", { className: "cf-chat-msg-time" }, [time]),
            ]),
            _el("div", { className: "cf-chat-msg-text" }, [msg.text || ""]),
        ]);

        container.appendChild(bubble);
        container.scrollTop = container.scrollHeight;
    }

    function _onChatKeydown(e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            _sendChat();
        }
    }

    function _sendChat() {
        var input = $id("cf-chat-input");
        if (!input) return;
        var text = input.value.trim();
        if (!text) return;

        _postToIframe({ type: "chat-msg", text: text });
        _appendChatMessage({ text: text, name: "\u042F" }, true);
        _chatMessages.push({ text: text, name: "\u042F", from: st.peerId });
        input.value = "";
    }

    // ── Reactions ─────────────────────────────────────────────────────

    var REACTIONS = ["\uD83D\uDC4D", "\u2764\uFE0F", "\uD83D\uDE02", "\uD83D\uDC4F", "\uD83C\uDF89", "\uD83D\uDE0D", "\uD83D\uDE2E", "\uD83D\uDE22"];

    function _showReactionPicker() {
        var picker = $id("cf-reaction-picker");
        if (!picker) return;

        if (picker.style.display !== "none") {
            picker.style.display = "none";
            return;
        }

        _empty(picker);
        for (var i = 0; i < REACTIONS.length; i++) {
            (function (emoji) {
                picker.appendChild(_el("button", {
                    className: "cf-reaction-btn",
                    onClick: function () {
                        _postToIframe({ type: "reaction", emoji: emoji });
                        _showFloatingReaction(emoji, true);
                        picker.style.display = "none";
                    }
                }, [emoji]));
            })(REACTIONS[i]);
        }

        picker.style.display = "";
    }

    function _onReaction(msg) {
        if (msg.emoji) {
            _showFloatingReaction(msg.emoji, false);
        }
    }

    function _showFloatingReaction(emoji, isSelf) {
        var overlay = $id("cf-reactions-overlay");
        if (!overlay) return;

        var el = _el("div", { className: "cf-float-reaction" + (isSelf ? " cf-float-reaction--self" : "") }, [emoji]);
        el.style.left = (20 + Math.random() * 60) + "%";
        overlay.appendChild(el);

        // Remove after animation
        setTimeout(function () {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, 2000);
    }

    // ── Toast notifications ───────────────────────────────────────────

    function _showToast(msg) {
        var container = $id("cf-toast-container");
        if (!container) return;

        var toast = _el("div", { className: "cf-toast" }, [msg]);
        container.appendChild(toast);

        setTimeout(function () {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 3000);
    }

    function _showError(msg) {
        _showToast("\u26A0\uFE0F " + msg);
        _log("error:", msg);
    }

    // ── Panels close ──────────────────────────────────────────────────

    function _closePanels() {
        var panels = document.querySelectorAll(".cf-panel");
        for (var i = 0; i < panels.length; i++) {
            panels[i].classList.remove("cf-panel--open");
        }
        var overlay = $id("cf-panels-overlay");
        if (overlay) overlay.style.display = "none";

        var picker = $id("cf-reaction-picker");
        if (picker) picker.style.display = "none";
    }

    // ── Copy room code ────────────────────────────────────────────────

    function _copyRoomCode() {
        if (!st.roomCode) return;
        var textarea = document.createElement("textarea");
        textarea.value = st.roomCode;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand("copy");
            _showToast("\u041A\u043E\u0434 \u0441\u043A\u043E\u043F\u0438\u0440\u043E\u0432\u0430\u043D");
        } catch (e) {
            _showError("\u041D\u0435 \u0443\u0434\u0430\u043B\u043E\u0441\u044C \u0441\u043A\u043E\u043F\u0438\u0440\u043E\u0432\u0430\u0442\u044C");
        }
        document.body.removeChild(textarea);
    }

    // ── End call / kicked / room ended ────────────────────────────────

    function _endCall() {
        _postToIframe({ type: "leave" });
        _resetToLobby();
    }

    function _onKicked() {
        _showToast("\u0412\u0430\u0441 \u0443\u0434\u0430\u043B\u0438\u043B\u0438 \u0438\u0437 \u043A\u043E\u043D\u0444\u0435\u0440\u0435\u043D\u0446\u0438\u0438");
        _resetToLobby();
    }

    function _onRoomEnded() {
        _showToast("\u041A\u043E\u043D\u0444\u0435\u0440\u0435\u043D\u0446\u0438\u044F \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043D\u0430");
        _resetToLobby();
    }

    function _resetToLobby() {
        st.inCall = false;
        st.participants = {};
        st.peerId = null;
        st.screenSharing = false;
        st.handRaised = false;
        st.micOn = true;
        st.camOn = true;
        st.roomCode = null;

        if (_roomEl) {
            _roomEl.style.display = "none";
            // Clean up video elements
            var videos = _roomEl.querySelectorAll("video");
            for (var i = 0; i < videos.length; i++) {
                try { videos[i].srcObject = null; } catch (e) {}
            }
        }

        if (_lobbyEl) {
            _lobbyEl.style.display = "";
            _showLobbyError("");
            _updateLobbyJoinState(false);
            $id("cf-code-input").value = "";
        }

        _updateConnectionStatus();
    }

    // ── Init / Destroy ────────────────────────────────────────────────

    function _init(containerEl) {
        if (_container) return; // already initialized
        _container = containerEl;

        window.addEventListener("message", _onIframeMessage);

        // ── beforeunload: сохраняем состояние для PiP при уходе со страницы ──
        window.addEventListener("beforeunload", function () {
            if (st.inCall && st.roomCode) {
                try {
                    sessionStorage.setItem("cf_pip_state", JSON.stringify({
                        room: st.roomCode,
                        name: st.myName || "User",
                        user_id: st.myUserId || null,
                    }));
                } catch (e) {
                    _warn("failed to save PiP state:", e);
                }
            }
        });

        _buildLobby();
        _updateConnectionStatus();

        // ── Восстановление из PiP или URL-параметра ──
        // Приоритет: sessionStorage (возврат из PiP) > URL ?room=
        var savedRoom = null;
        var savedName = null;
        var savedUserId = null;

        var pipSaved = sessionStorage.getItem("cf_pip_state");
        if (pipSaved) {
            try {
                var ps = JSON.parse(pipSaved);
                if (ps && ps.room) {
                    savedRoom = ps.room;
                    savedName = ps.name || null;
                    savedUserId = ps.user_id || null;
                }
            } catch (e) {
                _warn("failed to parse PiP state:", e);
            }
            sessionStorage.removeItem("cf_pip_state");
        }

        // Если нет в sessionStorage — проверяем URL ?room=
        if (!savedRoom) {
            var urlParams = new URLSearchParams(window.location.search);
            var urlRoom = urlParams.get("room");
            if (urlRoom) {
                savedRoom = urlRoom;
            }
        }

        if (savedRoom) {
            // Автоматически заходим в комнату
            var autoName = savedName || localStorage.getItem("cf_username") || "User";
            var nameInput = $id("cf-name-input");
            if (nameInput) nameInput.value = autoName;

            st.roomCode = savedRoom;
            st.myName = autoName;
            st.myUserId = savedUserId;
            st.joinInProgress = true;

            _log("auto-joining room from saved state:", savedRoom);
            // Небольшая задержка чтобы iframe успел загрузиться
            setTimeout(function () {
                _postToIframe({
                    type: "join",
                    room: savedRoom,
                    name: autoName,
                    user_id: savedUserId || null,
                });
                _updateLobbyJoinState(true);
            }, 400);
        }

        _log("conference UI initialized");
    }

    function _destroy() {
        window.removeEventListener("message", _onIframeMessage);
        if (_roomEl && _roomEl.parentNode) {
            _roomEl.parentNode.removeChild(_roomEl);
        }
        if (_lobbyEl && _lobbyEl.parentNode) {
            _lobbyEl.parentNode.removeChild(_lobbyEl);
        }
        _container = null;
        _lobbyEl = null;
        _roomEl = null;
        st = {
            inCall: false, roomCode: null, peerId: null, myRole: "participant",
            participants: {}, flags: {}, micOn: true, camOn: true,
            screenSharing: false, handRaised: false, connected: false,
            joinInProgress: false,
        };
        _log("conference UI destroyed");
    }

})();
