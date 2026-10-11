/**
 * pwa_install.js — PWA_INSTALL_V1 (11.10.2026).
 *
 * Кнопка «📲 Скачать приложение»:
 *  - Android (Chrome / Edge / Samsung Internet): перехватываем beforeinstallprompt
 *    и по клику показываем системный диалог установки. Событие приходит только
 *    если приложение ещё НЕ установлено — поэтому кнопка не мешает тем, у кого оно есть.
 *  - iPhone / iPad: события нет — по клику показываем подсказку
 *    «Поделиться → На экран “Домой”».
 *  - Внутри уже установленного приложения (standalone) кнопка не создаётся.
 *
 * Также регистрирует /sw.js со scope «/».
 * Подключается автоматически (routes/pwa.py) только разрешённым пользователям
 * (PWA_ALLOWED_USERS) или вручную из base.html.
 */
(function () {
  'use strict';

  var deferredPrompt = null;
  var LS_INSTALLED = 'formyla_pwa_installed';
  var LS_DISMISSED = 'formyla_pwa_fab_dismissed';

  function isStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
           window.navigator.standalone === true;
  }
  function isIOS() {
    var ua = navigator.userAgent || '';
    var iPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return /iPhone|iPad|iPod/i.test(ua) || iPadOS;
  }
  function lsGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function lsSet(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }
  function track(name) {
    try { if (window.plausible) window.plausible(name); } catch (e) {}
  }

  /* ───── 1. Service worker (корневой scope) ───── */
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function (reg) {
        console.log('[PWA] SW registered, scope:', reg.scope);
        // Убираем старую регистрацию /static/sw.js (scope /static/), если осталась у пользователя.
        navigator.serviceWorker.getRegistrations().then(function (regs) {
          regs.forEach(function (r) {
            if (r.scope.indexOf('/static/') !== -1) r.unregister();
          });
        }).catch(function () {});
      }).catch(function (e) { console.warn('[PWA] SW registration failed:', e); });
    });
  }

  if (isStandalone()) { lsSet(LS_INSTALLED, '1'); return; }

  /* ───── 2. Стили ───── */
  var CSS = [
    '.pwa-install-btn{display:none;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;',
    '  border:1px solid rgba(56,239,125,.35);background:rgba(56,239,125,.10);color:#86efac;',
    '  font-weight:600;font-size:14px;font-family:inherit;cursor:pointer;text-decoration:none;white-space:nowrap;transition:background .2s}',
    '.pwa-install-btn:hover{background:rgba(56,239,125,.2)}',
    '.pwa-install-btn.is-visible{display:inline-flex}',
    '.drawer-link.pwa-install-btn{display:none;width:100%;text-align:left;background:transparent;border:none;border-radius:0}',
    '.drawer-link.pwa-install-btn.is-visible{display:flex}',
    '#pwaInstallFab{display:none;position:fixed;right:16px;bottom:calc(76px + env(safe-area-inset-bottom,0px));z-index:9998;',
    '  align-items:center;gap:8px;padding:10px 14px 10px 16px;border-radius:999px;',
    '  border:1px solid rgba(56,239,125,.45);background:rgba(15,23,42,.92);color:#86efac;',
    '  font-weight:600;font-size:14px;font-family:inherit;box-shadow:0 4px 16px rgba(0,0,0,.4);backdrop-filter:blur(6px)}',
    '#pwaInstallFab.is-visible{display:inline-flex}',
    '#pwaInstallFab button{all:unset;cursor:pointer;font:inherit;color:inherit}',
    '#pwaInstallFab .pwa-fab-close{color:#64748b;font-size:16px;line-height:1;padding:2px 4px}',
    '@media (min-width:769px){#pwaInstallFab{display:none !important}}',
    '@media (max-width:768px){.header .pwa-install-btn{display:none !important}}',
    '#pwaIosSheet{position:fixed;inset:0;z-index:10000;display:none;align-items:flex-end;justify-content:center;background:rgba(0,0,0,.55)}',
    '#pwaIosSheet.is-open{display:flex}',
    '#pwaIosSheet .sheet{width:100%;max-width:480px;background:#1e293b;color:#e2e8f0;border-radius:16px 16px 0 0;',
    '  padding:20px 20px calc(24px + env(safe-area-inset-bottom,0px));font-family:inherit;box-shadow:0 -8px 32px rgba(0,0,0,.5)}',
    '#pwaIosSheet h3{margin:0 0 12px;font-size:18px}',
    '#pwaIosSheet ol{margin:0 0 16px;padding-left:22px;line-height:1.6;color:#cbd5e1}',
    '#pwaIosSheet .close{width:100%;padding:12px;border:none;border-radius:10px;background:#334155;color:#fff;font-size:15px;font-weight:600;cursor:pointer}'
  ].join('\n');

  function injectCSS() {
    if (document.getElementById('pwaInstallCss')) return;
    var s = document.createElement('style');
    s.id = 'pwaInstallCss';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ───── 3. Разметка ───── */
  var buttons = [];

  function makeBtn(className, label) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = className;
    b.innerHTML = '<span>📲</span><span>' + label + '</span>';
    b.addEventListener('click', onInstallClick);
    buttons.push(b);
    return b;
  }

  function mountButtons() {
    // Десктоп: в блок авторизации шапки (слева от «Профиль» / «Начать»)
    var headerAuth = document.querySelector('.header > div');
    if (headerAuth) headerAuth.insertBefore(makeBtn('pwa-install-btn', 'Скачать приложение'), headerAuth.firstChild);

    // Мобильное меню (drawer)
    var drawerNav = document.querySelector('.drawer-nav');
    if (drawerNav) drawerNav.appendChild(makeBtn('drawer-link pwa-install-btn', 'Скачать приложение'));

    // Плавающая кнопка для телефона (справа над нижней навигацией).
    // На анкете (/intake) навигация скрыта — кнопку там тоже не показываем.
    var onIntake = document.body.classList.contains('page-intake');
    if (!lsGet(LS_DISMISSED) && !onIntake) {
      var fab = document.createElement('div');
      fab.id = 'pwaInstallFab';
      fab.innerHTML = '<button type="button" class="pwa-fab-main">📲 Скачать приложение</button>' +
                      '<button type="button" class="pwa-fab-close" aria-label="Скрыть">✕</button>';
      fab.querySelector('.pwa-fab-main').addEventListener('click', onInstallClick);
      fab.querySelector('.pwa-fab-close').addEventListener('click', function () {
        fab.classList.remove('is-visible');
        lsSet(LS_DISMISSED, String(Date.now()));
      });
      document.body.appendChild(fab);
      buttons.push(fab);
    }

    // Подсказка для iOS
    var sheet = document.createElement('div');
    sheet.id = 'pwaIosSheet';
    sheet.innerHTML =
      '<div class="sheet">' +
      '  <h3>📲 Установить FORMYLA на iPhone</h3>' +
      '  <ol>' +
      '    <li>Откройте сайт в <b>Safari</b>.</li>' +
      '    <li>Нажмите кнопку <b>«Поделиться»</b> ' +
      '<span style="display:inline-block;border:1px solid #64748b;border-radius:4px;padding:0 5px;font-size:12px">⬆</span> внизу экрана.</li>' +
      '    <li>Выберите <b>«На экран “Домой”»</b> и нажмите <b>«Добавить»</b>.</li>' +
      '  </ol>' +
      '  <button type="button" class="close">Понятно</button>' +
      '</div>';
    sheet.addEventListener('click', function (e) { if (e.target === sheet) closeSheet(); });
    sheet.querySelector('.close').addEventListener('click', closeSheet);
    document.body.appendChild(sheet);
  }

  function showButtons() { buttons.forEach(function (b) { b.classList.add('is-visible'); }); }
  function hideButtons() { buttons.forEach(function (b) { b.classList.remove('is-visible'); }); }
  function openSheet() { var s = document.getElementById('pwaIosSheet'); if (s) s.classList.add('is-open'); }
  function closeSheet() { var s = document.getElementById('pwaIosSheet'); if (s) s.classList.remove('is-open'); }

  /* ───── 4. Логика установки ───── */
  function onInstallClick() {
    track('pwa_install_click');
    if (deferredPrompt) {
      var p = deferredPrompt;
      deferredPrompt = null;            // prompt() можно вызвать только один раз
      p.prompt();
      p.userChoice.then(function (choice) {
        console.log('[PWA] install prompt:', choice && choice.outcome);
        if (choice && choice.outcome === 'accepted') { track('pwa_install_accepted'); hideButtons(); }
      }).catch(function () {});
      return;
    }
    if (isIOS()) { openSheet(); return; }
    // Диалог уже показывался и был закрыт — Chrome пришлёт событие заново только после перезагрузки страницы.
    alert('Откройте меню браузера (⋮) и выберите «Установить приложение» или «Добавить на главный экран».');
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();             // не показывать мини-баннер Chrome автоматически
    deferredPrompt = e;
    lsSet(LS_INSTALLED, '0');       // событие приходит только если приложение НЕ установлено
    showButtons();
    console.log('[PWA] beforeinstallprompt captured');
  });

  window.addEventListener('appinstalled', function () {
    console.log('[PWA] app installed');
    lsSet(LS_INSTALLED, '1');
    track('pwa_installed');
    deferredPrompt = null;
    hideButtons();
  });

  function init() {
    injectCSS();
    mountButtons();               // кнопки создаются скрытыми
    if (isIOS()) showButtons();   // на iOS beforeinstallprompt никогда не придёт — показываем сразу
    // На Android кнопки появятся после beforeinstallprompt (т.е. когда приложение ещё не установлено).
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
