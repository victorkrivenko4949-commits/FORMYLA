/* ============================================================
   static/js/streak_how.js — STREAK_V2
   Кнопка «Как работает» рядом с серией (профиль + задачи дня).
   Показывает модальное окно с правилами начисления серии.
   Использование: <button data-streak-how>Как работает</button>
   Скрипт сам навешивает обработчики на все [data-streak-how].
   ============================================================ */

(function () {
  'use strict';

  var MODAL_ID = 'streakHowModal';

  function buildModal() {
    var m = document.createElement('div');
    m.id = MODAL_ID;
    m.setAttribute('role', 'dialog');
    m.setAttribute('aria-modal', 'true');
    m.setAttribute('aria-label', 'Как работает серия');
    m.style.cssText = [
      'position:fixed', 'inset:0', 'z-index:10000', 'display:none',
      'align-items:center', 'justify-content:center',
      'background:rgba(0,0,0,0.55)', 'backdrop-filter:blur(2px)'
    ].join(';');
    m.innerHTML =
      '<div style="max-width:430px;width:calc(100% - 32px);background:#141e2d;' +
      'border:1px solid rgba(56,239,125,0.25);border-radius:14px;padding:26px 26px 22px;' +
      'box-shadow:0 18px 50px rgba(0,0,0,0.45);font-family:inherit;color:#e8eef6;">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">' +
      '<span style="font-size:19px;font-weight:800;">🔥 Как работает серия</span>' +
      '<button type="button" data-streak-how-close aria-label="Закрыть" ' +
      'style="background:none;border:none;color:#8b99ad;font-size:22px;line-height:1;cursor:pointer;padding:2px 6px;">&times;</button>' +
      '</div>' +
      '<div style="font-size:15px;line-height:1.6;color:rgba(232,238,246,0.9);">' +
      'Серия — это дни подряд. Она растёт на <strong>+1 за день</strong>, если ты:' +
      '<ul style="margin:10px 0 10px 18px;padding:0;">' +
      '<li style="margin-bottom:6px;">провёл на сайте <strong>больше 20 минут</strong>, или</li>' +
      '<li><strong>правильно решил хотя бы 1 задачу дня</strong>.</li>' +
      '</ul>' +
      'За один день можно получить только <strong>+1</strong> к серии — даже если выполнил оба условия.' +
      '</div>' +
      '<div style="margin-top:14px;padding:10px 14px;border-radius:10px;background:rgba(20,30,45,0.6);' +
      'border:1px solid rgba(56,239,125,0.15);font-size:13.5px;color:rgba(232,238,246,0.75);">' +
      'Если пропустить день — ни времени, ни верной задачи — серия обнулится. ' +
      'За каждые 3 дня серии даётся выходной, который сохраняет серию.' +
      '</div>' +
      '<button type="button" data-streak-how-close ' +
      'style="margin-top:18px;width:100%;padding:10px;border:none;border-radius:10px;cursor:pointer;' +
      'background:linear-gradient(135deg,#11998e,#38ef7d);color:#08130d;font-weight:700;font-size:15px;">Понятно</button>' +
      '</div>';
    m.addEventListener('click', function (e) {
      if (e.target === m || e.target.closest('[data-streak-how-close]')) hide();
    });
    document.body.appendChild(m);
    return m;
  }

  function show() {
    var m = document.getElementById(MODAL_ID) || buildModal();
    m.style.display = 'flex';
    document.addEventListener('keydown', onKey);
  }

  function hide() {
    var m = document.getElementById(MODAL_ID);
    if (m) m.style.display = 'none';
    document.removeEventListener('keydown', onKey);
  }

  function onKey(e) {
    if (e.key === 'Escape') hide();
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-streak-how]');
    if (btn) { e.preventDefault(); show(); }
  });
})();
