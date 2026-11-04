/* EXIT_QUESTION_V1: карточка «что остановило?» внизу экрана. Не блокирует сайт, можно пропустить. */
(function () {
  'use strict';
  if (window.ftExitQLoaded) return;
  window.ftExitQLoaded = true;
  var q = null, card = null, tries = 0;

  function busy() {
    // не перекрываем другие опросы и важные окна сайта
    var ids = ['ft-readiness-overlay', 'ft-feedback-overlay', 'ft-linkreq-overlay'];
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      if (el && el.offsetParent !== null && getComputedStyle(el).display !== 'none') return true;
    }
    return window.ftFb && window.ftFb.shown;
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
    });
  }

  function show() {
    if (!q || card) return;
    if (busy()) { if (++tries < 40) setTimeout(show, 3000); return; }
    card = document.createElement('section');
    card.id = 'ft-exit-q';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-labelledby', 'ft-exit-q-title');
    card.style.cssText = 'position:fixed;left:50%;transform:translateX(-50%);bottom:84px;z-index:39000;' +
      'width:min(440px,calc(100vw - 24px));max-height:70vh;overflow:auto;background:var(--card,#141a2e);' +
      'color:var(--text,#e2e8f0);border:1px solid rgba(96,165,250,.5);border-radius:16px;padding:18px 18px 14px;' +
      'box-shadow:0 18px 50px rgba(0,0,0,.5);font-size:15px;';
    var opts = q.options.map(function (o) {
      return '<label style="display:flex;gap:10px;align-items:center;padding:8px 0;cursor:pointer;">' +
        '<input type="radio" name="ftexit" value="' + esc(o.value) + '"> ' + esc(o.label) + '</label>';
    }).join('');
    card.innerHTML =
      '<button type="button" data-skip aria-label="Закрыть" style="position:absolute;top:8px;right:10px;background:none;border:0;color:#94a3b8;font-size:22px;cursor:pointer;line-height:1;">×</button>' +
      '<h2 id="ft-exit-q-title" style="font-size:17px;font-weight:800;margin:0 26px 6px 0;">' + esc(q.question) + '</h2>' +
      '<p style="margin:0 0 8px;color:var(--muted,#94a3b8);font-size:13px;">Ответ поможет нам сделать сайт лучше. Можно пропустить.</p>' +
      '<form><fieldset style="border:0;margin:0;padding:0;"><legend style="position:absolute;left:-9999px;">Варианты ответа</legend>' + opts + '</fieldset>' +
      '<textarea name="text" maxlength="500" rows="2" placeholder="Если хочешь — напиши подробнее" aria-label="Комментарий" ' +
      'style="width:100%;box-sizing:border-box;margin:8px 0;padding:8px;border-radius:8px;border:1px solid #475569;background:#0b1120;color:inherit;font:inherit;"></textarea>' +
      '<div style="display:flex;gap:8px;">' +
      '<button type="submit" style="flex:1;padding:10px;border:0;border-radius:10px;font-weight:700;cursor:pointer;background:#2563eb;color:#fff;">Отправить</button>' +
      '<button type="button" data-skip style="padding:10px 14px;border:1px solid #475569;border-radius:10px;background:transparent;color:inherit;cursor:pointer;">Пропустить</button></div>' +
      '<p role="alert" data-err style="color:#f87171;font-size:13px;margin:8px 0 0;"></p></form>';
    document.body.appendChild(card);
    card.querySelector('form').addEventListener('submit', function (e) { e.preventDefault(); send(false); });
    Array.prototype.forEach.call(card.querySelectorAll('[data-skip]'), function (b) {
      b.addEventListener('click', function () { send(true); });
    });
  }

  function send(dismiss) {
    var picked = card.querySelector('input:checked');
    var err = card.querySelector('[data-err]');
    if (!dismiss && !picked) { err.textContent = 'Выбери вариант или нажми «Пропустить».'; return; }
    var body = {trigger: q.trigger, key: q.key, dismiss: dismiss};
    if (!dismiss) { body.answer = picked.value; body.text = card.querySelector('textarea').value; }
    var headers = {'Content-Type': 'application/json', 'X-Exit-CSRF': q.csrf};
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) headers['X-CSRFToken'] = meta.content;
    fetch('/api/exit-question', {method: 'POST', credentials: 'same-origin', headers: headers, body: JSON.stringify(body)})
      .then(function (r) { return r.json().then(function (d) { if (!r.ok || !d.ok) throw new Error(d.error || 'Ошибка'); }); })
      .then(function () {
        if (dismiss) { card.remove(); card = null; return; }
        card.innerHTML = '<p style="margin:4px 0;font-weight:700;">Спасибо! Это правда помогает.</p>';
        setTimeout(function () { if (card) { card.remove(); card = null; } }, 2500);
      })
      .catch(function (e) { if (dismiss) { card.remove(); card = null; } else { err.textContent = e.message || 'Ошибка сети. Попробуй ещё раз.'; } });
  }

  setTimeout(function () {
    fetch('/api/exit-question/pending', {credentials: 'same-origin', cache: 'no-store'})
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (d) { if (d && d.pending) { q = d; show(); } })
      .catch(function () {});
  }, 4000);
})();
