/* WISH_SURVEY_V1: «Что ты хочешь от Формулы?» — ответ длиннее 30 символов даёт скидку 30%.
 * Показывается один раз. «Позже» прячет окно до завтра (только в этом браузере).
 * window.ftWishOpen() — открыть принудительно (баннер на /subscribe). */
(function () {
  'use strict';
  if (window.ftWishLoaded) return;
  window.ftWishLoaded = true;

  var SNOOZE_KEY = 'ftWishSnoozeUntil';
  var data = null, overlay = null, prevOverflow = '', prevFocus = null, waitTimer = null;

  function snoozed() {
    try { return Number(localStorage.getItem(SNOOZE_KEY) || 0) > Date.now(); } catch (e) { return false; }
  }
  function snooze() {
    try { localStorage.setItem(SNOOZE_KEY, String(Date.now() + 24 * 3600 * 1000)); } catch (e) {}
  }
  function norm(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }
  // Длина в символах, как считает сервер (эмодзи = 1, а не 2 UTF-16 единицы).
  function clen(s) { return Array.from(s).length; }
  // \p{L} через конструктор: старый браузер без его поддержки не уронит весь скрипт.
  var LETTER_RE;
  try { LETTER_RE = new RegExp('\\p{L}', 'gu'); } catch (e) { LETTER_RE = /[A-Za-zА-Яа-яЁё]/g; }
  function letters(s) { var m = s.match(LETTER_RE); return m ? m.length : 0; }
  function el(tag, css, txt) {
    var n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (txt != null) n.textContent = txt;
    return n;
  }

  function load(cb) {
    if (data) { cb(data); return; }
    fetch('/api/wish-survey/pending', {credentials: 'same-origin', cache: 'no-store'})
      .then(function (r) { if (!r.ok) throw new Error(); return r.json(); })
      .then(function (d) { data = d; cb(d); })
      .catch(function () {});
  }

  function otherOverlayVisible() {
    if (window.ftFb && window.ftFb.shown) return true;
    if (document.getElementById('ft-readiness-overlay')) return true;
    // Другие окна сайта: запрос учителя/родителя, «какие олимпиады», «перепройди анкету».
    var ids = ['ft-linkreq-overlay', 'ft-notice-overlay', 'ft-retake-overlay', 'ft-feedback-overlay'];
    for (var i = 0; i < ids.length; i++) {
      var o = document.getElementById(ids[i]);
      if (o && o.style.display && o.style.display !== 'none') return true;
    }
    return false;
  }

  function priceList(prices) {
    var box = el('div', 'margin:10px 0 0;display:grid;gap:6px;');
    (prices || []).forEach(function (p) {
      var row = el('div', 'display:flex;justify-content:space-between;gap:10px;padding:8px 12px;border-radius:10px;background:rgba(244,185,66,.08);font-size:15px;');
      row.appendChild(el('span', '', '«' + p.title + '»'));
      var price = el('span', 'white-space:nowrap;');
      price.appendChild(el('s', 'opacity:.6;margin-right:8px;', p.base + ' ₽'));
      price.appendChild(el('b', 'color:#F4B942;', p.amount + ' ₽'));
      row.appendChild(price);
      box.appendChild(row);
    });
    return box;
  }

  function close(markSnooze) {
    if (!overlay) return;
    if (markSnooze) snooze();
    overlay.remove(); overlay = null;
    document.removeEventListener('keydown', onKey, true);
    document.body.style.overflow = prevOverflow;
    if (prevFocus && prevFocus.isConnected) prevFocus.focus();
  }

  function onKey(e) {
    if (!overlay) return;
    if (e.key === 'Escape') { e.preventDefault(); close(true); return; }
    if (e.key !== 'Tab') return;
    var nodes = Array.from(overlay.querySelectorAll('textarea, a, button:not(:disabled)'));
    if (!nodes.length) return;
    var first = nodes[0], last = nodes[nodes.length - 1];
    if (e.shiftKey && (document.activeElement === first || !overlay.contains(document.activeElement))) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && (document.activeElement === last || !overlay.contains(document.activeElement))) {
      e.preventDefault(); first.focus();
    }
  }

  function show(d) {
    if (overlay) return;
    if (otherOverlayVisible()) {
      clearTimeout(waitTimer);
      waitTimer = setTimeout(function () { show(d); }, 400);
      return;
    }
    var need = d.min_chars || 31;
    prevFocus = document.activeElement;
    prevOverflow = document.body.style.overflow;

    overlay = el('div', 'position:fixed;inset:0;z-index:41000;background:rgba(5,8,18,.78);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;');
    overlay.id = 'ft-wish-overlay';
    var card = el('form', 'background:var(--card,#141a2e);color:var(--text,#e2e8f0);border:1px solid rgba(244,185,66,.45);border-radius:16px;max-width:460px;width:100%;box-sizing:border-box;padding:22px 18px;box-shadow:0 18px 60px rgba(0,0,0,.55);max-height:90vh;overflow:auto;');
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    card.setAttribute('aria-labelledby', 'ft-wish-title');

    var title = el('h2', 'font-size:20px !important;line-height:1.3;font-weight:800;margin:0 0 8px;', 'Что ты хочешь от Формулы?');
    title.id = 'ft-wish-title';
    card.appendChild(title);
    if (d.offer) {
      card.appendChild(el('p', 'font-size:15px;margin:0 0 4px;color:var(--text,#e2e8f0);',
        'Напиши честно, чего ждёшь от сайта. Ответ длиннее 30 символов — и ты получаешь скидку ' + d.percent + '% на Premium, на оба тарифа:'));
      card.appendChild(priceList(d.prices));
    } else {
      card.appendChild(el('p', 'font-size:15px;margin:0;', 'Напиши, чего вы ждёте от сайта, — мы читаем каждый ответ.'));
    }

    var ta = document.createElement('textarea');
    ta.id = 'ft-wish-text';
    ta.maxLength = 2000;
    ta.rows = 4;
    ta.placeholder = 'Например: хочу подготовиться к региональному этапу и научиться решать геометрию…';
    ta.setAttribute('aria-label', 'Твой ответ');
    ta.style.cssText = 'display:block;width:100% !important;box-sizing:border-box;margin:14px 0 6px;padding:12px !important;border-radius:12px;border:1px solid rgba(148,163,184,.35);background:rgba(255,255,255,.04);color:inherit;font:inherit;font-size:15px;line-height:1.4;resize:vertical;min-height:96px;';
    card.appendChild(ta);

    var counter = el('p', 'font-size:13px;margin:0 0 12px;color:var(--muted,#94a3b8);');
    counter.setAttribute('aria-live', 'polite');
    card.appendChild(counter);

    var btn = el('button', 'width:100%;padding:12px;border:0;border-radius:10px;font-size:15px;font-weight:700;cursor:pointer;background:linear-gradient(135deg,#F4B942,#e09a1f);color:#1a1205;');
    btn.type = 'submit';
    card.appendChild(btn);
    var later = el('button', 'width:100%;margin-top:8px;padding:10px;border:0;border-radius:10px;font-size:14px;cursor:pointer;background:transparent;color:var(--muted,#94a3b8);', 'Позже');
    later.type = 'button';
    card.appendChild(later);
    var err = el('p', 'color:#f87171;font-size:13px;margin:10px 0 0;');
    err.setAttribute('role', 'alert');
    card.appendChild(err);

    function update() {
      var v = norm(ta.value);
      if (!d.offer) {
        counter.textContent = '';
        btn.textContent = 'Отправить';
        btn.disabled = !v;
        return;
      }
      if (clen(v) >= need && letters(v) >= 10) {
        counter.textContent = '✓ Скидка ' + d.percent + '% будет твоей';
        counter.style.color = '#4ade80';
        btn.textContent = 'Отправить и получить скидку ' + d.percent + '%';
      } else {
        var left = Math.max(need - clen(v), 0);
        counter.textContent = left > 0
          ? 'Ещё ' + left + ' ' + plural(left) + ' — и скидка ' + d.percent + '% твоя'
          : 'Напиши словами — так мы поймём, что тебе нужно';
        counter.style.color = '';
        btn.textContent = v ? 'Отправить без скидки' : 'Отправить';
      }
      btn.disabled = !v;
    }
    ta.addEventListener('input', update);
    update();

    later.addEventListener('click', function () { close(true); });
    card.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = norm(ta.value);
      if (!v || btn.disabled) return;
      btn.disabled = true; btn.textContent = 'Отправляю...'; err.textContent = '';
      fetch('/api/wish-survey', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-Wish-CSRF': d.csrf},
        body: JSON.stringify({answer: v})
      }).then(function (r) {
        return r.json().then(function (res) {
          if (!r.ok || !res.ok) throw new Error(res.error || 'Не удалось сохранить ответ.');
          return res;
        });
      }).then(function (res) {
        data = null;
        thanks(card, res);
      }).catch(function (e2) {
        err.textContent = e2.message || 'Ошибка сети. Попробуй ещё раз.';
        btn.disabled = false; update();
      });
    });

    overlay.appendChild(card);
    overlay.addEventListener('click', function (e) { e.stopPropagation(); });
    document.body.appendChild(overlay);
    document.body.style.overflow = 'hidden';
    document.addEventListener('keydown', onKey, true);
    ta.focus();
  }

  function plural(n) {
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return 'символ';
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'символа';
    return 'символов';
  }

  function thanks(card, res) {
    card.innerHTML = '';
    card.appendChild(el('h2', 'font-size:20px !important;font-weight:800;margin:0 0 8px;', 'Спасибо за ответ!'));
    if (res.offer && res.discount) {
      card.appendChild(el('p', 'font-size:15px;margin:0;', 'Скидка ' + res.percent + '% активирована. Она применится автоматически при оплате любого тарифа:'));
      card.appendChild(priceList(res.prices));
      var go = el('a', 'display:block;text-align:center;margin-top:14px;padding:12px;border-radius:10px;font-weight:700;text-decoration:none;background:linear-gradient(135deg,#F4B942,#e09a1f);color:#1a1205;', 'Посмотреть тарифы');
      go.href = '/subscribe';
      card.appendChild(go);
    } else if (res.offer && res.used) {
      card.appendChild(el('p', 'font-size:15px;margin:0;', 'Скидка уже была использована при оплате.'));
    } else if (res.offer) {
      card.appendChild(el('p', 'font-size:15px;margin:0;', 'Ответ сохранён. Чтобы получить скидку, напиши подробнее (больше 30 символов) — это можно сделать на странице тарифов.'));
    } else {
      card.appendChild(el('p', 'font-size:15px;margin:0;', 'Мы прочитаем ваш ответ.'));
    }
    var ok = el('button', 'width:100%;margin-top:10px;padding:10px;border:1px solid rgba(148,163,184,.35);border-radius:10px;font-size:14px;cursor:pointer;background:transparent;color:inherit;', 'Закрыть');
    ok.type = 'button';
    ok.addEventListener('click', function () {
      close(false);
      if (res.discount && /^\/(subscribe|payments\/premium\/checkout)/.test(location.pathname)) location.reload();
    });
    card.appendChild(ok);
    ok.focus();
  }

  window.ftWishOpen = function () {
    load(function (d) { if (d.can_improve || d.pending) show(d); });
  };

  if (!snoozed()) {
    setTimeout(function () { load(function (d) { if (d.pending) show(d); }); }, 1500);
  }
})();
