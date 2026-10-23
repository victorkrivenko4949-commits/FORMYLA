/* SECTION_STATS_V1 — трекер времени по разделам сайта.
 * Подставляется автоматически в каждую HTML-страницу (services/site_stats.py).
 *
 * Правила подсчёта (исправляют старый heartbeat из base.html):
 *  - считаем по реальным меткам времени (Date.now), а не «+30 сек на тик»;
 *  - время идёт ТОЛЬКО пока вкладка видна (visibilityState === 'visible');
 *    при уходе со вкладки таймер останавливается и остаток досылается sendBeacon;
 *  - простой: если 2 минуты нет ни мыши, ни клавиатуры, ни скролла — таймер на паузе;
 *  - события внутри same-origin iframe (атлас 102 методов) тоже считаются активностью;
 *  - две открытые вкладки не удваивают время: сервер начисляет не больше, чем
 *    реально прошло по часам с прошлого удара.
 */
(function () {
  if (window.__ftSiteTime) return;
  window.__ftSiteTime = true;

  var FLUSH_MS = 20000;         // отправка каждые 20 сек
  var IDLE_MS = 120000;         // пауза после 2 мин без действий
  var ENDPOINT = '/api/track/beat';

  var path = location.pathname;
  function sectionFor(p) {
    if (p.indexOf('/daily_tasks') === 0) return 'daily';
    if (p.indexOf('/olympiads/methods') === 0) return 'methods';
    if (p.indexOf('/geometry/draw') === 0 || p.indexOf('/geometry/drawings') === 0) return 'generators';
    return 'other';
  }
  var section = sectionFor(path);

  var lastTick = Date.now();    // момент, с которого ещё не учтено время
  var lastInput = Date.now();   // последняя активность пользователя
  var pending = 0;              // накопленные, ещё не отправленные секунды
  var running = document.visibilityState === 'visible';

  function isIdle(now) { return now - lastInput > IDLE_MS; }

  // Переносим прошедшее время в pending (если вкладка видна и нет простоя).
  function settle() {
    var now = Date.now();
    if (running) {
      var active = now - lastTick;
      if (isIdle(now)) {
        // активными считаем только секунды до начала простоя
        active = Math.max(0, Math.min(active, (lastInput + IDLE_MS) - lastTick));
      }
      if (active > 0) pending += active / 1000;
    }
    lastTick = now;
  }

  function send(useBeacon) {
    var sec = Math.round(pending);
    if (sec <= 0) { pending = 0; return; }
    pending = 0;
    var body = JSON.stringify({ section: section, page: path, seconds: sec });
    if (useBeacon && navigator.sendBeacon) {
      try {
        navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
        return;
      } catch (e) { /* ниже — fetch */ }
    }
    fetch(ENDPOINT, {
      method: 'POST', credentials: 'include', keepalive: true,
      headers: { 'Content-Type': 'application/json' }, body: body
    }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        if (d.ask_section_feedback) showSectionFeedback(d.ask_section_feedback);
        if (d.feedback_pending && typeof window.__ftShowFeedback === 'function') window.__ftShowFeedback();
        window.__ftSiteTotals = d.totals || null;
      }).catch(function () {});
  }

  function flush(useBeacon) { settle(); send(useBeacon); }

  // Активность пользователя
  function touch() {
    var now = Date.now();
    if (isIdle(now)) { lastTick = now; }  // вернулся после простоя — отсчёт заново
    lastInput = now;
  }
  function bindActivity(doc) {
    if (!doc || doc.__ftBound) return;
    doc.__ftBound = true;
    ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'wheel', 'pointerdown'].forEach(function (ev) {
      doc.addEventListener(ev, touch, { passive: true, capture: true });
    });
  }
  bindActivity(document);
  // same-origin iframe (атлас «102 метода» внутри /olympiads/methods)
  function bindFrames() {
    var frames = document.querySelectorAll('iframe');
    for (var i = 0; i < frames.length; i++) {
      try {
        var d = frames[i].contentDocument;
        if (d) bindActivity(d);
        frames[i].addEventListener('load', function () {
          try { bindActivity(this.contentDocument); } catch (e) {}
        });
      } catch (e) { /* чужой origin — игнор */ }
    }
  }
  bindFrames();
  setTimeout(bindFrames, 1500);

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') {
      flush(true);           // остановить и дослать остаток
      running = false;
    } else {
      lastTick = Date.now(); // вернулись — отсчёт с этого момента
      lastInput = lastTick;
      running = true;
    }
  });
  window.addEventListener('pagehide', function () { flush(true); });
  window.addEventListener('beforeunload', function () { flush(true); });
  setInterval(function () { flush(false); }, FLUSH_MS);

  /* ───── Опрос по разделу (102 метода, 15+ минут). Блокирующий, как «Как тебе сайт?» ───── */
  var fbShown = false;
  function showSectionFeedback(sec) {
    if (fbShown || document.getElementById('ft-section-fb')) return;
    fbShown = true;
    fetch('/api/feedback/section/pending', { credentials: 'include' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.pending) { fbShown = false; return; }
        buildModal(d.section || sec, d.question, d.subtitle);
      }).catch(function () { fbShown = false; });
  }

  function buildModal(sec, question, subtitle) {
    var ov = document.createElement('div');
    ov.id = 'ft-section-fb';
    ov.style.cssText = 'display:flex;position:fixed;inset:0;z-index:4001;background:rgba(5,8,18,0.78);backdrop-filter:blur(4px);align-items:center;justify-content:center;padding:16px;';
    ov.innerHTML =
      '<div style="background:var(--card,#141a2e);border:1px solid rgba(244,185,66,0.45);border-radius:16px;max-width:460px;width:100%;padding:26px 24px;box-shadow:0 18px 60px rgba(0,0,0,0.55);color:#fff;">' +
        '<div style="font-size:20px;font-weight:800;margin-bottom:6px;">' + esc(question) + '</div>' +
        '<div style="font-size:14px;color:var(--muted,#9aa3b5);margin-bottom:18px;line-height:1.5;">' + esc(subtitle) + '</div>' +
        '<div id="ft-sfb-stars" style="display:flex;gap:8px;justify-content:center;margin-bottom:6px;">' +
          [1,2,3,4,5].map(function (n) { return '<button type="button" data-star="' + n + '" style="font-size:34px;background:none;border:none;cursor:pointer;color:#5c6478;padding:2px;">★</button>'; }).join('') +
        '</div>' +
        '<div style="display:flex;justify-content:space-between;font-size:11px;color:var(--muted,#9aa3b5);margin-bottom:14px;padding:0 6px;"><span>сложно, непонятно</span><span>всё понятно</span></div>' +
        '<textarea id="ft-sfb-text" rows="3" maxlength="2000" placeholder="Какой метод было тяжело понять и почему? (необязательно)" style="width:100%;box-sizing:border-box;border-radius:10px;padding:10px 12px;font-size:14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);color:inherit;resize:vertical;"></textarea>' +
        '<button id="ft-sfb-submit" type="button" style="width:100%;margin-top:14px;padding:12px;border:none;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;background:linear-gradient(135deg,#F4B942,#e09a1f);color:#1a1205;">Отправить</button>' +
        '<div id="ft-sfb-hint" style="font-size:12px;color:#f87171;margin-top:8px;display:none;text-align:center;">Сначала поставь оценку — звёзды сверху</div>' +
      '</div>';
    document.body.appendChild(ov);
    document.body.style.overflow = 'hidden';
    var chosen = 0, sending = false;
    var stars = ov.querySelectorAll('#ft-sfb-stars button');
    stars.forEach(function (b) {
      b.addEventListener('click', function () {
        chosen = parseInt(b.dataset.star, 10);
        stars.forEach(function (s) { s.style.color = parseInt(s.dataset.star, 10) <= chosen ? '#F4B942' : '#5c6478'; });
        ov.querySelector('#ft-sfb-hint').style.display = 'none';
      });
    });
    document.addEventListener('keydown', function (e) { if (ov.parentNode && e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); } }, true);
    var btn = ov.querySelector('#ft-sfb-submit');
    btn.addEventListener('click', function () {
      if (sending) return;
      if (chosen < 1) { ov.querySelector('#ft-sfb-hint').style.display = 'block'; return; }
      sending = true; btn.textContent = 'Отправляю...';
      fetch('/api/feedback/section', {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section: sec, rating: chosen, text: ov.querySelector('#ft-sfb-text').value || '' })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.ok) { ov.remove(); document.body.style.overflow = ''; }
        else { sending = false; btn.textContent = 'Отправить'; }
      }).catch(function () { sending = false; btn.textContent = 'Отправить'; });
    });
  }
  function esc(s) { return String(s || '').replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }

  // Если вопрос уже ждёт (например, перезагрузили страницу) — показать через 5 сек.
  setTimeout(function () { showSectionFeedback('methods'); }, 5000);

  /* ───── Мелкие удобства без правки шаблонов ───── */
  function enhance() {
    // ссылка «По разделам» на странице /admin/users
    if (path === '/admin/users') {
      var t = document.querySelector('.us-title');
      if (t && !document.getElementById('ft-sections-link')) {
        var a = document.createElement('a');
        a.id = 'ft-sections-link';
        a.href = '/admin/users/sections'; a.textContent = '→ Статистика по разделам (задачи дня / 102 метода / генераторы)';
        a.style.cssText = 'display:inline-block;margin:6px 0 10px;font-size:14px;color:#a78bfa;font-weight:700;';
        t.insertAdjacentElement('afterend', a);
      }
    }
    // ссылка «Мои чертежи» на странице генератора
    if (path.indexOf('/geometry/draw') === 0) {
      var h = document.querySelector('#geoexact h1, .gx h1');
      if (h && !document.getElementById('ft-drawings-link')) {
        var l = document.createElement('a');
        l.id = 'ft-drawings-link';
        l.href = '/geometry/drawings'; l.textContent = '🗂 Мои чертежи';
        l.style.cssText = 'display:inline-block;margin-left:14px;font-size:14px;color:#7dd3fc;font-weight:700;vertical-align:middle;';
        h.appendChild(l);
      }
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', enhance); else enhance();
})();
