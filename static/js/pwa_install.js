/**
 * pwa_install.js — PWA_INSTALL_V5 (22.10.2026).
 *
 * Состояния кнопки:
 *   install    — «📲 Скачать приложение» (пришёл beforeinstallprompt или это iOS)
 *   installing — «⏳ Устанавливаем…» (спиннер, пока браузер ставит приложение)
 *   installed  — зависит от устройства:
 *     • компьютер, Chrome/Edge  — «✅ Открыть приложение»: запуск через протокол web+formyla://open
 *       (protocol_handlers в манифесте). Браузер один раз спросит разрешение, дальше открывает сразу.
 *       Не открылось за 1.5 с — короткое уведомление на 3 с, без вкладок и окон.
 *     • Android / iPhone / Firefox / Safari — браузеры не дают сайту запустить установленное
 *       приложение, поэтому вместо нерабочей кнопки — плашка «✅ Приложение установлено»
 *       (по нажатию — подсказка «откройте FORMYLA с главного экрана»). Плавающая кнопка скрывается.
 *
 * Как понимаем, что уже установлено:
 *   1) событие appinstalled; 2) navigator.getInstalledRelatedApps(); 3) флаг в localStorage.
 *   Если браузер присылает beforeinstallprompt — значит НЕ установлено, верим ему.
 *
 * Статистика: факт установки — один раз на POST /api/pwa/installed.
 * Обновления: проверка новой версии service worker при открытии и возврате на вкладку.
 * Внутри установленного приложения (standalone): кнопок нет, показываем заставку.
 * Подключается автоматически (routes/pwa.py) только разрешённым пользователям (PWA_ALLOWED_USERS).
 */
(function () {
  'use strict';

  var deferredPrompt = null;
  var state = 'hidden';
  var LS_INSTALLED = 'formyla_pwa_installed';
  var LS_DISMISSED = 'formyla_pwa_fab_dismissed';
  var LS_REPORTED = 'formyla_pwa_install_reported';
  var SS_SPLASH = 'formyla_pwa_splash_shown';
  var PROTOCOL_URL = 'web+formyla://open';
  var installingTimer = null;
  var openTimer = null;
  var toastTimer = null;
  var fabEl = null;

  function isStandalone() {
    return (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) ||
           window.navigator.standalone === true;
  }
  function isIOS() {
    var ua = navigator.userAgent || '';
    var iPadOS = navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
    return /iPhone|iPad|iPod/i.test(ua) || iPadOS;
  }
  function isChromium() {
    var ua = navigator.userAgent || '';
    if (/Firefox|FxiOS/i.test(ua)) return false;
    return /Chrome|Chromium|Edg|YaBrowser|OPR/i.test(ua);
  }
  function platform() {
    if (isIOS()) return 'ios';
    if (/Android/i.test(navigator.userAgent || '')) return 'android';
    return 'desktop';
  }
  // Можно ли с этой вкладки запустить установленное приложение.
  function canLaunch() { return platform() === 'desktop' && isChromium(); }

  function lsGet(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function lsSet(key, val) { try { localStorage.setItem(key, val); } catch (e) {} }
  function ssGet(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } }
  function ssSet(key, val) { try { sessionStorage.setItem(key, val); } catch (e) {} }
  function track(name) { try { if (window.plausible) window.plausible(name); } catch (e) {} }

  /* ───── 0. Статистика установок ───── */
  function reportInstall(source) {
    if (lsGet(LS_REPORTED) === '1') return;
    try {
      fetch('/api/pwa/installed', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source, platform: platform() })
      }).then(function (r) {
        if (r.ok) lsSet(LS_REPORTED, '1');
      }).catch(function () {});
    } catch (e) {}
  }

  var LOGO_SVG =
    '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">' +
    '<defs><linearGradient id="pwaGrad" x1="0%" y1="0%" x2="0%" y2="100%">' +
    '<stop offset="0%" stop-color="#38ef7d"/><stop offset="100%" stop-color="#11998e"/></linearGradient></defs>' +
    '<polygon class="pwa-hex" points="50,10 85,30 85,70 50,90 15,70 15,30" fill="none" stroke="url(#pwaGrad)" stroke-width="5"/>' +
    '<polyline class="pwa-line" points="30,40 50,50 50,90" fill="none" stroke="url(#pwaGrad)" stroke-width="5"/>' +
    '<line class="pwa-line" x1="50" y1="50" x2="70" y2="40" stroke="url(#pwaGrad)" stroke-width="5"/>' +
    '<circle class="pwa-dot" cx="50" cy="50" r="5" fill="#fff"/></svg>';

  /* ───── 1. Service worker + автообновление ───── */
  if ('serviceWorker' in navigator) {
    var hadController = !!navigator.serviceWorker.controller;
    var refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (!hadController || refreshing) { hadController = true; return; }
      refreshing = true;
      console.log('[PWA] new version activated — reloading');
      window.location.reload();
    });

    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function (reg) {
        console.log('[PWA] SW registered, scope:', reg.scope);
        navigator.serviceWorker.getRegistrations().then(function (regs) {
          regs.forEach(function (r) { if (r.scope.indexOf('/static/') !== -1) r.unregister(); });
        }).catch(function () {});

        function check() { try { reg.update().catch(function () {}); } catch (e) {} }
        check();
        setInterval(check, 30 * 60 * 1000);
        document.addEventListener('visibilitychange', function () {
          if (document.visibilityState === 'visible') check();
        });
        if (reg.waiting) reg.waiting.postMessage({ type: 'SKIP_WAITING' });
        reg.addEventListener('updatefound', function () {
          var nw = reg.installing;
          if (!nw) return;
          nw.addEventListener('statechange', function () {
            if (nw.state === 'installed' && navigator.serviceWorker.controller) {
              nw.postMessage({ type: 'SKIP_WAITING' });
            }
          });
        });
      }).catch(function (e) { console.warn('[PWA] SW registration failed:', e); });
    });
  }

  /* ───── 2. Заставка внутри установленного приложения ───── */
  function showSplash() {
    if (ssGet(SS_SPLASH)) return;
    ssSet(SS_SPLASH, '1');
    var css = document.createElement('style');
    css.textContent =
      '#pwaSplash{position:fixed;inset:0;z-index:100000;display:flex;flex-direction:column;align-items:center;justify-content:center;' +
      '  background:radial-gradient(1200px 800px at 50% 30%,#1e293b 0%,#0f172a 55%,#020617 100%);color:#fff;' +
      '  font-family:"Segoe UI",system-ui,sans-serif;transition:opacity .45s ease;overflow:hidden}' +
      '#pwaSplash.out{opacity:0;pointer-events:none}' +
      '#pwaSplash::before,#pwaSplash::after{content:"";position:absolute;border-radius:50%;filter:blur(60px);opacity:.35;animation:pwaFloat 6s ease-in-out infinite}' +
      '#pwaSplash::before{width:320px;height:320px;background:#38ef7d;top:-80px;left:-80px}' +
      '#pwaSplash::after{width:380px;height:380px;background:#38bdf8;bottom:-120px;right:-100px;animation-delay:-3s}' +
      '#pwaSplash .logo{width:120px;height:120px;position:relative;z-index:1;filter:drop-shadow(0 0 24px rgba(56,239,125,.45))}' +
      '#pwaSplash .pwa-hex{stroke-dasharray:240;stroke-dashoffset:240;animation:pwaDraw 1.1s ease forwards}' +
      '#pwaSplash .pwa-line{stroke-dasharray:80;stroke-dashoffset:80;animation:pwaDraw .7s ease .6s forwards}' +
      '#pwaSplash .pwa-dot{transform-origin:50px 50px;transform:scale(0);animation:pwaPop .4s cubic-bezier(.2,1.6,.4,1) 1.1s forwards}' +
      '#pwaSplash .title{margin-top:22px;font-size:30px;font-weight:800;font-style:italic;letter-spacing:3px;position:relative;z-index:1;opacity:0;animation:pwaUp .6s ease .9s forwards}' +
      '#pwaSplash .title span{background:linear-gradient(135deg,#38ef7d,#11998e);-webkit-background-clip:text;background-clip:text;color:transparent}' +
      '#pwaSplash .sub{margin-top:8px;color:#94a3b8;font-size:14px;position:relative;z-index:1;opacity:0;animation:pwaUp .6s ease 1.2s forwards}' +
      '#pwaSplash .bar{position:absolute;bottom:calc(48px + env(safe-area-inset-bottom,0px));width:140px;height:3px;border-radius:3px;background:rgba(255,255,255,.1);overflow:hidden}' +
      '#pwaSplash .bar i{display:block;height:100%;width:40%;border-radius:3px;background:linear-gradient(90deg,#38ef7d,#38bdf8);animation:pwaBar 1.2s ease-in-out infinite}' +
      '@keyframes pwaDraw{to{stroke-dashoffset:0}}' +
      '@keyframes pwaPop{to{transform:scale(1)}}' +
      '@keyframes pwaUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}' +
      '@keyframes pwaFloat{0%,100%{transform:translate(0,0)}50%{transform:translate(30px,-25px)}}' +
      '@keyframes pwaBar{0%{transform:translateX(-120%)}100%{transform:translateX(350%)}}';
    var el = document.createElement('div');
    el.id = 'pwaSplash';
    el.innerHTML = '<div class="logo">' + LOGO_SVG + '</div>' +
                   '<div class="title">FORMYLA<span>.net</span></div>' +
                   '<div class="sub">Подготовка к олимпиадам по математике</div>' +
                   '<div class="bar"><i></i></div>';
    (document.head || document.documentElement).appendChild(css);
    (document.body || document.documentElement).appendChild(el);
    setTimeout(function () { el.classList.add('out'); }, 1700);
    setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 2250);
  }

  if (isStandalone()) {
    lsSet(LS_INSTALLED, '1');
    reportInstall('standalone_launch');
    if (document.body) showSplash(); else document.addEventListener('DOMContentLoaded', showSplash);
    return;
  }

  /* ───── 3. Стили ───── */
  var CSS = [
    '.pwa-install-btn{display:none;align-items:center;gap:6px;padding:8px 14px;border-radius:8px;',
    '  border:1px solid rgba(56,239,125,.35);background:rgba(56,239,125,.10);color:#86efac;',
    '  font-weight:600;font-size:14px;font-family:inherit;cursor:pointer;text-decoration:none;white-space:nowrap;transition:background .2s}',
    '.pwa-install-btn:hover{background:rgba(56,239,125,.2)}',
    '.pwa-install-btn.is-visible{display:inline-flex}',
    '.pwa-install-btn[data-state="installed"],#pwaInstallFab[data-state="installed"]{border-color:rgba(56,189,248,.45);color:#7dd3fc;background:rgba(56,189,248,.10)}',
    '.pwa-install-btn[data-state="done"]{border-color:rgba(148,163,184,.3);color:#94a3b8;background:transparent;cursor:default}',
    '.pwa-install-btn[data-state="done"]:hover{background:transparent}',
    '.pwa-install-btn[data-state="installing"],#pwaInstallFab[data-state="installing"]{opacity:.85;pointer-events:none}',
    '.drawer-link.pwa-install-btn{display:none;width:100%;text-align:left;background:transparent;border:none;border-radius:0}',
    '.drawer-link.pwa-install-btn.is-visible{display:flex}',
    '#pwaInstallFab{display:none;position:fixed;right:16px;bottom:calc(76px + env(safe-area-inset-bottom,0px));z-index:9998;',
    '  align-items:center;gap:8px;padding:10px 14px 10px 16px;border-radius:999px;',
    '  border:1px solid rgba(56,239,125,.45);background:rgba(15,23,42,.92);color:#86efac;',
    '  font-weight:600;font-size:14px;font-family:inherit;box-shadow:0 4px 16px rgba(0,0,0,.4);backdrop-filter:blur(6px)}',
    '#pwaInstallFab.is-visible{display:inline-flex}',
    '#pwaInstallFab[data-state="done"]{display:none !important}',
    '#pwaInstallFab button{all:unset;cursor:pointer;font:inherit;color:inherit;display:inline-flex;align-items:center;gap:6px}',
    '#pwaInstallFab .pwa-fab-close{color:#64748b;font-size:16px;line-height:1;padding:2px 4px}',
    '.pwa-spin{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.25);border-top-color:currentColor;border-radius:50%;animation:pwaSpin .8s linear infinite}',
    '@keyframes pwaSpin{to{transform:rotate(360deg)}}',
    '@media (min-width:769px){#pwaInstallFab{display:none !important}}',
    '@media (max-width:768px){.header .pwa-install-btn{display:none !important}}',
    '#pwaToast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom,0px));transform:translate(-50%,20px);z-index:10001;',
    '  max-width:min(92vw,420px);padding:12px 16px;border-radius:12px;background:#1e293b;color:#e2e8f0;border:1px solid rgba(56,189,248,.35);',
    '  font-size:14px;line-height:1.45;font-family:inherit;box-shadow:0 8px 24px rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .25s,transform .25s}',
    '#pwaToast.is-open{opacity:1;transform:translate(-50%,0)}',
    '.pwa-sheet-wrap{position:fixed;inset:0;z-index:10000;display:none;align-items:flex-end;justify-content:center;background:rgba(0,0,0,.55)}',
    '.pwa-sheet-wrap.is-open{display:flex}',
    '.pwa-sheet-wrap .sheet{width:100%;max-width:480px;background:#1e293b;color:#e2e8f0;border-radius:16px 16px 0 0;',
    '  padding:20px 20px calc(24px + env(safe-area-inset-bottom,0px));font-family:inherit;box-shadow:0 -8px 32px rgba(0,0,0,.5)}',
    '.pwa-sheet-wrap h3{margin:0 0 12px;font-size:18px}',
    '.pwa-sheet-wrap ol,.pwa-sheet-wrap p{margin:0 0 16px;line-height:1.6;color:#cbd5e1}',
    '.pwa-sheet-wrap ol{padding-left:22px}',
    '.pwa-sheet-wrap .close{width:100%;padding:12px;border:none;border-radius:10px;background:#334155;color:#fff;font-size:15px;font-weight:600;cursor:pointer}',
    '@media (min-width:769px){.pwa-sheet-wrap{align-items:center}.pwa-sheet-wrap .sheet{border-radius:16px}}'
  ].join('\n');

  function injectCSS() {
    if (document.getElementById('pwaInstallCss')) return;
    var s = document.createElement('style');
    s.id = 'pwaInstallCss';
    s.textContent = CSS;
    document.head.appendChild(s);
  }

  /* ───── 4. Уведомление (toast) ───── */
  function toast(html) {
    var t = document.getElementById('pwaToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'pwaToast';
      t.setAttribute('role', 'status');
      document.body.appendChild(t);
    }
    t.innerHTML = html;
    t.classList.add('is-open');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('is-open'); }, 3000);
  }

  /* ───── 5. Разметка ───── */
  var buttons = [];
  var labels = [];

  var LABELS = {
    install:    '<span>📲</span><span>Скачать приложение</span>',
    installing: '<span class="pwa-spin"></span><span>Устанавливаем…</span>',
    installed:  '<span>✅</span><span>Открыть приложение</span>',
    done:       '<span>✅</span><span>Приложение установлено</span>'
  };

  function makeBtn(className) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = className;
    b.innerHTML = LABELS.install;
    b.addEventListener('click', onClick);
    buttons.push(b); labels.push(b);
    return b;
  }

  function makeSheet(id, html) {
    var w = document.createElement('div');
    w.id = id; w.className = 'pwa-sheet-wrap';
    w.innerHTML = '<div class="sheet">' + html + '</div>';
    w.addEventListener('click', function (e) { if (e.target === w) w.classList.remove('is-open'); });
    var c = w.querySelector('.close'); if (c) c.addEventListener('click', function () { w.classList.remove('is-open'); });
    document.body.appendChild(w);
    return w;
  }
  function openSheet(id) { var s = document.getElementById(id); if (s) s.classList.add('is-open'); }

  function mountButtons() {
    var headerAuth = document.querySelector('.header > div');
    if (headerAuth) headerAuth.insertBefore(makeBtn('pwa-install-btn'), headerAuth.firstChild);

    var drawerNav = document.querySelector('.drawer-nav');
    if (drawerNav) drawerNav.appendChild(makeBtn('drawer-link pwa-install-btn'));

    var onIntake = document.body.classList.contains('page-intake');
    if (!lsGet(LS_DISMISSED) && !onIntake) {
      var fab = document.createElement('div');
      fab.id = 'pwaInstallFab';
      fab.innerHTML = '<button type="button" class="pwa-fab-main">' + LABELS.install + '</button>' +
                      '<button type="button" class="pwa-fab-close" aria-label="Скрыть">✕</button>';
      var main = fab.querySelector('.pwa-fab-main');
      main.addEventListener('click', onClick);
      fab.querySelector('.pwa-fab-close').addEventListener('click', function () {
        fab.classList.remove('is-visible');
        lsSet(LS_DISMISSED, String(Date.now()));
      });
      document.body.appendChild(fab);
      fabEl = fab;
      buttons.push(fab); labels.push(main);
    }

    makeSheet('pwaIosSheet',
      '<h3>📲 Установить FORMYLA на iPhone</h3><ol>' +
      '<li>Откройте сайт в <b>Safari</b>.</li>' +
      '<li>Нажмите кнопку <b>«Поделиться»</b> <span style="display:inline-block;border:1px solid #64748b;border-radius:4px;padding:0 5px;font-size:12px">⬆</span> внизу экрана.</li>' +
      '<li>Выберите <b>«На экран “Домой”»</b> и нажмите <b>«Добавить»</b>.</li></ol>' +
      '<button type="button" class="close">Понятно</button>');

    makeSheet('pwaHintSheet',
      '<h3>📲 Как установить</h3>' +
      '<p>Откройте меню браузера (⋮ или ⋯) и выберите <b>«Установить приложение»</b> или <b>«Добавить на главный экран»</b>.</p>' +
      '<button type="button" class="close">Понятно</button>');
  }

  /* ───── 6. Состояния ───── */
  function setState(next) {
    if (next === 'installed' && !canLaunch()) next = 'done';
    state = next;
    var html = LABELS[next];
    if (!html) { buttons.forEach(function (b) { b.classList.remove('is-visible'); }); return; }
    labels.forEach(function (l) { l.innerHTML = html; });
    buttons.forEach(function (b) { b.setAttribute('data-state', next); b.classList.add('is-visible'); });
    if (fabEl && next === 'done') fabEl.classList.remove('is-visible');
  }

  function markInstalled(reportSource) {
    if (installingTimer) { clearTimeout(installingTimer); installingTimer = null; }
    lsSet(LS_INSTALLED, '1');
    deferredPrompt = null;
    setState('installed');
    if (reportSource) reportInstall(reportSource);
  }

  /* ───── 7. Запуск установленного приложения (только компьютер, Chrome/Edge) ───── */
  function openApp() {
    track('pwa_open_click');
    var left = false;
    function onHide() { if (document.visibilityState === 'hidden') left = true; }
    function onBlur() { left = true; }
    document.addEventListener('visibilitychange', onHide);
    window.addEventListener('blur', onBlur);

    if (openTimer) clearTimeout(openTimer);
    openTimer = setTimeout(function () {
      document.removeEventListener('visibilitychange', onHide);
      window.removeEventListener('blur', onBlur);
      openTimer = null;
      if (left) { track('pwa_open_ok'); return; }
      track('pwa_open_fallback');
      toast('Не получилось открыть автоматически — запустите <b>FORMYLA</b> из меню «Пуск» или с рабочего стола.');
    }, 1500);

    try {
      console.log('[PWA] open via protocol:', PROTOCOL_URL);
      window.location.href = PROTOCOL_URL;
    } catch (e) {
      console.warn('[PWA] openApp failed:', e);
    }
  }

  function onClick() {
    if (state === 'installing') return;
    if (state === 'installed') { openApp(); return; }
    if (state === 'done') {
      toast('Приложение уже установлено — откройте <b>FORMYLA</b> с главного экрана.');
      return;
    }
    track('pwa_install_click');
    if (deferredPrompt) {
      var p = deferredPrompt;
      deferredPrompt = null;
      setState('installing');
      p.prompt();
      p.userChoice.then(function (choice) {
        var ok = choice && choice.outcome === 'accepted';
        console.log('[PWA] install prompt:', choice && choice.outcome);
        if (ok) {
          track('pwa_install_accepted');
          installingTimer = setTimeout(function () { markInstalled('timer'); }, 6000);
        } else {
          setState('install');
          deferredPrompt = null;
        }
      }).catch(function () { setState('install'); });
      return;
    }
    if (isIOS()) { openSheet('pwaIosSheet'); return; }
    openSheet('pwaHintSheet');
  }

  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    deferredPrompt = e;
    lsSet(LS_INSTALLED, '0');
    lsSet(LS_REPORTED, '0');
    if (state !== 'installing') setState('install');
    console.log('[PWA] beforeinstallprompt captured');
  });

  window.addEventListener('appinstalled', function () {
    console.log('[PWA] app installed');
    track('pwa_installed');
    markInstalled('appinstalled');
  });

  function detectInstalled() {
    if (lsGet(LS_INSTALLED) === '1') setState('installed');
    if (navigator.getInstalledRelatedApps) {
      navigator.getInstalledRelatedApps().then(function (apps) {
        if (apps && apps.length && state !== 'installing') markInstalled(null);
      }).catch(function () {});
    }
  }

  // Протокол сработал, но открылась вкладка (обработчик не приложение) — чистим адрес.
  function cleanLaunchParams() {
    if (!/[?&](source=pwa_open|launch=)/.test(window.location.search)) return;
    try {
      var u = new URL(window.location.href);
      u.searchParams.delete('source');
      u.searchParams.delete('launch');
      window.history.replaceState(null, '', u.pathname + (u.search || '') + u.hash);
    } catch (e) {}
  }

  function init() {
    injectCSS();
    mountButtons();
    detectInstalled();
    if (isIOS() && state === 'hidden') setState('install');
    cleanLaunchParams();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
