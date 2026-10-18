// FORMYLA.net Whiteboard - group video meeting via LiveKit.
// Pulls the official LiveKit client (ESM build) from a CDN at runtime,
// so we don't need a build step.  Falls back to "feature disabled" if the
// server says LIVEKIT_* env vars are missing.
//
// MEET_STABILITY_V1:
//   * автопереподключение: при обрыве связи / истечении токена / уходе
//     вкладки в фон берём свежий токен с тем же identity и заходим снова,
//     пока пользователь сам не нажал «Выйти»;
//   * heartbeat раз в минуту — сервер не считает нас «ушедшими»;
//   * Wake Lock — телефон не гасит экран и не рвёт звонок;
//   * совместимость с livekit-client v2 (remoteParticipants / trackPublications) —
//     раньше второй участник падал с ошибкой и доска не синхронизировалась;
//   * кнопка «Позвать всех к себе» (📣) — все участники увидят ваш
//     участок доски (реализация в wb_collab.js).

(function () {
  "use strict";

  var LIVEKIT_CDN = "https://cdn.jsdelivr.net/npm/livekit-client@2.5.10/+esm";

  var lk = null;                // resolved LiveKit module
  var room = null;              // current Room instance
  var roomId = null;
  var identity = null;
  var displayName = null;
  var configCache = null;
  var participantsEl = null;

  // Состояние «хочу быть в звонке» — живёт между переподключениями.
  var wantConnected = false;
  var connecting = false;
  var rejoinTimer = 0;
  var rejoinAttempt = 0;
  var heartbeatTimer = 0;
  var wakeLock = null;
  var prefs = { mic: true, cam: true };   // что было включено до обрыва
  var MAX_REJOIN_ATTEMPTS = 60;           // ~15 минут с бэкоффом до 15 с

  // ─── DOM helpers ─────────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }
  function panel() { return $("wbMeetPanel"); }
  function setStatus(text, kind) {
    var el = $("wbMeetStatus");
    if (el) { el.textContent = text || ""; el.dataset.kind = kind || ""; }
  }
  function showPanel(on) {
    var p = panel();
    if (!p) return;
    p.hidden = !on;
    p.classList.toggle("open", !!on);
  }
  function remoteParticipantsOf(r) {
    var m = r && (r.remoteParticipants || r.participants);
    return m || new Map();
  }
  function publicationsOf(p) {
    var m = p && (p.trackPublications || p.tracks);
    return m || new Map();
  }

  // ─── Server config ──────────────────────────────────────────────────
  function fetchConfig() {
    if (configCache) return Promise.resolve(configCache);
    return fetch("/api/wb_meet/config", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) { configCache = j; return j; });
  }

  // ─── LiveKit lib loader ─────────────────────────────────────────────
  function ensureLib() {
    if (lk) return Promise.resolve(lk);
    return import(/* @vite-ignore */ LIVEKIT_CDN).then(function (mod) {
      lk = mod;
      return mod;
    });
  }

  // ─── Token / slot API ───────────────────────────────────────────────
  function requestToken(roomCode, name, prevIdentity) {
    var body = { room: roomCode, name: name || "Гость" };
    if (prevIdentity) body.identity = prevIdentity;
    return fetch("/api/wb_meet/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok, status: r.status, data: j }; });
    });
  }

  function releaseToken() {
    if (!roomId || !identity) return Promise.resolve();
    return fetch("/api/wb_meet/release", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ room: roomId, identity: identity })
    }).catch(function () {});
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(function () {
      if (!roomId || !identity) return;
      fetch("/api/wb_meet/heartbeat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ room: roomId, identity: identity })
      }).catch(function () {});
    }, 60 * 1000);
  }
  function stopHeartbeat() {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = 0; }
  }

  // ─── Wake Lock (не гасить экран на телефоне) ────────────────────────
  function acquireWakeLock() {
    try {
      if (!("wakeLock" in navigator) || wakeLock) return;
      navigator.wakeLock.request("screen").then(function (wl) {
        wakeLock = wl;
        wl.addEventListener("release", function () { wakeLock = null; });
      }).catch(function () {});
    } catch (e) {}
  }
  function releaseWakeLock() {
    try { if (wakeLock) { wakeLock.release(); wakeLock = null; } } catch (e) {}
  }

  // ─── Participant grid ───────────────────────────────────────────────
  function tileFor(participant, isLocal) {
    var id = "wbMeetTile-" + participant.identity;
    var existing = document.getElementById(id);
    if (existing) return existing;
    var tile = document.createElement("div");
    tile.id = id;
    tile.className = "wbm-tile" + (isLocal ? " wbm-tile-self" : "");
    tile.innerHTML =
      '<div class="wbm-video-wrap"></div>' +
      '<div class="wbm-name"></div>' +
      '<div class="wbm-mute" hidden></div>';
    tile.querySelector(".wbm-name").textContent = (participant.name || "Гость") + (isLocal ? " (вы)" : "");
    participantsEl.appendChild(tile);
    refreshGrid();
    return tile;
  }

  function removeTile(participant) {
    var id = "wbMeetTile-" + participant.identity;
    var el = document.getElementById(id);
    if (el) { el.remove(); refreshGrid(); }
  }

  function refreshGrid() {
    if (!participantsEl) return;
    var n = participantsEl.children.length || 1;
    var cols = n <= 1 ? 1 : (n <= 4 ? 2 : (n <= 9 ? 3 : 4));
    participantsEl.style.gridTemplateColumns = "repeat(" + cols + ", 1fr)";
  }

  function attachTrack(participant, pub, track) {
    if (!room || !track) return;
    var isLocal = participant === room.localParticipant;
    var tile = tileFor(participant, isLocal);
    var wrap = tile.querySelector(".wbm-video-wrap");
    if (!wrap) return;
    if (track.kind === "video") {
      var prev = wrap.querySelector("video");
      if (prev) prev.remove();
      var el = track.attach();
      el.classList.add("wbm-video");
      if (isLocal) el.muted = true;
      wrap.appendChild(el);
    } else if (track.kind === "audio") {
      if (isLocal) return; // свой микрофон не воспроизводим
      var aprev = wrap.querySelector("audio");
      if (aprev) aprev.remove();
      var a = track.attach();
      a.style.display = "none";
      wrap.appendChild(a);
    }
  }

  function detachTrack(participant, pub, track) {
    try { track.detach().forEach(function (el) { el.remove(); }); } catch (e) {}
  }

  function bindParticipant(p) {
    if (!room || !lk || !p) return;
    tileFor(p, p === room.localParticipant);
    publicationsOf(p).forEach(function (pub) {
      if (pub && pub.track && (pub.isSubscribed || p === room.localParticipant)) attachTrack(p, pub, pub.track);
    });
    if (p.__wbBound) return;
    p.__wbBound = true;
    p.on(lk.ParticipantEvent.TrackSubscribed, function (track, pub) { attachTrack(p, pub, track); });
    p.on(lk.ParticipantEvent.TrackUnsubscribed, function (track, pub) { detachTrack(p, pub, track); });
    p.on(lk.ParticipantEvent.IsSpeakingChanged, function (speaking) {
      var tile = document.getElementById("wbMeetTile-" + p.identity);
      if (tile) tile.classList.toggle("speaking", !!speaking);
    });
  }

  // ─── Panel UI ───────────────────────────────────────────────────────
  function ensurePanel() {
    if (panel()) return;
    var host = document.getElementById("wbCanvasWrap") || document.body;
    var div = document.createElement("div");
    div.id = "wbMeetPanel";
    div.className = "wb-meet-panel";
    div.hidden = true;
    div.innerHTML =
      '<div class="wbm-head">' +
        '<span class="wbm-title">📹 Групповой звонок</span>' +
        '<span id="wbMeetStatus" class="wbm-status">не подключено</span>' +
        '<button type="button" class="wbm-x" id="wbMeetClose" title="Свернуть">×</button>' +
      '</div>' +
      '<div class="wbm-form" id="wbMeetForm">' +
        '<input type="text" id="wbMeetName" placeholder="Ваше имя" maxlength="40" autocomplete="name">' +
        '<div class="wbm-row">' +
          '<input type="text" id="wbMeetRoom" placeholder="Код комнаты (например: math-42)" maxlength="64" autocomplete="off">' +
          '<button type="button" class="wbm-btn wbm-btn-primary" id="wbMeetJoin">Войти</button>' +
        '</div>' +
        '<div class="wbm-hint" id="wbMeetHint"></div>' +
      '</div>' +
      '<div class="wbm-room" id="wbMeetRoomView" hidden>' +
        '<div class="wbm-grid" id="wbMeetGrid"></div>' +
        '<div class="wbm-toolbar">' +
          '<button type="button" class="wbm-icon" id="wbMeetMic"    title="Микрофон">🎤</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetCam"    title="Камера">🎥</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetShare"  title="Демонстрация экрана">🖥️</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetSummon" title="Позвать всех к себе — все участники увидят ваш участок доски">📣</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetCopy"   title="Скопировать ссылку">🔗</button>' +
          '<button type="button" class="wbm-icon wbm-icon-danger" id="wbMeetLeave" title="Выйти">📴</button>' +
        '</div>' +
      '</div>';
    host.appendChild(div);

    participantsEl = $("wbMeetGrid");
    $("wbMeetClose").addEventListener("click", function () { showPanel(false); });
    $("wbMeetJoin").addEventListener("click", onJoinClick);
    $("wbMeetRoom").addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); onJoinClick(); }
    });
    $("wbMeetMic").addEventListener("click", toggleMic);
    $("wbMeetCam").addEventListener("click", toggleCam);
    $("wbMeetShare").addEventListener("click", toggleShare);
    $("wbMeetSummon").addEventListener("click", summonAll);
    $("wbMeetCopy").addEventListener("click", copyLink);
    $("wbMeetLeave").addEventListener("click", leaveRoom);

    var params = new URLSearchParams(window.location.search);
    var preRoom = params.get("meet") || localStorage.getItem("wb_meet_room_last") || "";
    var preName = localStorage.getItem("wb_meet_name_last") || "";
    if (preRoom) $("wbMeetRoom").value = preRoom;
    if (preName) $("wbMeetName").value = preName;
  }

  function ensureTopBarButton() {
    if ($("wbMeetToggle")) return;
    var actions = document.querySelector("#drw-pane-whiteboard .top-bar .actions.zoom");
    if (!actions) return;
    fetchConfig().then(function (cfg) {
      if (!cfg || !cfg.enabled) {
        try {
          console.info("[wb_meet] Групповой звонок выключен: на сервере не заданы " +
            "LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET. См. docs/livekit_setup.md.");
        } catch (e) {}
        return;
      }
      if ($("wbMeetToggle")) return;
      var btn = document.createElement("button");
      btn.id = "wbMeetToggle";
      btn.className = "icon-btn icon-btn-meet";
      btn.title = "Групповой звонок (до " + (cfg.max || 10) + " человек)";
      btn.type = "button";
      btn.textContent = "📹";
      btn.addEventListener("click", function () {
        ensurePanel();
        showPanel(true);
        var hint = $("wbMeetHint");
        if (hint) hint.textContent = "Можно пригласить до " + (cfg.max || 10) + " человек.";
        var joinBtn = $("wbMeetJoin");
        if (joinBtn) joinBtn.disabled = false;
        var inp = $("wbMeetRoom");
        if (inp && !room) inp.focus();
      });
      var clearBtn = document.getElementById("wbClear");
      if (clearBtn && clearBtn.parentNode === actions) actions.insertBefore(btn, clearBtn);
      else actions.appendChild(btn);
    }).catch(function () {});
  }

  function onJoinClick() {
    var rid = ($("wbMeetRoom").value || "").trim().replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
    var nm  = ($("wbMeetName").value || "").trim().slice(0, 40) || "Гость";
    if (!rid) { setStatus("Введите код комнаты", "warn"); $("wbMeetRoom").focus(); return; }
    try {
      localStorage.setItem("wb_meet_room_last", rid);
      localStorage.setItem("wb_meet_name_last", nm);
    } catch (e) {}
    wantConnected = true;
    rejoinAttempt = 0;
    identity = null;           // новый вход — новый identity
    roomId = rid; displayName = nm;
    joinRoom(rid, nm, false);
  }

  // ─── Join / rejoin ──────────────────────────────────────────────────
  function joinRoom(rid, name, isRejoin) {
    if (connecting) return;
    connecting = true;
    setStatus(isRejoin ? "Переподключаемся…" : "Загрузка LiveKit…", isRejoin ? "warn" : "");
    var newRoom = null;

    Promise.all([ensureLib(), fetchConfig()]).then(function (arr) {
      var cfg = arr[1];
      if (!cfg.enabled) { setStatus("Сервер не настроен", "err"); wantConnected = false; return null; }
      if (!isRejoin) setStatus("Получаем токен…");
      return requestToken(rid, name, isRejoin ? identity : null);
    }).then(function (r) {
      if (!r) return;
      if (!r.ok) {
        if (r.status === 503) { setStatus("LiveKit не настроен на сервере", "err"); wantConnected = false; }
        else if (r.status === 409) { setStatus("Комната заполнена (макс. 10)", "err"); wantConnected = false; }
        else if (r.status === 400) { setStatus("Неверный код комнаты", "err"); wantConnected = false; }
        else { throw new Error("token_http_" + r.status); }
        return;
      }
      var data = r.data;
      roomId = data.room;
      identity = data.identity;
      displayName = data.name;
      setStatus(isRejoin ? "Переподключаемся…" : "Подключаемся к LiveKit…", isRejoin ? "warn" : "");

      // Старый объект комнаты (если остался) — закрываем тихо.
      if (room) { var old = room; room = null; try { old.disconnect(); } catch (e) {} }

      newRoom = new lk.Room({
        adaptiveStream: true,
        dynacast: true,
        videoCaptureDefaults: { resolution: lk.VideoPresets.h540.resolution },
      });
      room = newRoom;

      newRoom.on(lk.RoomEvent.ParticipantConnected, function (p) { if (room === newRoom) bindParticipant(p); });
      newRoom.on(lk.RoomEvent.ParticipantDisconnected, function (p) { removeTile(p); });
      newRoom.on(lk.RoomEvent.TrackSubscribed, function (track, pub, p) { if (room === newRoom) attachTrack(p, pub, track); });
      newRoom.on(lk.RoomEvent.TrackUnsubscribed, function (track, pub, p) { detachTrack(p, pub, track); });
      newRoom.on(lk.RoomEvent.LocalTrackPublished, function (pub, p) { if (room === newRoom && pub && pub.track) attachTrack(p, pub, pub.track); });
      newRoom.on(lk.RoomEvent.LocalTrackUnpublished, function (pub) { if (pub && pub.track) detachTrack(null, pub, pub.track); });
      newRoom.on(lk.RoomEvent.Reconnecting, function () { if (room === newRoom) setStatus("Связь нестабильна, восстанавливаем…", "warn"); });
      newRoom.on(lk.RoomEvent.Reconnected, function () { if (room === newRoom) setStatus("В разговоре", "ok"); });
      newRoom.on(lk.RoomEvent.Disconnected, function (reason) {
        if (room !== newRoom) return;      // событие от уже заменённой комнаты
        try { window.dispatchEvent(new CustomEvent("wb-meet-leave", { detail: { rejoining: wantConnected } })); } catch (e) {}
        if (!wantConnected) { tearDownView(); return; }
        try { console.warn("[wb_meet] disconnected, reason=", reason, "— scheduling rejoin"); } catch (e) {}
        scheduleRejoin();
      });
      newRoom.on(lk.RoomEvent.ActiveSpeakersChanged, function (speakers) {
        if (!participantsEl) return;
        var ids = new Set(speakers.map(function (s) { return s.identity; }));
        Array.from(participantsEl.children).forEach(function (tile) {
          var id = tile.id.replace("wbMeetTile-", "");
          tile.classList.toggle("speaking", ids.has(id));
        });
      });

      return newRoom.connect(data.url, data.token).then(function () {
        if (room !== newRoom) return;
        rejoinAttempt = 0;
        $("wbMeetForm").hidden = true;
        $("wbMeetRoomView").hidden = false;
        if (participantsEl) participantsEl.innerHTML = "";
        bindParticipant(newRoom.localParticipant);
        remoteParticipantsOf(newRoom).forEach(bindParticipant);
        setStatus("В разговоре", "ok");
        startHeartbeat();
        acquireWakeLock();
        try {
          window.dispatchEvent(new CustomEvent("wb-meet-room", {
            detail: { room: newRoom, lk: lk, identity: identity, name: displayName, roomId: roomId, rejoin: !!isRejoin }
          }));
        } catch (e) { console.warn("[wb_meet] dispatch failed:", e); }
        return Promise.all([
          newRoom.localParticipant.setMicrophoneEnabled(!!prefs.mic).catch(function () {}),
          newRoom.localParticipant.setCameraEnabled(!!prefs.cam).catch(function () {}),
        ]).then(syncToggleButtons);
      });
    }).catch(function (e) {
      console.warn("[wb_meet] join err", e);
      if (e && e.name === "NotAllowedError") {
        setStatus("Доступ к камере/микрофону запрещён", "err");
        return;
      }
      if (wantConnected) scheduleRejoin();
      else setStatus("Не удалось подключиться", "err");
    }).finally(function () { connecting = false; });
  }

  function scheduleRejoin() {
    if (!wantConnected) return;
    if (rejoinTimer) return;
    rejoinAttempt++;
    if (rejoinAttempt > MAX_REJOIN_ATTEMPTS) {
      wantConnected = false;
      setStatus("Связь потеряна. Нажмите «Войти», чтобы вернуться", "err");
      tearDownView();
      return;
    }
    var delay = Math.min(15000, 1000 * Math.pow(2, Math.min(rejoinAttempt - 1, 4)));
    setStatus("Связь прервана — переподключаемся (" + rejoinAttempt + ")…", "warn");
    rejoinTimer = setTimeout(function () {
      rejoinTimer = 0;
      if (!wantConnected) return;
      if (room && room.state === "connected") return;
      joinRoom(roomId, displayName, true);
    }, delay);
  }

  function rejoinNowIfNeeded() {
    if (!wantConnected || connecting) return;
    if (room && room.state === "connected") { acquireWakeLock(); return; }
    if (rejoinTimer) { clearTimeout(rejoinTimer); rejoinTimer = 0; }
    joinRoom(roomId, displayName, true);
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") rejoinNowIfNeeded();
  });
  window.addEventListener("online", rejoinNowIfNeeded);
  window.addEventListener("pageshow", function (e) { if (e.persisted) rejoinNowIfNeeded(); });

  function tearDownView() {
    stopHeartbeat();
    releaseWakeLock();
    if (participantsEl) participantsEl.innerHTML = "";
    var f = $("wbMeetForm"), v = $("wbMeetRoomView");
    if (f) f.hidden = false;
    if (v) v.hidden = true;
  }

  function leaveRoom() {
    wantConnected = false;
    if (rejoinTimer) { clearTimeout(rejoinTimer); rejoinTimer = 0; }
    try { window.dispatchEvent(new CustomEvent("wb-meet-leave", { detail: { rejoining: false } })); } catch (e) {}
    var r = room; room = null;
    var p = r ? r.disconnect() : Promise.resolve();
    Promise.resolve(p).catch(function () {}).then(function () {
      releaseToken();
      roomId = null; identity = null;
      tearDownView();
      setStatus("Вы вышли");
    });
  }

  // ─── Toolbar actions ────────────────────────────────────────────────
  function syncToggleButtons() {
    if (!room) return;
    var mic = $("wbMeetMic"), cam = $("wbMeetCam");
    var micOn = !!room.localParticipant.isMicrophoneEnabled;
    var camOn = !!room.localParticipant.isCameraEnabled;
    if (mic) { mic.classList.toggle("off", !micOn); mic.textContent = micOn ? "🎤" : "🔇"; }
    if (cam) { cam.classList.toggle("off", !camOn); cam.textContent = camOn ? "🎥" : "🚫"; }
  }
  function toggleMic() {
    if (!room) return;
    var enabled = room.localParticipant.isMicrophoneEnabled;
    prefs.mic = !enabled;
    room.localParticipant.setMicrophoneEnabled(!enabled).then(syncToggleButtons).catch(function () {});
  }
  function toggleCam() {
    if (!room) return;
    var enabled = room.localParticipant.isCameraEnabled;
    prefs.cam = !enabled;
    room.localParticipant.setCameraEnabled(!enabled).then(syncToggleButtons).catch(function () {});
  }
  function toggleShare() {
    if (!room) return;
    var enabled = room.localParticipant.isScreenShareEnabled;
    room.localParticipant.setScreenShareEnabled(!enabled).then(function () {
      var btn = $("wbMeetShare");
      if (btn) btn.classList.toggle("active", !enabled);
    }).catch(function (e) { console.warn("[wb_meet] screenshare err", e); });
  }
  function summonAll() {
    if (!room || room.state !== "connected") { setStatus("Сначала подключитесь к звонку", "warn"); return; }
    try { window.dispatchEvent(new CustomEvent("wb-meet-summon")); } catch (e) {}
    setStatus("Все участники переведены к вашему участку доски", "ok");
    var btn = $("wbMeetSummon");
    if (btn) { btn.classList.add("active"); setTimeout(function () { btn.classList.remove("active"); }, 1200); }
  }

  function copyLink() {
    if (!roomId) return;
    var url = window.location.origin + window.location.pathname + "?meet=" + encodeURIComponent(roomId);
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(function () { setStatus("Ссылка скопирована"); });
    } else {
      window.prompt("Скопируйте ссылку:", url);
    }
  }

  // Освобождаем слот при закрытии вкладки (переподключение не нужно).
  window.addEventListener("pagehide", function () {
    try {
      if (roomId && identity && navigator.sendBeacon) {
        var blob = new Blob([JSON.stringify({ room: roomId, identity: identity })], { type: "application/json" });
        navigator.sendBeacon("/api/wb_meet/release", blob);
      }
    } catch (e) {}
  });

  // ─── Boot ───────────────────────────────────────────────────────────
  function boot() {
    if (!document.getElementById("wbCanvas")) return;
    ensureTopBarButton();
    var params = new URLSearchParams(window.location.search);
    if (params.get("meet")) { ensurePanel(); showPanel(true); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.WB_MEET = {
    open:  function (rid) { ensurePanel(); showPanel(true); if (rid) { var i = $("wbMeetRoom"); if (i) i.value = rid; } },
    close: function ()    { showPanel(false); },
    leave: leaveRoom,
    summon: summonAll,
    status: function (text, kind) { setStatus(text, kind); },
    state: function () { return { roomId: roomId, identity: identity, name: displayName, connected: !!(room && room.state === "connected"), wantConnected: wantConnected }; }
  };
})();
