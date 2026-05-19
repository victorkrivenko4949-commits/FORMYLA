// FORMYLA — слушатель приглашений на видеозвонок.
//
// Подключается на КАЖДОЙ странице сайта (через base.html). Раз в ~7 секунд
// дёргает GET /api/wb_call/invites/poll и, если есть новое приглашение от
// друга — рисует всплывающее окно «🤙 N звонит — Принять / Отклонить».
//
// При «Принять»:
//   * если мы уже на странице доски (`/drawing`) — открываем виджет звонка
//     (window.WB_CALL.open(room)) и подставляем код, чтобы пользователю
//     осталось нажать только «Войти» (на самом деле виджет сам всё сделает).
//   * иначе — переходим на `/drawing?room=<code>`. На той странице
//     wb_call.js увидит ?room=... и автоматически откроет панель звонка.
//
// При «Отклонить» — отправляем POST /api/wb_call/invites/dismiss, чтобы
// приглашение не показывалось повторно при F5.

(function () {
  "use strict";

  // Не запускаем дважды (на случай, если файл подключили в нескольких местах).
  if (window.__WB_CALL_LISTENER_INITED) return;
  window.__WB_CALL_LISTENER_INITED = true;

  var POLL_INTERVAL_MS = 7000;
  var SEEN_TTL_MS = 5 * 60 * 1000;        // 5 минут «не повторять то же»
  var _seen = new Map();                  // key -> shown_at
  var _pollTimer = 0;
  var _currentOverlay = null;
  var _audioCtx = null;

  function seenKey(inv) {
    return inv.from_id + "|" + inv.room + "|" + inv.ts;
  }

  function rememberSeen(inv) {
    _seen.set(seenKey(inv), Date.now());
    // Чистим старое
    var now = Date.now();
    _seen.forEach(function (t, k) {
      if (now - t > SEEN_TTL_MS) _seen.delete(k);
    });
  }

  function alreadySeen(inv) {
    return _seen.has(seenKey(inv));
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Короткий «ping» при появлении приглашения (Web Audio API, без файлов).
  function playPing() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      if (!_audioCtx) _audioCtx = new Ctx();
      if (_audioCtx.state === "suspended") _audioCtx.resume();
      var o = _audioCtx.createOscillator();
      var g = _audioCtx.createGain();
      o.type = "sine";
      o.frequency.setValueAtTime(880, _audioCtx.currentTime);
      o.frequency.exponentialRampToValueAtTime(1320, _audioCtx.currentTime + 0.15);
      g.gain.setValueAtTime(0.0001, _audioCtx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.12, _audioCtx.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, _audioCtx.currentTime + 0.35);
      o.connect(g); g.connect(_audioCtx.destination);
      o.start();
      o.stop(_audioCtx.currentTime + 0.4);
      setTimeout(function () {
        var o2 = _audioCtx.createOscillator();
        var g2 = _audioCtx.createGain();
        o2.type = "sine";
        o2.frequency.setValueAtTime(660, _audioCtx.currentTime);
        o2.frequency.exponentialRampToValueAtTime(990, _audioCtx.currentTime + 0.15);
        g2.gain.setValueAtTime(0.0001, _audioCtx.currentTime);
        g2.gain.exponentialRampToValueAtTime(0.10, _audioCtx.currentTime + 0.02);
        g2.gain.exponentialRampToValueAtTime(0.0001, _audioCtx.currentTime + 0.35);
        o2.connect(g2); g2.connect(_audioCtx.destination);
        o2.start();
        o2.stop(_audioCtx.currentTime + 0.4);
      }, 450);
    } catch (e) { /* mute */ }
  }

  function dismissOnServer(inv) {
    try {
      fetch("/api/wb_call/invites/dismiss", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_id: inv.from_id, room: inv.room })
      }).catch(function () {});
    } catch (e) {}
  }

  function ensureStyles() {
    if (document.getElementById("wb-invite-styles")) return;
    var s = document.createElement("style");
    s.id = "wb-invite-styles";
    s.textContent = [
      ".wb-invite-overlay{position:fixed;inset:0;background:rgba(2,6,23,.55);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);z-index:99998;display:flex;align-items:center;justify-content:center;animation:wbInvFade .18s ease}",
      "@keyframes wbInvFade{from{opacity:0}to{opacity:1}}",
      "@keyframes wbInvPop{from{transform:translateY(20px) scale(.96);opacity:0}to{transform:translateY(0) scale(1);opacity:1}}",
      "@keyframes wbInvPulse{0%,100%{box-shadow:0 0 0 0 rgba(74,168,255,.55)}50%{box-shadow:0 0 0 14px rgba(74,168,255,0)}}",
      ".wb-invite-card{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);border:1px solid rgba(74,168,255,.35);border-radius:18px;box-shadow:0 30px 60px rgba(0,0,0,.55);padding:24px 26px;width:min(420px,92vw);color:#e2e8f0;font-family:inherit;animation:wbInvPop .22s ease}",
      ".wb-invite-head{display:flex;align-items:center;gap:14px;margin-bottom:14px}",
      ".wb-invite-avatar{width:54px;height:54px;border-radius:50%;object-fit:cover;background:rgba(255,255,255,.06);flex-shrink:0;animation:wbInvPulse 1.8s ease-in-out infinite}",
      ".wb-invite-avatar-fallback{display:flex;align-items:center;justify-content:center;color:#cbd5e1;font-weight:700;font-size:22px}",
      ".wb-invite-title{font-size:13px;color:#94a3b8;letter-spacing:.4px;text-transform:uppercase;margin:0 0 2px}",
      ".wb-invite-name{font-size:18px;font-weight:700;color:#fff;margin:0;overflow:hidden;text-overflow:ellipsis}",
      ".wb-invite-sub{margin:0 0 16px;color:#94a3b8;font-size:13.5px;line-height:1.45}",
      ".wb-invite-sub b{color:#cbd5e1}",
      ".wb-invite-actions{display:flex;gap:10px}",
      ".wb-invite-btn{flex:1;height:42px;border:none;border-radius:10px;font-weight:600;font-size:14.5px;cursor:pointer;transition:transform .12s ease,background .15s ease}",
      ".wb-invite-btn:hover{transform:translateY(-1px)}",
      ".wb-invite-btn-accept{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff}",
      ".wb-invite-btn-decline{background:rgba(248,113,113,.16);color:#fca5a5;border:1px solid rgba(248,113,113,.35)}",
      ".wb-invite-btn-decline:hover{background:rgba(248,113,113,.28);color:#fff}",
      ".wb-invite-foot{margin-top:12px;font-size:11.5px;color:#64748b;text-align:center}"
    ].join("\n");
    document.head.appendChild(s);
  }

  function showInvite(inv) {
    if (_currentOverlay) return;        // показываем по одному
    ensureStyles();
    rememberSeen(inv);
    playPing();

    var name = escapeHtml(inv.from_name || ("ID " + inv.from_id));
    var avatarHtml = inv.from_avatar
      ? '<img class="wb-invite-avatar" src="' + escapeHtml(inv.from_avatar) + '" alt="">'
      : '<div class="wb-invite-avatar wb-invite-avatar-fallback">' +
          escapeHtml((name[0] || "?").toUpperCase()) +
        '</div>';

    var overlay = document.createElement("div");
    overlay.className = "wb-invite-overlay";
    overlay.innerHTML =
      '<div class="wb-invite-card" role="dialog" aria-modal="true">' +
        '<div class="wb-invite-head">' +
          avatarHtml +
          '<div style="min-width:0;flex:1;">' +
            '<p class="wb-invite-title">\u{1F4F9} \u0412\u0430\u0441 \u0437\u043e\u0432\u0443\u0442 \u043d\u0430 \u0437\u0432\u043e\u043d\u043e\u043a</p>' +
            '<p class="wb-invite-name">' + name + '</p>' +
          '</div>' +
        '</div>' +
        '<p class="wb-invite-sub">' +
          '\u041f\u0440\u0438\u0441\u043e\u0435\u0434\u0438\u043d\u0438\u0442\u044c\u0441\u044f \u043a \u0432\u0438\u0434\u0435\u043e\u0437\u0432\u043e\u043d\u043a\u0443 \u0438 \u043e\u0431\u0449\u0435\u0439 \u0434\u043e\u0441\u043a\u0435 \u0434\u043b\u044f \u0440\u0438\u0441\u043e\u0432\u0430\u043d\u0438\u044f? \u041a\u043e\u043c\u043d\u0430\u0442\u0430: <b>' +
          escapeHtml(inv.room) + '</b>' +
        '</p>' +
        '<div class="wb-invite-actions">' +
          '<button type="button" class="wb-invite-btn wb-invite-btn-decline" data-act="decline">\u041e\u0442\u043a\u043b\u043e\u043d\u0438\u0442\u044c</button>' +
          '<button type="button" class="wb-invite-btn wb-invite-btn-accept" data-act="accept">\u{1F4F9} \u041f\u0440\u0438\u043d\u044f\u0442\u044c</button>' +
        '</div>' +
        '<p class="wb-invite-foot">\u041f\u0440\u0438\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u0435 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0437\u0430\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u0447\u0435\u0440\u0435\u0437 60 \u0441.</p>' +
      '</div>';

    document.body.appendChild(overlay);
    _currentOverlay = overlay;

    function cleanup() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      _currentOverlay = null;
    }

    var autoCloseTimer = setTimeout(function () {
      cleanup();
    }, 60 * 1000);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) {       // клик по затемнению — закрыть без действия
        clearTimeout(autoCloseTimer);
        cleanup();
      }
    });

    overlay.querySelectorAll(".wb-invite-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        clearTimeout(autoCloseTimer);
        var act = btn.getAttribute("data-act");
        dismissOnServer(inv);
        cleanup();
        if (act === "accept") {
          acceptInvite(inv);
        }
      });
    });
  }

  function acceptInvite(inv) {
    var room = inv.room;
    // Если уже на странице доски — открываем виджет прямо здесь.
    var onDrawing = /^\/drawing(\/|$|\?)/.test(window.location.pathname);
    if (onDrawing && window.WB_CALL && typeof window.WB_CALL.open === "function") {
      window.WB_CALL.open(room);
      // Триггерим клик по «Войти», чтобы пользователю не пришлось щёлкать ещё раз.
      setTimeout(function () {
        var startBtn = document.getElementById("wbCallStart");
        if (startBtn) startBtn.click();
      }, 200);
      return;
    }
    // Иначе — переходим на /drawing?room=<code> в этой же вкладке.
    var url = "/drawing?room=" + encodeURIComponent(room);
    window.location.href = url;
  }

  function pollOnce() {
    fetch("/api/wb_call/invites/poll", {
      credentials: "same-origin",
      // Lightweight; avoid global handlers fighting back.
      headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(function (r) {
      if (!r.ok) return { invites: [] };
      return r.json();
    }).then(function (data) {
      var list = (data && data.invites) || [];
      // Берём только самое новое неувиденное приглашение.
      for (var i = list.length - 1; i >= 0; i--) {
        var inv = list[i];
        if (!alreadySeen(inv)) {
          showInvite(inv);
          break;
        }
      }
    }).catch(function (e) {
      // Тихо: пользователь мог разлогиниться, сеть подвисла и т.п.
    });
  }

  function startPolling() {
    pollOnce();
    if (_pollTimer) clearInterval(_pollTimer);
    _pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
  }

  // Стартуем только для авторизованных. Маркер берём из body или meta.
  function isAuthenticated() {
    var m = document.querySelector('meta[name="x-user-authenticated"]');
    if (m && m.getAttribute("content") === "1") return true;
    // Фолбэк: body атрибут (если такой ставится).
    if (document.body && document.body.dataset && document.body.dataset.authenticated === "1") return true;
    // Если ничего нет — всё равно попробуем, /invites/poll сам вернёт пусто.
    return true;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { if (isAuthenticated()) startPolling(); });
  } else {
    if (isAuthenticated()) startPolling();
  }

  // Останавливаем поллинг когда вкладка надолго в фоне (visibilitychange):
  // экономит batteries/сеть, новые приглашения подхватим при возврате.
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = 0; }
    } else {
      if (!_pollTimer && isAuthenticated()) startPolling();
    }
  });
})();
