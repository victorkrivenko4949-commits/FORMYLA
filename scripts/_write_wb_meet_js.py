"""One-shot helper: write the full static/js/wb_meet.js.

Run once:
    python scripts/_write_wb_meet_js.py
"""
from pathlib import Path

JS = r"""// FORMYLA Whiteboard - group video meeting via LiveKit.
// Pulls the official LiveKit client (ESM build) from a CDN at runtime,
// so we don't need a build step.  Falls back to "feature disabled" if the
// server says LIVEKIT_* env vars are missing.
//
// UI is mounted lazily — only when the user clicks the "Group meet" button
// in the top-bar of the whiteboard.

(function () {
  "use strict";

  // Loaded once, on first click.  Pinned to a major version that supports
  // the v2 API used below.  The "+esm" path is jsdelivr's ESM gateway.
  var LIVEKIT_CDN = "https://cdn.jsdelivr.net/npm/livekit-client@2.5.10/+esm";

  var lk = null;                // resolved LiveKit module
  var room = null;              // current Room instance
  var roomId = null;
  var identity = null;
  var displayName = null;
  var configCache = null;       // result of /api/wb_meet/config
  var participantsEl = null;    // grid container
  var localContainer = null;

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

  // ─── Token request ──────────────────────────────────────────────────
  function requestToken(roomCode, name) {
    return fetch("/api/wb_meet/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ room: roomCode, name: name || "Гость" })
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
      '<div class="wbm-name">' + (participant.name || "Гость") + (isLocal ? " (вы)" : "") + '</div>' +
      '<div class="wbm-mute" hidden>🔇</div>';
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
    // Pick a reasonable column count for up to 10 tiles.
    var cols = n <= 1 ? 1 : (n <= 4 ? 2 : (n <= 9 ? 3 : 4));
    participantsEl.style.gridTemplateColumns = "repeat(" + cols + ", 1fr)";
  }

  function attachTrack(participant, pub, track) {
    var tile = tileFor(participant, participant === room.localParticipant);
    var wrap = tile.querySelector(".wbm-video-wrap");
    if (!wrap) return;
    if (track.kind === "video") {
      // Replace any previous element so we don't stack on track-republish.
      var prev = wrap.querySelector("video");
      if (prev) prev.remove();
      var el = track.attach();
      el.classList.add("wbm-video");
      if (participant === room.localParticipant) el.muted = true;
      wrap.appendChild(el);
    } else if (track.kind === "audio") {
      // Audio elements are not visible but must be in the DOM to play.
      var aprev = wrap.querySelector("audio");
      if (aprev) aprev.remove();
      var a = track.attach();
      a.style.display = "none";
      wrap.appendChild(a);
    }
  }

  function detachTrack(participant, pub, track) {
    try { track.detach().forEach(function (el) { el.remove(); }); } catch (e) {}
    // Tile may still exist if other tracks remain — don't kill it here.
  }

  function bindParticipant(p) {
    tileFor(p, p === room.localParticipant);
    // Subscribe to existing tracks
    p.tracks.forEach(function (pub) {
      if (pub.isSubscribed && pub.track) attachTrack(p, pub, pub.track);
    });
    p.on(lk.ParticipantEvent.TrackSubscribed, function (track, pub) {
      attachTrack(p, pub, track);
    });
    p.on(lk.ParticipantEvent.TrackUnsubscribed, function (track, pub) {
      detachTrack(p, pub, track);
    });
    p.on(lk.ParticipantEvent.IsSpeakingChanged, function (speaking) {
      var tile = document.getElementById("wbMeetTile-" + p.identity);
      if (tile) tile.classList.toggle("speaking", !!speaking);
    });
  }

  // ─── Public actions ─────────────────────────────────────────────────
  function ensurePanel() {
    if (panel()) return;
    var host = document.getElementById("wbCanvasWrap") || document.body;
    var div = document.createElement("div");
    div.id = "wbMeetPanel";
    div.className = "wb-meet-panel";
    div.hidden = true;
    div.innerHTML =
      '<div class="wbm-head">' +
        '<span class="wbm-title">👥 Групповой звонок</span>' +
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
          '<button type="button" class="wbm-icon" id="wbMeetMic"   title="Микрофон">🎤</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetCam"   title="Камера">📷</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetShare" title="Демонстрация экрана">🖥️</button>' +
          '<button type="button" class="wbm-icon" id="wbMeetCopy"  title="Скопировать ссылку">🔗</button>' +
          '<button type="button" class="wbm-icon wbm-icon-danger" id="wbMeetLeave" title="Выйти">⛔</button>' +
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
    $("wbMeetCopy").addEventListener("click", copyLink);
    $("wbMeetLeave").addEventListener("click", leaveRoom);

    // Prefill room/name from URL ?room= or previous session
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
    var btn = document.createElement("button");
    btn.id = "wbMeetToggle";
    btn.className = "icon-btn icon-btn-meet";
    btn.title = "Групповой звонок (до 10 человек)";
    btn.type = "button";
    btn.textContent = "👥";
    btn.addEventListener("click", function () {
      ensurePanel();
      showPanel(true);
      // Verify the server has LiveKit configured; show a hint if not.
      fetchConfig().then(function (cfg) {
        var hint = $("wbMeetHint");
        if (!cfg.enabled) {
          if (hint) {
            hint.innerHTML =
              "⚠ Сервер ещё не подключён к LiveKit Cloud.<br>" +
              "Админу: задай LIVEKIT_URL, LIVEKIT_API_KEY и LIVEKIT_API_SECRET " +
              "в Environment на Render — после рестарта кнопка заработает.";
          }
          $("wbMeetJoin").disabled = true;
        } else if (hint) {
          hint.textContent = "Можно пригласить до " + (cfg.max || 10) + " человек.";
          $("wbMeetJoin").disabled = false;
        }
        var inp = $("wbMeetRoom");
        if (inp && !room) inp.focus();
      });
    });
    var clearBtn = document.getElementById("wbClear");
    if (clearBtn && clearBtn.parentNode === actions) {
      actions.insertBefore(btn, clearBtn);
    } else {
      actions.appendChild(btn);
    }
  }

  function onJoinClick() {
    var rid = ($("wbMeetRoom").value || "").trim().replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
    var nm  = ($("wbMeetName").value || "").trim().slice(0, 40) || "Гость";
    if (!rid) { setStatus("Введите код комнаты", "warn"); $("wbMeetRoom").focus(); return; }
    try {
      localStorage.setItem("wb_meet_room_last", rid);
      localStorage.setItem("wb_meet_name_last", nm);
    } catch (e) {}
    joinRoom(rid, nm);
  }

  function joinRoom(rid, name) {
    setStatus("Загрузка LiveKit…");
    Promise.all([ensureLib(), fetchConfig()]).then(function (arr) {
      var cfg = arr[1];
      if (!cfg.enabled) {
        setStatus("Сервер не настроен", "err");
        return null;
      }
      setStatus("Получаем токен…");
      return requestToken(rid, name);
    }).then(function (r) {
      if (!r) return;
      if (!r.ok) {
        if (r.status === 503) setStatus("LiveKit не настроен на сервере", "err");
        else if (r.status === 409) setStatus("Комната заполнена (макс. 10)", "err");
        else if (r.status === 400) setStatus("Неверный код комнаты", "err");
        else setStatus("Не удалось получить токен", "err");
        return;
      }
      var data = r.data;
      roomId = data.room;
      identity = data.identity;
      displayName = data.name;
      setStatus("Подключаемся к LiveKit…");

      room = new lk.Room({
        adaptiveStream: true,
        dynacast: true,
        videoCaptureDefaults: { resolution: lk.VideoPresets.h540.resolution },
      });

      // Wire participant events.
      room.on(lk.RoomEvent.ParticipantConnected,    bindParticipant);
      room.on(lk.RoomEvent.ParticipantDisconnected, function (p) { removeTile(p); });
      room.on(lk.RoomEvent.TrackSubscribed, function (track, pub, p) { attachTrack(p, pub, track); });
      room.on(lk.RoomEvent.TrackUnsubscribed, function (track, pub, p) { detachTrack(p, pub, track); });
      room.on(lk.RoomEvent.Disconnected, function () {
        setStatus("Связь прервана", "warn");
        try { window.dispatchEvent(new CustomEvent("wb-meet-leave")); } catch (e) {}
        tearDownView();
      });
      room.on(lk.RoomEvent.ActiveSpeakersChanged, function (speakers) {
        var ids = new Set(speakers.map(function (s) { return s.identity; }));
        Array.from(participantsEl.children).forEach(function (tile) {
          var id = tile.id.replace("wbMeetTile-", "");
          tile.classList.toggle("speaking", ids.has(id));
        });
      });

      return room.connect(data.url, data.token).then(function () {
        // Show the in-call view.
        $("wbMeetForm").hidden = true;
        $("wbMeetRoomView").hidden = false;
        bindParticipant(room.localParticipant);
        room.participants.forEach(bindParticipant);
        setStatus("В разговоре", "ok");
        // Notify wb_collab.js that a LiveKit room is ready so it can
        // hook publishData + DataReceived to broadcast whiteboard ops.
        try {
          window.dispatchEvent(new CustomEvent("wb-meet-room", {
            detail: { room: room, lk: lk, identity: identity, name: displayName, roomId: roomId }
          }));
        } catch (e) { console.warn("[wb_meet] dispatch failed:", e); }
        // Auto-enable camera and microphone (user already granted via the prompt).
        return Promise.all([
          room.localParticipant.setMicrophoneEnabled(true).catch(function () {}),
          room.localParticipant.setCameraEnabled(true).catch(function () {}),
        ]);
      });
    }).catch(function (e) {
      console.warn("[wb_meet] join err", e);
      var msg = (e && e.name === "NotAllowedError")
        ? "Доступ к камере/микрофону запрещён"
        : "Не удалось подключиться";
      setStatus(msg, "err");
    });
  }

  function tearDownView() {
    if (participantsEl) participantsEl.innerHTML = "";
    $("wbMeetForm").hidden = false;
    $("wbMeetRoomView").hidden = true;
  }

  function leaveRoom() {
    // Tell wb_collab.js to detach BEFORE we tear down the room object,
    // otherwise it loses the reference and can't unsubscribe handlers.
    try { window.dispatchEvent(new CustomEvent("wb-meet-leave")); } catch (e) {}
    var p = room ? room.disconnect() : Promise.resolve();
    p.finally(function () {
      releaseToken();
      room = null; roomId = null; identity = null;
      tearDownView();
      setStatus("Вы вышли");
    });
  }

  function toggleMic() {
    if (!room) return;
    var enabled = room.localParticipant.isMicrophoneEnabled;
    room.localParticipant.setMicrophoneEnabled(!enabled).then(function () {
      var btn = $("wbMeetMic");
      btn.classList.toggle("off", enabled);
      btn.textContent = enabled ? "🔇" : "🎤";
    });
  }
  function toggleCam() {
    if (!room) return;
    var enabled = room.localParticipant.isCameraEnabled;
    room.localParticipant.setCameraEnabled(!enabled).then(function () {
      var btn = $("wbMeetCam");
      btn.classList.toggle("off", enabled);
      btn.textContent = enabled ? "🚫" : "📷";
    });
  }
  function toggleShare() {
    if (!room) return;
    var enabled = room.localParticipant.isScreenShareEnabled;
    room.localParticipant.setScreenShareEnabled(!enabled).then(function () {
      var btn = $("wbMeetShare");
      btn.classList.toggle("active", !enabled);
    }).catch(function (e) { console.warn("[wb_meet] screenshare err", e); });
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

  // Best-effort: release the slot when the tab closes.
  window.addEventListener("beforeunload", function () {
    try {
      if (room) room.disconnect();
      if (roomId && identity && navigator.sendBeacon) {
        var blob = new Blob([JSON.stringify({ room: roomId, identity: identity })],
                            { type: "application/json" });
        navigator.sendBeacon("/api/wb_meet/release", blob);
      }
    } catch (e) {}
  });

  // ─── Boot ───────────────────────────────────────────────────────────
  function boot() {
    if (!document.getElementById("wbCanvas")) return;
    ensureTopBarButton();
    // If the user arrived with ?meet=room-code, open the panel for them.
    var params = new URLSearchParams(window.location.search);
    if (params.get("meet")) {
      ensurePanel();
      showPanel(true);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.WB_MEET = {
    open:  function (rid) { ensurePanel(); showPanel(true); if (rid) { var i = $("wbMeetRoom"); if (i) i.value = rid; } },
    close: function ()    { showPanel(false); },
    leave: leaveRoom,
    state: function () { return { roomId: roomId, identity: identity, connected: !!(room && room.state === "connected") }; }
  };
})();
"""

OUT = Path(__file__).resolve().parent.parent / "static" / "js" / "wb_meet.js"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(JS, encoding="utf-8", newline="\n")
print(f"[ok] wrote {OUT} ({len(JS):,} bytes, {JS.count(chr(10))+1} lines)")
