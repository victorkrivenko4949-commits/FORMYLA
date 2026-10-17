/* =====================================================================
 * static/js/dt_solution_guard.js
 * ---------------------------------------------------------------------
 * Баг Лаврика #23: на /daily_tasks поле «Решение» «то нажимается, то нет»,
 * а после нажатия «Ответ» набранный текст сбрасывается — инлайн-скрипт
 * дашборда перерисовывает модалку через innerHTML (приход AI-превью,
 * ошибка валидации, повторное открытие), и textarea создаётся заново пустой.
 *
 * Скрипт автономный и не трогает существующий код модалки:
 *   1) каждый ввод в #dt-solution-input / #dt-answer-input сохраняется
 *      в localStorage с ключом по задаче (id или хэш условия), TTL 24 ч;
 *   2) MutationObserver: как только поле появилось в DOM пустым — текст
 *      возвращается, фокус и курсор восстанавливаются;
 *   3) pointerdown по полю принудительно даёт focus();
 *   4) для отвеченной задачи черновики удаляются.
 *
 * Подключается daily_tasks/solution_guard.py (after_request на blueprint).
 * Отключить без деплоя: DT_SOLUTION_GUARD_DISABLED=1.
 * ===================================================================== */
(function () {
  'use strict';
  if (window.__dtSolutionGuard) return;
  window.__dtSolutionGuard = true;

  var FIELDS = ['dt-solution-input', 'dt-answer-input'];
  var TTL_MS = 24 * 60 * 60 * 1000;
  var PREFIX = 'dt_guard_v1:';
  var lastFocus = { id: null, at: 0, pos: 0 };
  var scheduled = false;

  function hash(s) {
    var h = 0;
    for (var i = 0; i < s.length; i++) { h = ((h << 5) - h + s.charCodeAt(i)) | 0; }
    return String(h);
  }

  function currentItem() {
    try { return window.dtCurrentItem || null; } catch (_) { return null; }
  }

  function itemKey() {
    var it = currentItem();
    if (it && it.id !== undefined && it.id !== null) return 'id:' + it.id;
    var st = document.getElementById('dt-modal-statement');
    var t = st ? (st.textContent || '') : '';
    t = t.replace(/\s+/g, ' ').trim();
    return t ? 'txt:' + hash(t) : null;
  }

  function isAnswered() {
    var it = currentItem();
    if (!it) return false;
    if (it.is_answered) return true;
    return it.user_answer !== null && it.user_answer !== undefined && it.user_answer !== '';
  }

  function storage() {
    try { return window.localStorage; } catch (_) { return null; }
  }

  function save(fieldId, val) {
    var k = itemKey(), s = storage();
    if (!k || !s) return;
    try {
      if (val) s.setItem(PREFIX + k + ':' + fieldId, JSON.stringify({ v: val, t: Date.now() }));
      else s.removeItem(PREFIX + k + ':' + fieldId);
    } catch (_) {}
  }

  function load(fieldId) {
    var k = itemKey(), s = storage();
    if (!k || !s) return '';
    try {
      var raw = s.getItem(PREFIX + k + ':' + fieldId);
      if (!raw) return '';
      var o = JSON.parse(raw);
      if (!o || !o.v || (Date.now() - (o.t || 0)) > TTL_MS) {
        s.removeItem(PREFIX + k + ':' + fieldId);
        return '';
      }
      return o.v;
    } catch (_) { return ''; }
  }

  function clearAll() {
    var k = itemKey(), s = storage();
    if (!k || !s) return;
    for (var i = 0; i < FIELDS.length; i++) {
      try { s.removeItem(PREFIX + k + ':' + FIELDS[i]); } catch (_) {}
    }
  }

  function caretOf(el) {
    return (typeof el.selectionStart === 'number') ? el.selectionStart : (el.value || '').length;
  }

  document.addEventListener('input', function (e) {
    var el = e.target;
    if (!el || FIELDS.indexOf(el.id) === -1) return;
    save(el.id, el.value || '');
    lastFocus = { id: el.id, at: Date.now(), pos: caretOf(el) };
  }, true);

  document.addEventListener('focusin', function (e) {
    var el = e.target;
    if (!el || FIELDS.indexOf(el.id) === -1) return;
    lastFocus = { id: el.id, at: Date.now(), pos: caretOf(el) };
  }, true);

  document.addEventListener('pointerdown', function (e) {
    var el = e.target;
    if (!el || FIELDS.indexOf(el.id) === -1 || el.disabled) return;
    if (document.activeElement !== el) {
      setTimeout(function () { try { el.focus(); } catch (_) {} }, 0);
    }
  }, true);

  function restore() {
    scheduled = false;
    if (isAnswered()) { clearAll(); return; }
    for (var i = 0; i < FIELDS.length; i++) {
      var id = FIELDS[i];
      var el = document.getElementById(id);
      if (!el || el.disabled) continue;
      if ((el.value || '') === '') {
        var draft = load(id);
        if (draft) {
          el.value = draft;
          try { el.dispatchEvent(new Event('input', { bubbles: true })); } catch (_) {}
        }
      }
      if (lastFocus.id === id && (Date.now() - lastFocus.at) < 3000) {
        var ae = document.activeElement;
        if (!ae || ae === document.body || ae === document.documentElement) {
          try {
            el.focus();
            var p = Math.min(lastFocus.pos, (el.value || '').length);
            el.setSelectionRange(p, p);
          } catch (_) {}
        }
      }
    }
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    (window.requestAnimationFrame || window.setTimeout)(restore);
  }

  function start() {
    if (!document.body) { setTimeout(start, 50); return; }
    if (window.MutationObserver) {
      var mo = new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          if (muts[i].addedNodes && muts[i].addedNodes.length) { schedule(); return; }
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
    }
    schedule();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
