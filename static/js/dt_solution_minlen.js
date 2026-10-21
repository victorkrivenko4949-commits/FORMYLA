/* =====================================================================
 * static/js/dt_solution_minlen.js
 * ---------------------------------------------------------------------
 * «Задачи дня»: для задач уровня >= 2 (2, 3, 4) текст решения должен быть
 * не короче 15 символов — либо прикреплено фото. Уровень 1 не трогаем.
 *
 * Автономный скрипт, инлайн-код дашборда не правит:
 *   1) capture-слушатель клика по кнопке «Ответ» (#dt-submit-btn), Enter в
 *      поле ответа (#dt-answer-input) и submit формы модалки (#dt-answer-form):
 *      если решение короткое и фото нет — отправка блокируется, под полем
 *      решения показывается подсказка, фокус уходит в поле решения;
 *   2) живой счётчик «N / 15 символов» под полем решения (только для уровня >= 2).
 *
 * Серверная проверка дублируется в daily_tasks/solution_minlen.py.
 * Пороги приходят с сервера: window.DT_SOLUTION_MIN_LEN / DT_SOLUTION_MIN_LEVEL.
 * ===================================================================== */
(function () {
  'use strict';
  if (window.__dtSolutionMinLen) return;
  window.__dtSolutionMinLen = true;

  var MIN_LEN = parseInt(window.DT_SOLUTION_MIN_LEN, 10) || 15;
  var MIN_LEVEL = parseInt(window.DT_SOLUTION_MIN_LEVEL, 10) || 2;
  var SOLUTION_IDS = ['dt-solution-input', 'dt-solution-text'];
  var HINT_ID = 'dt-minlen-hint';
  var COUNTER_ID = 'dt-minlen-counter';

  function currentItem() {
    try { return window.dtCurrentItem || null; } catch (_) { return null; }
  }

  function currentLevel() {
    var it = currentItem();
    var v = NaN;
    if (it) {
      v = parseInt(it.difficulty_level != null ? it.difficulty_level : it.difficulty, 10);
    }
    if (isNaN(v) && typeof window.dtCurrentDifficulty === 'number') v = window.dtCurrentDifficulty;
    if (isNaN(v)) {
      var t = document.getElementById('dt-modal-title');
      var m = t && /·\s*(\d+)\s*$/.exec(t.textContent || '');
      if (m) v = parseInt(m[1], 10);
    }
    return isNaN(v) ? 0 : v;
  }

  function solutionField() {
    for (var i = 0; i < SOLUTION_IDS.length; i++) {
      var el = document.getElementById(SOLUTION_IDS[i]);
      if (el && !el.disabled) return el;
    }
    return null;
  }

  function solutionLen(el) {
    var v = (el && el.value) ? String(el.value) : '';
    return v.replace(/\s+/g, ' ').trim().length;
  }

  function hasPhoto() {
    try {
      if (window.dtSolutionPhotoFile) return true;
      if (window.DT_PHOTO_BUFFER && window.DT_PHOTO_BUFFER.length) return true;
      var root = document.getElementById('dt-modal') || document;
      var inputs = root.querySelectorAll('input[type="file"]');
      for (var i = 0; i < inputs.length; i++) {
        if (inputs[i].files && inputs[i].files.length) return true;
      }
      var thumbs = root.querySelectorAll('.dt-photo-thumb, #dt-photo-preview img, #dt-photo-preview-list img');
      if (thumbs.length) return true;
    } catch (_) {}
    return false;
  }

  function isAnswered() {
    var it = currentItem();
    if (!it) return false;
    if (it.is_answered) return true;
    return it.user_answer !== null && it.user_answer !== undefined && it.user_answer !== '';
  }

  function needCheck() {
    return currentLevel() >= MIN_LEVEL && !isAnswered();
  }

  function ensureBlock(id, el, color) {
    var b = document.getElementById(id);
    if (b && b.parentNode) return b;
    b = document.createElement('div');
    b.id = id;
    b.style.cssText = 'font-size:12.5px;line-height:1.4;margin-top:6px;color:' + color + ';';
    if (el.parentNode) el.parentNode.insertBefore(b, el.nextSibling);
    return b;
  }

  function updateCounter() {
    var el = solutionField();
    var old = document.getElementById(COUNTER_ID);
    if (!el || !needCheck()) { if (old) old.remove(); return; }
    var n = solutionLen(el);
    var c = ensureBlock(COUNTER_ID, el, 'rgba(255,255,255,0.45)');
    var ok = n >= MIN_LEN || hasPhoto();
    c.textContent = 'Уровень ' + currentLevel() + ': опиши ход решения минимум на ' + MIN_LEN +
      ' символов или прикрепи фото · ' + n + ' / ' + MIN_LEN;
    c.style.color = ok ? '#3ecf8e' : 'rgba(255,255,255,0.45)';
    if (ok) {
      var h = document.getElementById(HINT_ID);
      if (h) h.remove();
    }
  }

  function showHint(el, n) {
    var h = ensureBlock(HINT_ID, el, '#fca5a5');
    h.textContent = 'Для задачи уровня ' + currentLevel() + ' нужно описать ход решения — минимум ' +
      MIN_LEN + ' символов (сейчас ' + n + '). Или прикрепи фото решения.';
    try { el.focus(); } catch (_) {}
    try { el.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (_) {}
  }

  // true — отправку надо заблокировать
  function violates() {
    if (!needCheck()) return false;
    if (hasPhoto()) return false;
    var el = solutionField();
    if (!el) return false;
    var n = solutionLen(el);
    if (n >= MIN_LEN) return false;
    showHint(el, n);
    return true;
  }

  function block(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
    e.stopPropagation();
  }

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.closest) return;
    var btn = t.closest('#dt-submit-btn, #dt-btn-check');
    if (!btn || btn.disabled) return;
    if (violates()) block(e);
  }, true);

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || e.shiftKey) return;
    var t = e.target;
    if (!t || t.id !== 'dt-answer-input') return;
    if (violates()) block(e);
  }, true);

  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f || f.id !== 'dt-answer-form') return;
    if (violates()) block(e);
  }, true);

  document.addEventListener('input', function (e) {
    var el = e.target;
    if (!el || SOLUTION_IDS.indexOf(el.id) === -1) return;
    updateCounter();
  }, true);

  document.addEventListener('change', function (e) {
    var el = e.target;
    if (el && el.type === 'file') setTimeout(updateCounter, 0);
  }, true);

  var scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    (window.requestAnimationFrame || window.setTimeout)(function () {
      scheduled = false;
      updateCounter();
    });
  }

  function start() {
    if (!document.body) { setTimeout(start, 50); return; }
    if (window.MutationObserver) {
      new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
          if (muts[i].addedNodes && muts[i].addedNodes.length) { schedule(); return; }
        }
      }).observe(document.body, { childList: true, subtree: true });
    }
    schedule();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
