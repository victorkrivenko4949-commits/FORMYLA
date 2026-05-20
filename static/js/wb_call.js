// FORMYLA Whiteboard - 1-to-1 video call panel.
// WebRTC peer connection + HTTP polling signalling (/api/wb_call/*).
//
// UI: small floating panel anchored bottom-right of the whiteboard.
//     Click the "video" button in the top-bar -> enter / accept a room code ->
//     two participants see each other and talk while drawing on the same canvas.
//
// Notes
// -----
// * STUN-only.  Behind symmetric NAT (~10-15% of networks) the call may fail
//   to connect - for those cases a TURN server would be needed.  The code
//   reads window.WB_CALL_ICE if present, so TURN creds can be injected from
//   a server-rendered <script> tag later without touching this file.
// * Polling is 1 s while in a call;  bumped down to 2.5 s when idle.
// * Each tab is a separate "peer" - same user from two tabs counts as two.

(function () {
  "use strict";

  if (!("RTCPeerConnection" in window)) {
    console.warn("[wb_call] WebRTC not supported in this browser");
    return;
  }

  var POLL_INTERVAL_ACTIVE_MS = 1000;
  var POLL_INTERVAL_IDLE_MS   = 2500;
  var DEFAULT_ICE = [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" }
  ];

  // -- State --------------------------------------------------------------
  var roomId   = null;
  var peerId   = null;            // my id, given by /join
  var otherId  = null;            // remote peer id once known
  var pc       = null;            // RTCPeerConnection
  var localStream = null;
  var pollTimer = 0;
  var pollInFlight = false;
  var polite = false;             // "perfect negotiation" role
  var makingOffer = false;
  var ignoreOffer = false;
  var camOn = true;
  var micOn = true;

  // -- Helpers ------------------------------------------------------------
  function $(id) { return document.getElementById(id); }

  function setStatus(text, kind) {
    var el = $("wbCallStatus");
    if (el) {
      el.textContent = text || "";
      el.dataset.kind = kind || "";
    }
  }

  function panel() { return $("wbCallPanel"); }

  function showPanel(on) {
    var p = panel();
    if (!p) return;
    p.hidden = !on;
    p.classList.toggle("open", !!on);
    if (on) {
      // На всякий случай форсим видимость поверх любого fullscreen-overlay
      // (например, .drw-pane-full с z-index:50 на /whiteboard).
      try {
        p.style.position = "fixed";
        p.style.right = "14px";
        p.style.bottom = "14px";
        p.style.zIndex = "10000";
      } catch (e) {}
    }
  }

  function iceServers() {
    if (window.WB_CALL_ICE && Array.isArray(window.WB_CALL_ICE) && window.WB_CALL_ICE.length) {
      return window.WB_CALL_ICE;
    }
    return DEFAULT_ICE;
  }

  function api(path, body) {
    return fetch("/api/wb_call/" + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body || {})
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
    });
  }

  // -- Panel construction -------------------------------------------------
  function ensurePanel() {
    if (panel()) return;
    var host = document.getElementById("wbCanvasWrap") || document.body;
    var div = document.createElement("div");
    div.id = "wbCallPanel";
    div.className = "wb-call-panel";
    div.hidden = true;
    div.innerHTML =
      '<div class="wbc-head">' +
        '<span class="wbc-title">\u{1F4F9} \u0417\u0432\u043e\u043d\u043e\u043a</span>' +
        '<span id="wbCallStatus" class="wbc-status">\u043d\u0435 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u043e</span>' +
        '<button type="button" class="wbc-x" id="wbCallClose" title="\u0421\u0432\u0435\u0440\u043d\u0443\u0442\u044c">\u00d7</button>' +
      '</div>' +
      '<div class="wbc-hint" id="wbCallHint">' +
        '\u041f\u0440\u0438\u0434\u0443\u043c\u0430\u0439\u0442\u0435 \u043a\u043e\u0434 \u043a\u043e\u043c\u043d\u0430\u0442\u044b \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u{1F3B2}, \u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0435\u0433\u043e \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u0443.' +
      '</div>' +
      '<div class="wbc-room-row" id="wbCallRoomRow">' +
        '<input type="text" id="wbCallRoom" placeholder="\u041a\u043e\u0434 \u043a\u043e\u043c\u043d\u0430\u0442\u044b (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: math-42)" maxlength="64" minlength="3" autocomplete="off" spellcheck="false">' +
        '<button type="button" class="wbc-btn wbc-btn-ghost" id="wbCallGen" title="\u0421\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439 \u043a\u043e\u0434">\u{1F3B2}</button>' +
        '<button type="button" class="wbc-btn wbc-btn-primary" id="wbCallStart">\u0412\u043e\u0439\u0442\u0438</button>' +
      '</div>' +
      '<div class="wbc-invite-row" id="wbCallInviteRow">' +
        '<button type="button" class="wbc-btn wbc-btn-invite" id="wbCallInvite">' +
          '\u{1F46B} \u041f\u0440\u0438\u0433\u043b\u0430\u0441\u0438\u0442\u044c \u0434\u0440\u0443\u0433\u0430' +
        '</button>' +
      '</div>' +
      '<div class="wbc-friends-list" id="wbCallFriends" hidden>' +
        '<div class="wbc-friends-head">' +
          '<span>\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0440\u0443\u0433\u0430</span>' +
          '<button type="button" class="wbc-friends-close" id="wbCallFriendsClose" aria-label="\u0417\u0430\u043a\u0440\u044b\u0442\u044c">\u00d7</button>' +
        '</div>' +
        '<div class="wbc-friends-body" id="wbCallFriendsBody">' +
          '<div class="wbc-friends-loading">\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u043c\u2026</div>' +
        '</div>' +
      '</div>' +
      '<div class="wbc-videos" id="wbCallVideos" hidden>' +
        '<div class="wbc-vid">' +
          '<video id="wbCallRemote" autoplay playsinline></video>' +
          '<span class="wbc-tag">\u0421\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a</span>' +
        '</div>' +
        '<div class="wbc-vid wbc-vid-self">' +
          '<video id="wbCallLocal" autoplay playsinline muted></video>' +
          '<span class="wbc-tag">\u0412\u044b</span>' +
        '</div>' +
      '</div>' +
      '<div class="wbc-toolbar" id="wbCallToolbar" hidden>' +
        '<button type="button" class="wbc-icon" id="wbCallMic"  title="\u041c\u0438\u043a\u0440\u043e\u0444\u043e\u043d">\u{1F3A4}</button>' +
        '<button type="button" class="wbc-icon" id="wbCallCam"  title="\u041a\u0430\u043c\u0435\u0440\u0430">\u{1F4F7}</button>' +
        '<button type="button" class="wbc-icon" id="wbCallRetry" title="\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0440\u043e\u0441\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f \u043a \u043a\u0430\u043c\u0435\u0440\u0435 / \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0443">\u{1F501}</button>' +
        '<button type="button" class="wbc-icon wbc-icon-danger" id="wbCallLeave" title="\u0412\u044b\u0439\u0442\u0438">\u26d4</button>' +
        '<button type="button" class="wbc-icon" id="wbCallCopy" title="\u0421\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443">\u{1F517}</button>' +
      '</div>';
    host.appendChild(div);

    $("wbCallClose").addEventListener("click", function () { showPanel(false); });
    $("wbCallStart").addEventListener("click", onStartClick);
    $("wbCallGen").addEventListener("click", onGenerateClick);
    $("wbCallRoom").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); onStartClick(); }
    });
    $("wbCallRoom").addEventListener("input", function () {
      // Подсказка-фидбек: показываем валидность ввода в реальном времени.
      var raw = ($("wbCallRoom").value || "").trim();
      var clean = raw.replace(/[^A-Za-z0-9_-]/g, "");
      var hint = $("wbCallHint");
      if (!hint) return;
      if (!raw) {
        hint.textContent = "\u041f\u0440\u0438\u0434\u0443\u043c\u0430\u0439\u0442\u0435 \u043a\u043e\u0434 \u043a\u043e\u043c\u043d\u0430\u0442\u044b \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u{1F3B2}, \u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0435\u0433\u043e \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u0443.";
        hint.dataset.kind = "";
      } else if (clean.length < 3) {
        hint.textContent = "\u041a\u043e\u0434 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 (\u043d\u0443\u0436\u043d\u043e \u22653 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432 a\u2013z, 0\u20139, -, _).";
        hint.dataset.kind = "warn";
      } else {
        hint.textContent = "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u044d\u0442\u043e\u0442 \u043a\u043e\u0434 \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u0443 \u2014 \u043e\u043d \u0432\u0432\u043e\u0434\u0438\u0442 \u0435\u0433\u043e \u0443 \u0441\u0435\u0431\u044f \u0438 \u043f\u043e\u043f\u0430\u0434\u0430\u0435\u0442 \u0432 \u044d\u0442\u0443 \u0436\u0435 \u043a\u043e\u043c\u043d\u0430\u0442\u0443.";
        hint.dataset.kind = "ok";
      }
    });
    $("wbCallMic").addEventListener("click", toggleMic);
    $("wbCallCam").addEventListener("click", toggleCam);
    $("wbCallRetry").addEventListener("click", retryMedia);
    $("wbCallLeave").addEventListener("click", leaveCall);
    $("wbCallCopy").addEventListener("click", copyLink);
    $("wbCallInvite").addEventListener("click", openFriendsList);
    $("wbCallFriendsClose").addEventListener("click", function () {
      $("wbCallFriends").hidden = true;
    });

    // Pre-fill from ?room= or localStorage.
    var params = new URLSearchParams(window.location.search);
    var pre = params.get("room") || localStorage.getItem("wb_call_room_last") || "";
    if (pre) $("wbCallRoom").value = pre;
  }

  function _wbOpenPanel() {
    try {
      ensurePanel();
      showPanel(true);
      var inp = $("wbCallRoom");
      if (inp && !roomId) inp.focus();
    } catch (e) {
      console.error("[wb_call] openPanel failed", e);
    }
  }

  function ensureTopBarButton() {
    if ($("wbCallToggle")) return;
    // Если в шаблоне уже есть inline-кнопка с [data-wb-call-open] —
    // динамическую не добавляем, чтобы не было дубля.
    if (document.querySelector("[data-wb-call-open]")) return;
    // Ищем тулбар на любой из страниц-доски: старый интегрированный
    // /drawing?tab=whiteboard (#drw-pane-whiteboard) или новая отдельная
    // /whiteboard (#wb-pane). Если ни одного нет — кнопка не вставляется.
    var actions =
      document.querySelector("#wb-pane .top-bar .actions.zoom") ||
      document.querySelector("#drw-pane-whiteboard .top-bar .actions.zoom") ||
      document.querySelector(".drw-pane-full .top-bar .actions.zoom");
    if (!actions) return;
    var btn = document.createElement("button");
    btn.id = "wbCallToggle";
    btn.className = "icon-btn icon-btn-call";
    btn.title = "\u0412\u0438\u0434\u0435\u043e\u0437\u0432\u043e\u043d\u043e\u043a (1-\u043d\u0430-1)";
    btn.type = "button";
    btn.textContent = "\u{1F4F9}";
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      _wbOpenPanel();
    });
    var clearBtn = document.getElementById("wbClear");
    if (clearBtn && clearBtn.parentNode === actions) {
      actions.insertBefore(btn, clearBtn);
    } else {
      actions.appendChild(btn);
    }
    // Глобальный делегирующий обработчик уже навешен в boot()
    // через _wbInstallGlobalClick().
  }

  // -- Media --------------------------------------------------------------
  function acquireMedia() {
    // 1) Secure-context guard: getUserMedia доступен ТОЛЬКО на https:// или
    //    на localhost / 127.0.0.1. На http в проде navigator.mediaDevices
    //    будет undefined, и браузер вообще не покажет диалог разрешения.
    var isLocalhost = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])$/i
                       .test(location.hostname);
    var isSecure = (window.isSecureContext === true) ||
                   location.protocol === "https:" ||
                   isLocalhost;
    if (!isSecure) {
      return Promise.reject(Object.assign(new Error("Insecure context"), {
        name: "SecurityError",
        _userMessage: "\u041a\u0430\u043c\u0435\u0440\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e HTTPS \u2014 \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0441\u0430\u0439\u0442 \u043f\u043e https://"
      }));
    }

    // 2) Не во всех браузерах есть mediaDevices (например, очень старый Safari
    //    или ограниченные WebView). Покажем явное сообщение, а не падать молча.
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      return Promise.reject(Object.assign(new Error("getUserMedia not available"), {
        name: "NotSupportedError",
        _userMessage: "\u0411\u0440\u0430\u0443\u0437\u0435\u0440 \u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442 \u0432\u0438\u0434\u0435\u043e\u0437\u0432\u043e\u043d\u043a\u0438 (getUserMedia)"
      }));
    }

    var videoConstraints = { width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24, max: 30 } };
    var audioConstraints = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };

    // 3) Главный путь: пробуем сразу видео+аудио (типичный сценарий звонка).
    return navigator.mediaDevices.getUserMedia({
      video: videoConstraints,
      audio: audioConstraints
    }).catch(function (err) {
      // 4) Fallback-логика. Если видео+аудио вместе не получились — пытаемся
      //    «спасти» звонок, чтобы можно было хотя бы слышать собеседника.
      //    Это закрывает массовые кейсы:
      //      * камера занята OBS/Zoom, а микрофон свободен;
      //      * нет камеры на устройстве (десктоп без вебки);
      //      * драйвер камеры завис, но звуковая карта работает.
      var isCameraIssue = err && (
        err.name === "NotFoundError" ||
        err.name === "NotReadableError" ||
        err.name === "OverconstrainedError" ||
        err.name === "TrackStartError"
      );
      if (!isCameraIssue) {
        // Это не «проблема с камерой» — это отказ доступа целиком, HTTPS и пр.
        // Пробрасываем ошибку дальше, чтобы пользователь увидел нормальный текст.
        throw err;
      }
      console.warn("[wb_call] video failed (" + err.name + "), retrying audio-only");
      setStatus("\u041a\u0430\u043c\u0435\u0440\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u2014 \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0430\u0435\u043c\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0441\u043e \u0437\u0432\u0443\u043a\u043e\u043c\u2026", "warn");
      return navigator.mediaDevices.getUserMedia({ video: false, audio: audioConstraints });
    });
  }

  function attachLocalStream(stream) {
    localStream = stream;
    var v = $("wbCallLocal");
    if (v) v.srcObject = stream;
    var hasVideo = stream && stream.getVideoTracks().length > 0;
    var hasAudio = stream && stream.getAudioTracks().length > 0;
    camOn = hasVideo;
    micOn = hasAudio;
    // Подпись на «своём» окошке: если видео нет — показываем «без камеры».
    var tagSelf = document.querySelector("#wbCallPanel .wbc-vid-self .wbc-tag");
    if (tagSelf) {
      tagSelf.textContent = hasVideo
        ? "\u0412\u044b"
        : "\u0412\u044b (\u0431\u0435\u0437 \u043a\u0430\u043c\u0435\u0440\u044b)";
    }
    refreshToggles();
  }

  function stopLocalStream() {
    if (!localStream) return;
    try { localStream.getTracks().forEach(function (t) { try { t.stop(); } catch (e) {} }); } catch (e) {}
    localStream = null;
    var v = $("wbCallLocal");
    if (v) v.srcObject = null;
  }

  function refreshToggles() {
    var mic = $("wbCallMic"); var cam = $("wbCallCam");
    if (mic) { mic.classList.toggle("off", !micOn); mic.textContent = micOn ? "\u{1F3A4}" : "\u{1F507}"; }
    if (cam) { cam.classList.toggle("off", !camOn); cam.textContent = camOn ? "\u{1F4F7}" : "\u{1F6AB}"; }
    // Если в потоке физически нет видео-трека — отключаем кнопку камеры,
    // чтобы пользователь не пытался «включить» несуществующее устройство.
    var hasVideoTrack = localStream && localStream.getVideoTracks().length > 0;
    if (cam) {
      cam.disabled = !hasVideoTrack;
      cam.title = hasVideoTrack
        ? "\u041a\u0430\u043c\u0435\u0440\u0430"
        : "\u041a\u0430\u043c\u0435\u0440\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430";
    }
  }

  function toggleMic() {
    if (!localStream) return;
    micOn = !micOn;
    localStream.getAudioTracks().forEach(function (t) { t.enabled = micOn; });
    refreshToggles();
  }
  function toggleCam() {
    if (!localStream) return;
    camOn = !camOn;
    localStream.getVideoTracks().forEach(function (t) { t.enabled = camOn; });
    refreshToggles();
  }

  function copyLink() {
    if (!roomId) return;
    var url = window.location.origin + window.location.pathname + "?room=" + encodeURIComponent(roomId);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { setStatus("\u0421\u0441\u044b\u043b\u043a\u0430 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0430"); });
    } else {
      window.prompt("\u0421\u043a\u043e\u043f\u0438\u0440\u0443\u0439\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 \u0434\u043b\u044f \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u0430:", url);
    }
  }

  // -- Peer connection ----------------------------------------------------
  // wbDC: RTCDataChannel для синхронизации доски между двумя пирами.
  // Контракт сообщений совпадает с wb_collab.js (LiveKit-вариант):
  //   { v:1, t:"hello", from }                — попросить snapshot
  //   { v:1, t:"snapshot", state:{objects, nextId} }
  //   { v:1, t:"op", op:{...} }               — diff-операция доски
  // Это даёт «бесплатно» синхронизацию рисования в peer-to-peer звонке,
  // без участия сервера и без задержки HTTP-polling'а.
  var wbDC = null;
  var wbDCReceivedSnapshot = false;
  var wbDCPrevBroadcast = null;

  function _wbDCSend(packet) {
    if (!wbDC || wbDC.readyState !== "open") return;
    try { wbDC.send(JSON.stringify(packet)); } catch (e) { /* ignore */ }
  }

  function _wbDCBindBroadcaster() {
    // Перехватываем window.__wbBroadcast: whiteboard.js вызывает её при
    // каждой локальной операции рисования. Делаем это так же, как wb_collab.js,
    // чтобы оба механизма (LiveKit и наш peer-to-peer) могли сосуществовать.
    if (window.__wbBroadcast && window.__wbBroadcast.__wb_call_proxy) return;
    wbDCPrevBroadcast = window.__wbBroadcast || null;
    var fn = function (op) {
      // 1) Сначала отдаём предыдущему broadcaster'у (если LiveKit-комната
      //    тоже активна — пусть и туда летит).
      try {
        if (typeof wbDCPrevBroadcast === "function" && wbDCPrevBroadcast !== fn) {
          wbDCPrevBroadcast(op);
        }
      } catch (e) {}
      // 2) И отправляем через наш data-channel другому пиру.
      _wbDCSend({ v: 1, t: "op", op: op });
    };
    fn.__wb_call_proxy = true;
    window.__wbBroadcast = fn;
  }

  function _wbDCUnbindBroadcaster() {
    if (window.__wbBroadcast && window.__wbBroadcast.__wb_call_proxy) {
      window.__wbBroadcast = wbDCPrevBroadcast || null;
    }
    wbDCPrevBroadcast = null;
  }

  function _wbDCOnMessage(ev) {
    var msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (!msg || typeof msg !== "object") return;

    if (msg.t === "hello") {
      // Партнёр запросил начальный снимок доски — отдаём.
      if (!window.WB || typeof window.WB.getSnapshot !== "function") return;
      try {
        var snap = window.WB.getSnapshot();
        _wbDCSend({ v: 1, t: "snapshot", state: snap });
      } catch (e) { console.warn("[wb_call] snapshot send failed", e); }
      return;
    }
    if (msg.t === "snapshot") {
      if (wbDCReceivedSnapshot) return;
      if (!msg.state || !window.WB || typeof window.WB.applyRemoteOp !== "function") return;
      try {
        window.WB.applyRemoteOp({ op: "snapshot", state: msg.state });
        wbDCReceivedSnapshot = true;
      } catch (e) { console.warn("[wb_call] apply snapshot failed", e); }
      return;
    }
    if (msg.t === "op" && msg.op) {
      if (!window.WB || typeof window.WB.applyRemoteOp !== "function") return;
      try { window.WB.applyRemoteOp(msg.op); }
      catch (e) { console.warn("[wb_call] apply op failed", e); }
      return;
    }
  }

  function _wbDCWire(channel) {
    wbDC = channel;
    wbDCReceivedSnapshot = false;
    channel.onopen = function () {
      try { console.debug("[wb_call] data-channel open"); } catch (e) {}
      _wbDCBindBroadcaster();
      // Просим у партнёра текущее состояние доски, чтобы догнать его рисунки.
      // Маленькая задержка — чтобы WB точно был инициализирован.
      setTimeout(function () {
        _wbDCSend({ v: 1, t: "hello", from: peerId || "?" });
      }, 250);
      // Показываем подпись в статусе панели: «доска синхронизируется».
      setStatus("\u0412 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0435 \u00b7 \u0434\u043e\u0441\u043a\u0430 \u0441\u0438\u043d\u0445\u0440.", "ok");
    };
    channel.onmessage = _wbDCOnMessage;
    channel.onclose = function () {
      try { console.debug("[wb_call] data-channel closed"); } catch (e) {}
      _wbDCUnbindBroadcaster();
      wbDC = null;
      wbDCReceivedSnapshot = false;
    };
    channel.onerror = function (e) {
      try { console.warn("[wb_call] data-channel error", e); } catch (_) {}
    };
  }

  function createPc() {
    var p = new RTCPeerConnection({ iceServers: iceServers() });

    p.onicecandidate = function (ev) {
      if (ev.candidate && otherId) {
        send({ type: "ice", candidate: ev.candidate.toJSON ? ev.candidate.toJSON() : ev.candidate });
      }
    };
    p.ontrack = function (ev) {
      var v = $("wbCallRemote");
      if (v && ev.streams && ev.streams[0]) { v.srcObject = ev.streams[0]; }
    };
    p.onconnectionstatechange = function () {
      var s = p.connectionState;
      if (s === "connected")        setStatus("\u0412 \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440\u0435", "ok");
      else if (s === "connecting")  setStatus("\u0421\u043e\u0435\u0434\u0438\u043d\u044f\u0435\u043c\u0441\u044f\u2026");
      else if (s === "failed")      setStatus("\u0421\u0432\u044f\u0437\u044c \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430", "err");
      else if (s === "disconnected") setStatus("\u0421\u0432\u044f\u0437\u044c \u043f\u0440\u0435\u0440\u0432\u0430\u043d\u0430", "warn");
    };
    p.onnegotiationneeded = function () { tryNegotiate(); };

    // Принимаем data-channel, который создал другой пир.
    p.ondatachannel = function (ev) {
      if (ev && ev.channel && ev.channel.label === "wb-board") {
        _wbDCWire(ev.channel);
      }
    };

    if (localStream) {
      localStream.getTracks().forEach(function (t) { p.addTrack(t, localStream); });
    }
    return p;
  }

  // Создаёт data-channel, если мы инициатор (impolite). Вызывается из
  // tryNegotiate() ДО createOffer, чтобы канал попал в SDP. На polite-стороне
  // канал придёт сам через ondatachannel.
  function _wbDCEnsureForInitiator() {
    if (!pc || polite || wbDC) return;
    try {
      var dc = pc.createDataChannel("wb-board", { ordered: true });
      _wbDCWire(dc);
    } catch (e) { console.warn("[wb_call] createDataChannel failed", e); }
  }

  function tryNegotiate() {
    if (!pc || !otherId) return;
    // Если мы инициатор — создаём data-channel ДО createOffer, чтобы он
    // попал в SDP. Это критично для синхронизации доски.
    _wbDCEnsureForInitiator();
    (async function () {
      try {
        makingOffer = true;
        var offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        send({ type: "sdp", sdp: pc.localDescription });
      } catch (e) {
        console.warn("[wb_call] negotiate err", e);
      } finally {
        makingOffer = false;
      }
    })();
  }

  // -- Signalling ---------------------------------------------------------
  function send(msg) {
    if (!roomId || !peerId || !otherId) return Promise.resolve();
    return api("send", { room: roomId, from: peerId, to: otherId, msg: msg }).catch(function (e) {
      console.warn("[wb_call] send err", e);
    });
  }

  function handleIncoming(from, msg) {
    if (!msg || typeof msg !== "object") return;
    if (!otherId) otherId = from;

    if (msg.type === "peer-joined") {
      otherId = from;
      polite = false;
      ensurePc();
      tryNegotiate();
      setStatus("\u0421\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u043b\u0441\u044f\u2026");
      return;
    }
    if (msg.type === "peer-left") {
      setStatus("\u0421\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a \u0432\u044b\u0448\u0435\u043b", "warn");
      teardownPc();
      otherId = null;
      var v = $("wbCallRemote"); if (v) v.srcObject = null;
      return;
    }

    if (msg.type === "sdp" && msg.sdp) {
      ensurePc();
      (async function () {
        var desc = msg.sdp;
        var offerCollision = (desc.type === "offer") && (makingOffer || pc.signalingState !== "stable");
        ignoreOffer = !polite && offerCollision;
        if (ignoreOffer) return;
        try {
          if (offerCollision) {
            await Promise.all([
              pc.setLocalDescription({ type: "rollback" }).catch(function () {}),
              pc.setRemoteDescription(desc)
            ]);
          } else {
            await pc.setRemoteDescription(desc);
          }
          if (desc.type === "offer") {
            var ans = await pc.createAnswer();
            await pc.setLocalDescription(ans);
            send({ type: "sdp", sdp: pc.localDescription });
          }
        } catch (e) {
          console.warn("[wb_call] sdp err", e);
        }
      })();
      return;
    }

    if (msg.type === "ice" && msg.candidate) {
      if (!pc) return;
      pc.addIceCandidate(msg.candidate).catch(function (e) {
        if (!ignoreOffer) console.warn("[wb_call] ice err", e);
      });
      return;
    }
  }

  function ensurePc() { if (!pc) pc = createPc(); }
  function teardownPc() {
    // Сначала закрываем data-channel и отвязываем broadcaster — иначе
    // window.__wbBroadcast останется указывать на dead-канал и доска не
    // будет работать локально после выхода из звонка.
    if (wbDC) {
      try { wbDC.close(); } catch (e) {}
      wbDC = null;
    }
    _wbDCUnbindBroadcaster();
    wbDCReceivedSnapshot = false;
    if (pc) {
      try { pc.getSenders().forEach(function (s) { try { s.track && s.track.stop(); } catch (e) {} }); } catch (e) {}
      try { pc.close(); } catch (e) {}
      pc = null;
    }
  }

  function pollLoop() {
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = 0; }
    if (!roomId || !peerId) return;
    if (pollInFlight) return;
    pollInFlight = true;
    api("poll", { room: roomId, peer_id: peerId }).then(function (r) {
      pollInFlight = false;
      if (!r.ok) {
        if (r.status === 404) {
          setStatus("\u041f\u0435\u0440\u0435\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0430\u0435\u043c\u0441\u044f\u2026", "warn");
          rejoin();
          return;
        }
        setStatus("\u041e\u0448\u0438\u0431\u043a\u0430 \u043e\u043f\u0440\u043e\u0441\u0430", "err");
        return;
      }
      var data = r.data || {};
      if (!otherId && Array.isArray(data.peers) && data.peers.length) {
        otherId = data.peers[0];
        ensurePc();
        polite = (peerId > otherId);
        if (!polite) tryNegotiate();
      }
      (data.messages || []).forEach(function (m) { handleIncoming(m.from, m.msg); });
    }).catch(function (e) {
      pollInFlight = false;
      console.warn("[wb_call] poll err", e);
    }).then(function () {
      var interval = (pc && pc.connectionState === "connected") || otherId
        ? POLL_INTERVAL_ACTIVE_MS
        : POLL_INTERVAL_IDLE_MS;
      pollTimer = setTimeout(pollLoop, interval);
    });
  }

  // -- Friends invite -----------------------------------------------------
  var _friendsCache = null;

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function buildRoomUrl(code) {
    return window.location.origin + window.location.pathname + "?room=" + encodeURIComponent(code);
  }

  function openFriendsList() {
    var box = $("wbCallFriends");
    var body = $("wbCallFriendsBody");
    if (!box || !body) return;
    box.hidden = false;

    // Перед запросом убедимся, что есть валидный код комнаты — иначе ссылку
    // отправить некуда. Если поле пустое — генерируем код автоматически.
    var inp = $("wbCallRoom");
    var rid = inp ? inp.value.trim().replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64) : "";
    if (!rid || rid.length < 3) {
      onGenerateClick();
      rid = inp.value.trim();
    }

    if (_friendsCache) {
      renderFriendsList(_friendsCache, rid);
      return;
    }

    body.innerHTML = '<div class="wbc-friends-loading">\u0417\u0430\u0433\u0440\u0443\u0436\u0430\u0435\u043c\u2026</div>';
    fetch("/api/social/friends/list", { credentials: "same-origin" })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) {
          body.innerHTML = '<div class="wbc-friends-empty">\u0412\u043e\u0439\u0434\u0438\u0442\u0435 \u0432 \u0430\u043a\u043a\u0430\u0443\u043d\u0442, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u0438\u0433\u043b\u0430\u0448\u0430\u0442\u044c \u0434\u0440\u0443\u0437\u0435\u0439.</div>';
          throw new Error("auth");
        }
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          body.innerHTML = '<div class="wbc-friends-empty">\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0434\u0440\u0443\u0437\u0435\u0439.</div>';
          return;
        }
        _friendsCache = data.friends || [];
        renderFriendsList(_friendsCache, rid);
      })
      .catch(function (e) {
        if (e && e.message === "auth") return;
        console.warn("[wb_call] friends list err", e);
        body.innerHTML = '<div class="wbc-friends-empty">\u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438.</div>';
      });
  }

  function renderFriendsList(friends, rid) {
    var body = $("wbCallFriendsBody");
    if (!body) return;
    if (!friends || !friends.length) {
      body.innerHTML =
        '<div class="wbc-friends-empty">' +
          '\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442 \u0434\u0440\u0443\u0437\u0435\u0439. ' +
          '<a href="/friends" target="_blank" rel="noopener">\u041d\u0430\u0439\u0442\u0438 \u0434\u0440\u0443\u0437\u0435\u0439</a>' +
        '</div>';
      return;
    }
    var html = '';
    friends.forEach(function (f) {
      var name = escapeHtml(f.nickname || f.name || ("ID " + f.id));
      var avatar = f.avatar_url
        ? '<img class="wbc-friend-avatar" src="' + escapeHtml(f.avatar_url) + '" alt="">'
        : '<div class="wbc-friend-avatar wbc-friend-avatar-fallback">' +
            escapeHtml((name[0] || "?").toUpperCase()) +
          '</div>';
      html += '<button type="button" class="wbc-friend-item" data-friend-id="' + f.id + '">' +
                avatar +
                '<span class="wbc-friend-name">' + name + '</span>' +
                '<span class="wbc-friend-invite">\u041f\u0440\u0438\u0433\u043b\u0430\u0441\u0438\u0442\u044c</span>' +
              '</button>';
    });
    body.innerHTML = html;
    // Делегируем клик: чтобы не перепривязывать после каждого ререндера.
    body.querySelectorAll(".wbc-friend-item").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var fid = parseInt(btn.getAttribute("data-friend-id"), 10);
        if (!isNaN(fid)) sendInviteToFriend(fid, rid, btn);
      });
    });
  }

  function sendInviteToFriend(friendId, code, btnEl) {
    var label = btnEl ? btnEl.querySelector(".wbc-friend-invite") : null;
    if (label) { label.textContent = "\u2026"; }
    if (btnEl) btnEl.disabled = true;

    // Шлём приглашение через signalling-канал виджета (push-уведомление).
    // Если друг сейчас на сайте — у него всплывёт окно «Принять/Отклонить»
    // в течение ~7 секунд (см. static/js/wb_call_listener.js).
    fetch("/api/wb_call/invite", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ friend_id: friendId, room: code })
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
    }).then(function (r) {
      if (!r.ok) {
        var errText = r.data && r.data.error;
        if (label) label.textContent = "\u26a0 " + (errText || "\u043e\u0448\u0438\u0431\u043a\u0430");
        if (btnEl) btnEl.disabled = false;
        return;
      }
      if (label) {
        label.textContent = "\u2713 \u041f\u0440\u0438\u0433\u043b\u0430\u0448\u0451\u043d";
        label.classList.add("wbc-friend-invite-sent");
      }
      setStatus("\u041f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e", "ok");
      if (btnEl) btnEl.disabled = false;
    }).catch(function (e) {
      console.warn("[wb_call] invite err", e);
      if (label) label.textContent = "\u26a0 \u041e\u0448\u0438\u0431\u043a\u0430";
      if (btnEl) btnEl.disabled = false;
    });
  }

  // -- Retry media (re-ask camera / mic permission) ------------------------
  function retryMedia() {
    // Останавливаем текущий поток (если есть) и заново вызываем getUserMedia.
    // Если разрешения сохранены — браузер вернёт стрим без диалога.
    // Если пользователь до этого нажимал "Запретить" — диалог появится только
    // после того как он вручную сбросит блокировку (значок 🔒 в адресной строке).
    setStatus("\u041f\u0435\u0440\u0435\u0437\u0430\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0435\u043c \u043a\u0430\u043c\u0435\u0440\u0443/\u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u2026");
    var oldStream = localStream;
    stopLocalStream();
    acquireMedia().then(function (stream) {
      attachLocalStream(stream);
      // Перепривязываем треки к существующему RTCPeerConnection, чтобы
      // собеседник сразу увидел/услышал обновлённое устройство.
      if (pc) {
        var senders = pc.getSenders();
        stream.getTracks().forEach(function (newTrack) {
          var sender = senders.find(function (s) { return s.track && s.track.kind === newTrack.kind; });
          if (sender) {
            sender.replaceTrack(newTrack).catch(function (e) {
              console.warn("[wb_call] replaceTrack err", e);
            });
          } else {
            try { pc.addTrack(newTrack, stream); } catch (e) {}
          }
        });
      }
      var hasVideo = stream.getVideoTracks().length > 0;
      setStatus(hasVideo
        ? "\u041a\u0430\u043c\u0435\u0440\u0430/\u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u044b"
        : "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0451\u043d \u0442\u043e\u043b\u044c\u043a\u043e \u0437\u0432\u0443\u043a", hasVideo ? "ok" : "warn");
    }).catch(function (e) {
      console.warn("[wb_call] retryMedia err", e);
      var msg = (e && e._userMessage) ||
                "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0434\u043e\u0441\u0442\u0443\u043f \u043a \u043a\u0430\u043c\u0435\u0440\u0435/\u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0443. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0440\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u0438\u044f \u0432 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0435.";
      setStatus(msg, "err");
      // Возвращаем старый поток, чтобы звонок не оборвался.
      if (oldStream) {
        localStream = oldStream;
        var v = $("wbCallLocal");
        if (v) v.srcObject = oldStream;
      }
    });
  }

  // -- Public actions -----------------------------------------------------
  function generateRoomCode() {
    // Понятные «слова + число» для удобства диктовки голосом.
    var words = [
      "math", "alpha", "beta", "delta", "sigma", "lemma", "theta",
      "graph", "prime", "axis", "vector", "scalar", "proof", "logic"
    ];
    var w = words[Math.floor(Math.random() * words.length)];
    var n = Math.floor(Math.random() * 900) + 100; // 100..999
    return w + "-" + n;
  }

  function onGenerateClick() {
    var inp = $("wbCallRoom");
    if (!inp) return;
    inp.value = generateRoomCode();
    try { inp.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
    inp.focus();
    inp.select();
  }

  function onStartClick() {
    var inp = $("wbCallRoom");
    var raw = inp ? inp.value.trim() : "";
    var rid = (raw || "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
    if (!rid) {
      setStatus("\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043a\u043e\u0434 \u043a\u043e\u043c\u043d\u0430\u0442\u044b \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u{1F3B2}", "warn");
      if (inp) inp.focus();
      return;
    }
    if (rid.length < 3) {
      setStatus("\u041a\u043e\u0434 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u043a\u043e\u0440\u043e\u0442\u043a\u0438\u0439 (\u043c\u0438\u043d. 3 \u0441\u0438\u043c\u0432\u043e\u043b\u0430)", "warn");
      if (inp) { inp.focus(); inp.select(); }
      return;
    }
    try { localStorage.setItem("wb_call_room_last", rid); } catch (e) {}
    joinRoom(rid);
  }

  function _wbPrevPeerKey(rid) { return "wb_call_prev_peer:" + rid; }
  function _wbGetPrevPeer(rid) {
    try { return localStorage.getItem(_wbPrevPeerKey(rid)) || null; }
    catch (e) { return null; }
  }
  function _wbSavePrevPeer(rid, pid) {
    try { localStorage.setItem(_wbPrevPeerKey(rid), pid); } catch (e) {}
  }
  function _wbClearPrevPeer(rid) {
    try { localStorage.removeItem(_wbPrevPeerKey(rid)); } catch (e) {}
  }

  function joinRoom(rid) {
    setStatus("\u0417\u0430\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0435\u043c \u043a\u0430\u043c\u0435\u0440\u0443\u2026");
    var prevPeer = _wbGetPrevPeer(rid);
    acquireMedia().then(function (stream) {
      attachLocalStream(stream);
      $("wbCallVideos").hidden = false;
      $("wbCallToolbar").hidden = false;
      $("wbCallRoomRow").hidden = true;
      setStatus("\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0430\u0435\u043c\u0441\u044f \u043a \u043a\u043e\u043c\u043d\u0430\u0442\u0435\u2026");
      return api("join", { room: rid, prev_peer_id: prevPeer });
    }).then(function (r) {
      if (!r) return;
      if (!r.ok) {
        if (r.status === 409) {
          var lim = (r.data && r.data.limit) || "?";
          setStatus("\u041a\u043e\u043c\u043d\u0430\u0442\u0430 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u0430 (\u043c\u0430\u043a\u0441. " + lim + " \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432)", "err");
        } else {
          setStatus("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0432\u043e\u0439\u0442\u0438", "err");
        }
        stopLocalStream();
        $("wbCallVideos").hidden = true;
        $("wbCallToolbar").hidden = true;
        $("wbCallRoomRow").hidden = false;
        return;
      }
      roomId = rid;
      peerId = r.data.peer_id;
      _wbSavePrevPeer(rid, peerId);
      var peers = r.data.peers || [];
      if (peers.length) {
        otherId = peers[0];
        polite = (peerId > otherId);
        ensurePc();
        if (!polite) tryNegotiate();
        setStatus("\u0421\u043e\u0435\u0434\u0438\u043d\u044f\u0435\u043c\u0441\u044f \u0441 \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u043e\u043c\u2026");
      } else {
        setStatus("\u0416\u0434\u0451\u043c \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u0430\u2026 \u041f\u043e\u0434\u0435\u043b\u0438\u0442\u0435\u0441\u044c \u043a\u043e\u0434\u043e\u043c \u0438\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u043e\u0439 \u{1F517}");
      }
      pollLoop();
    }).catch(function (e) {
      console.warn("[wb_call] join err", e);
      var msg;
      if (e && e._userMessage) {
        msg = e._userMessage;
      } else if (e && (e.name === "NotAllowedError" || e.name === "PermissionDeniedError")) {
        msg = "\u0414\u043e\u0441\u0442\u0443\u043f \u043a \u043a\u0430\u043c\u0435\u0440\u0435/\u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0443 \u0437\u0430\u043f\u0440\u0435\u0449\u0451\u043d \u2014 \u0440\u0430\u0437\u0440\u0435\u0448\u0438\u0442\u0435 \u0432 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445 \u0431\u0440\u0430\u0443\u0437\u0435\u0440\u0430 (\u0437\u043d\u0430\u0447\u043e\u043a \u0437\u0430\u043c\u043a\u0430 \u0432 \u0430\u0434\u0440\u0435\u0441\u043d\u043e\u0439 \u0441\u0442\u0440\u043e\u043a\u0435)";
      } else if (e && e.name === "SecurityError") {
        msg = "\u041a\u0430\u043c\u0435\u0440\u0430 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0430 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u043e HTTPS \u2014 \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0441\u0430\u0439\u0442 \u043f\u043e https://";
      } else if (e && e.name === "NotFoundError") {
        msg = "\u041a\u0430\u043c\u0435\u0440\u0430 \u0438\u043b\u0438 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u044b \u043d\u0430 \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0435";
      } else if (e && e.name === "NotReadableError") {
        msg = "\u041a\u0430\u043c\u0435\u0440\u0430/\u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u0437\u0430\u043d\u044f\u0442\u044b \u0434\u0440\u0443\u0433\u043e\u0439 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u043e\u0439 (Zoom, Skype, OBS\u2026)";
      } else if (e && e.name === "NotSupportedError") {
        msg = "\u0411\u0440\u0430\u0443\u0437\u0435\u0440 \u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442 \u0432\u0438\u0434\u0435\u043e\u0437\u0432\u043e\u043d\u043a\u0438";
      } else if (e && e.name === "OverconstrainedError") {
        msg = "\u041a\u0430\u043c\u0435\u0440\u0430 \u043d\u0435 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u0438\u0432\u0430\u0435\u0442 \u043d\u0443\u0436\u043d\u044b\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438";
      } else {
        msg = "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f";
      }
      setStatus(msg, "err");
      stopLocalStream();
      $("wbCallVideos").hidden = true;
      $("wbCallToolbar").hidden = true;
      $("wbCallRoomRow").hidden = false;
    });
  }

  function rejoin() {
    var rid = roomId;
    var oldPeerId = peerId;
    if (!rid) return;

    // Сперва аккуратно покидаем «зомби»-peer на сервере (если он там ещё
    // числится), чтобы не получить 409 room_full на следующем join.
    var leavePromise = oldPeerId
      ? api("leave", { room: rid, peer_id: oldPeerId }).catch(function () {})
      : Promise.resolve();

    leavePromise.then(function () {
      // Передаём свой прошлый peer_id, чтобы сервер сразу вычистил «зомби».
      return api("join", { room: rid, prev_peer_id: oldPeerId || _wbGetPrevPeer(rid) });
    }).then(function (r) {
      if (!r.ok) {
        if (r.status === 409) {
          var lim2 = (r.data && r.data.limit) || "?";
          setStatus(
            "\u041a\u043e\u043c\u043d\u0430\u0442\u0430 \u0437\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u0430 (\u043c\u0430\u043a\u0441. " + lim2 + " \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432). \u041f\u0440\u0438\u0434\u0443\u043c\u0430\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 \u043a\u043e\u0434.",
            "err"
          );
        } else if (r.status === 400) {
          setStatus("\u041d\u0435\u043a\u043e\u0440\u0440\u0435\u043a\u0442\u043d\u044b\u0439 \u043a\u043e\u0434 \u043a\u043e\u043c\u043d\u0430\u0442\u044b", "err");
        } else {
          setStatus("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f (\u043f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0432\u044b\u0439\u0442\u0438 \u0438 \u0432\u043e\u0439\u0442\u0438 \u0437\u0430\u043d\u043e\u0432\u043e)", "err");
        }
        return;
      }
      peerId = r.data.peer_id;
      _wbSavePrevPeer(rid, peerId);
      otherId = (r.data.peers && r.data.peers[0]) || null;
      teardownPc();
      if (otherId) {
        polite = (peerId > otherId);
        ensurePc();
        if (!polite) tryNegotiate();
        setStatus("\u0421\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u0435 \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e", "ok");
      } else {
        setStatus("\u0416\u0434\u0451\u043c \u0441\u043e\u0431\u0435\u0441\u0435\u0434\u043d\u0438\u043a\u0430\u2026 \u041f\u043e\u0434\u0435\u043b\u0438\u0442\u0435\u0441\u044c \u043a\u043e\u0434\u043e\u043c \u0438\u043b\u0438 \u0441\u0441\u044b\u043b\u043a\u043e\u0439 \u{1F517}");
      }
      pollLoop();
    }).catch(function (e) {
      console.warn("[wb_call] rejoin err", e);
      setStatus("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u0435\u0440\u0435\u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f \u2014 \u043f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0438\u043d\u0442\u0435\u0440\u043d\u0435\u0442", "err");
    });
  }

  function leaveCall() {
    if (roomId && peerId) {
      api("leave", { room: roomId, peer_id: peerId }).catch(function () {});
      _wbClearPrevPeer(roomId);
    }
    teardownPc();
    stopLocalStream();
    roomId = null; peerId = null; otherId = null;
    if (pollTimer) { clearTimeout(pollTimer); pollTimer = 0; }
    $("wbCallVideos").hidden = true;
    $("wbCallToolbar").hidden = true;
    $("wbCallRoomRow").hidden = false;
    setStatus("\u0412\u044b \u0432\u044b\u0448\u043b\u0438 \u0438\u0437 \u0437\u0432\u043e\u043d\u043a\u0430");
  }

  window.addEventListener("beforeunload", function () {
    if (roomId && peerId) {
      try {
        if (navigator.sendBeacon) {
          var blob = new Blob([JSON.stringify({ room: roomId, peer_id: peerId })],
                              { type: "application/json" });
          navigator.sendBeacon("/api/wb_call/leave", blob);
        }
      } catch (e) {}
    }
  });

  // -- Boot ---------------------------------------------------------------
  function _wbInstallGlobalClick() {
    if (window.__wb_call_global_click) return;
    window.__wb_call_global_click = true;
    // Слушаем И click, И pointerdown — на случай если что-то (например,
    // другой capture-listener на canvas-wrap) перехватывает click до нас.
    // pointerdown срабатывает раньше click и не отменяется stopPropagation
    // на родительском элементе, если мы тоже идём в capture-фазе.
    function handler(ev) {
      var t = ev.target;
      if (!t) return;
      var hit = t.closest && t.closest("#wbCallToggle, [data-wb-call-open]");
      if (hit) {
        ev.preventDefault();
        ev.stopPropagation();
        _wbOpenPanel();
      }
    }
    document.addEventListener("click", handler, true);
    document.addEventListener("pointerdown", function (ev) {
      // pointerdown сам по себе не «активирует» кнопку — используем его
      // только как диагностический сигнал + как фолбэк, если click потом
      // не приедет (например, click погасили e.preventDefault на родителе).
      var t = ev.target;
      if (!t) return;
      var hit = t.closest && t.closest("#wbCallToggle, [data-wb-call-open]");
      if (hit) {
        try { console.debug("[wb_call] pointerdown on call button"); } catch (e) {}
      }
    }, true);
  }

  // Прямой биндинг: для каждой найденной inline-кнопки [data-wb-call-open]
  // вешаем onclick напрямую. Это страховка на случай, если в DOM есть
  // другой capture-listener выше нас, который вызывает stopImmediatePropagation
  // и не даёт document-делегатору сработать.
  function _wbBindInlineButtons() {
    var btns = document.querySelectorAll("[data-wb-call-open]");
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      if (b.__wb_call_bound) continue;
      b.__wb_call_bound = true;
      b.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        try { console.debug("[wb_call] inline button click"); } catch (e) {}
        _wbOpenPanel();
      });
    }
  }

  function boot() {
    try { console.debug("[wb_call] boot, readyState=", document.readyState); } catch (e) {}
    // Глобальный делегирующий обработчик ставим в любом случае — даже если
    // на текущей странице кнопки нет. На /whiteboard inline-кнопка в шаблоне
    // имеет [data-wb-call-open], так что клик сработает гарантированно.
    _wbInstallGlobalClick();
    _wbBindInlineButtons();

    // На случай, если кнопка появится в DOM позже (динамические тулбары) —
    // ставим лёгкий MutationObserver и перепривязываем новые кнопки.
    try {
      var mo = new MutationObserver(function () { _wbBindInlineButtons(); });
      mo.observe(document.documentElement, { childList: true, subtree: true });
    } catch (e) {}

    if (!document.getElementById("wbCanvas")) return;
    ensureTopBarButton();

    // Auto-show the panel if the URL has ?room=...  so guests join instantly.
    var params = new URLSearchParams(window.location.search);
    var roomFromUrl = params.get("room");
    if (roomFromUrl) {
      ensurePanel();
      showPanel(true);
      // Подставляем код комнаты в input.
      var inp = $("wbCallRoom");
      if (inp) inp.value = roomFromUrl;

      // Если URL содержит auto=1 (это значит пользователь пришёл по принятому
      // приглашению друга через wb_call_listener.js) — автоматически нажимаем
      // «Войти», чтобы не заставлять делать лишний клик. Браузер всё равно
      // покажет диалог разрешения камеры/микрофона — это нормально и
      // обязательно (требование getUserMedia).
      if (params.get("auto") === "1") {
        // Маленькая задержка — даём панели и стилям отрисоваться.
        setTimeout(function () {
          var startBtn = $("wbCallStart");
          if (startBtn) {
            try { startBtn.click(); } catch (e) {}
          }
        }, 350);
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Expose a small public API for debugging / future extensions.
  window.WB_CALL = {
    open:  function (rid) { ensurePanel(); showPanel(true); if (rid) { var i = $("wbCallRoom"); if (i) i.value = rid; } },
    close: function ()    { showPanel(false); },
    leave: leaveCall,
    state: function () { return { roomId: roomId, peerId: peerId, otherId: otherId, connected: !!(pc && pc.connectionState === "connected") }; }
  };
})();
