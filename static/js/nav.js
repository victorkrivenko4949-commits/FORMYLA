/**
 * FORMYLA.net - Dropdown Navigation
 */
document.addEventListener('DOMContentLoaded', function () {

  // Open/close dropdowns
  document.querySelectorAll('.nav-dropdown').forEach(function (dd) {
    var toggle = dd.querySelector('.nav-toggle');
    if (!toggle) return;

    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      document.querySelectorAll('.nav-dropdown.open').forEach(function (other) {
        if (other !== dd) other.classList.remove('open');
      });
      dd.classList.toggle('open');
    });
  });

  // Close on outside click
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.nav-dropdown')) {
      document.querySelectorAll('.nav-dropdown.open').forEach(function (o) {
        o.classList.remove('open');
      });
    }
  });

  // Close on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.nav-dropdown.open').forEach(function (o) {
        o.classList.remove('open');
      });
    }
  });

  // Highlight active nav item
  var path = window.location.pathname;

  // «Прочее» active rules: any page that lives under /misc itself,
  // or any of the misc-linked pages (profile, friends, leaderboard, chat,
  // drawing, about, probniks, secrets, problems, matstat, index).
  var miscPaths = ['/misc', '/profile', '/friends', '/leaderboard',
    '/chat', '/drawing', '/about', '/probniks', '/secrets',
    '/problems', '/matstat', '/olympiad-start', '/articles', '/'];
  function isMiscPath(p) {
    for (var i = 0; i < miscPaths.length; i++) {
      if (p === miscPaths[i] || p.indexOf(miscPaths[i] + '/') === 0 ||
          p.indexOf(miscPaths[i] + '?') === 0) {
        return true;
      }
    }
    return false;
  }
  var isMisc = isMiscPath(path);

  document.querySelectorAll('.nav-item, .nav-menu a').forEach(function (a) {
    var href = a.getAttribute('href');
    if (!href || href === '#') return;

    var isActive = false;

    // Для пункта «Прочее» проверяем по списку
    if (href === '/misc') {
      isActive = isMisc;
    } else if (href === path ||
               (href !== '/' && path.indexOf(href) === 0)) {
      isActive = true;
    }

    if (isActive) {
      a.classList.add('active');
      var parent = a.closest('.nav-dropdown');
      if (parent) {
        var parentToggle = parent.querySelector('.nav-toggle');
        if (parentToggle) parentToggle.classList.add('active');
      }
    }
  });

  /* ── PINNED NAV ITEMS (из «Прочее» 📌, localStorage formyla_pinned_misc) ── */
  function unpinById(id) {
    var pinned = [];
    try { pinned = JSON.parse(localStorage.getItem('formyla_pinned_misc') || '[]'); } catch (e) { pinned = []; }
    pinned = pinned.filter(function (x) { return x.id !== id; });
    localStorage.setItem('formyla_pinned_misc', JSON.stringify(pinned));
    refreshPinnedNav();
  }
  function refreshPinnedNav() {
    var container = document.getElementById('pinnedNavItems');
    if (!container) return;
    container.innerHTML = '';
    var pinned = [];
    try { pinned = JSON.parse(localStorage.getItem('formyla_pinned_misc') || '[]'); } catch (e) { pinned = []; }
    pinned.forEach(function (p) {
      if (!p || !p.label || !p.href || p.href === '#') return;
      if (p.id === 'profile') return; // профиль авто-закреплён отдельной синей кнопкой
      // These sections live in Misc; the start link has its own one-hour window.
      var materialPath;
      try { materialPath = new URL(p.href, window.location.origin).pathname.replace(/\/$/, ''); } catch (e) { materialPath = p.href; }
      if (materialPath === '/articles' || materialPath === '/olympiad-start') return;
      var wrap = document.createElement('span');
      wrap.className = 'nav-pinned-item';
      var a = document.createElement('a');
      a.href = p.href;
      a.className = 'nav-item';
      a.textContent = '📌 ' + p.label;
      if (p.id === 'ai_tutor') {
        a.href = '#';
        a.addEventListener('click', function (e) {
          e.preventDefault();
          if (typeof toggleTutorPopup === 'function') {
            if (!window.popupOpen) toggleTutorPopup();
            if (typeof selectAgent === 'function') {
              selectAgent('general', 'Универсальный агент');
            }
          }
        });
      }
      var pinPath = (function (h) {
        try { return new URL(h, window.location.origin).pathname; } catch (e) { return h; }
      })(p.href);
      if (pinPath === path || (pinPath !== '/' && path.indexOf(pinPath) === 0)) {
        a.classList.add('active');
      }
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'nav-unpin-btn';
      btn.title = 'Открепить';
      btn.setAttribute('aria-label', 'Открепить ' + p.label);
      btn.textContent = '✕';
      btn.addEventListener('click', function () { unpinById(p.id); });
      wrap.appendChild(a);
      wrap.appendChild(btn);
      container.appendChild(wrap);
    });
  }
  refreshPinnedNav();
  window.refreshPinnedNav = refreshPinnedNav;

  /* ── ПРОФИЛЬ (авто-закреплён, синяя кнопка справа) ──
     По умолчанию виден. Открепить — наведением на кнопку → красная ✕. */
  function refreshProfilePin() {
    var wrap = document.getElementById('profileNavWrap');
    if (!wrap) return;
    var hidden = false;
    try { hidden = localStorage.getItem('formyla_profile_hidden') === '1'; } catch (e) { hidden = false; }
    wrap.style.display = hidden ? 'none' : 'inline-flex';
  }
  function unpinProfile() {
    try { localStorage.setItem('formyla_profile_hidden', '1'); } catch (e) {}
    refreshProfilePin();
  }
  function repinProfile() {
    try { localStorage.removeItem('formyla_profile_hidden'); } catch (e) {}
    refreshProfilePin();
  }
  refreshProfilePin();
  window.refreshProfilePin = refreshProfilePin;
  window.unpinProfile = unpinProfile;
  window.repinProfile = repinProfile;

});


/* Getting started: persistent one-hour navigation window and misc cards. */
(function () {
  'use strict';
  var START = '/olympiad-start', ARTICLES = '/articles';
  var FIRST_KEY = 'formyla_start_first_visit_v1';
  var DISMISS_KEY = 'formyla_start_notice_dismissed_v1';
  var HOUR = 60 * 60 * 1000;
  var firstVisit = 0, expiryTimer, noticeTimer;
  var navSelector = '.nav a, .nav-item[href], .drawer-link[href], .bottom-nav-item[href], #pinnedNavItems a';

  function read(key) {
    try {
      var value = localStorage.getItem(key);
      if (value !== null) return value;
    } catch (e) {}
    var prefix = encodeURIComponent(key) + '=';
    try {
      var parts = document.cookie.split(';');
      for (var i = 0; i < parts.length; i++) {
        var part = parts[i].trim();
        if (part.indexOf(prefix) === 0) return decodeURIComponent(part.slice(prefix.length));
      }
    } catch (e) {}
    return null;
  }
  function write(key, value) {
    try { localStorage.setItem(key, String(value)); } catch (e) {}
    try {
      document.cookie = encodeURIComponent(key) + '=' + encodeURIComponent(value) +
        '; Max-Age=31536000; Path=/; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
    } catch (e) {}
  }
  function pathOf(link) {
    try { return new URL(link.getAttribute('href'), location.origin).pathname.replace(/\/$/, '') || '/'; }
    catch (e) { return ''; }
  }
  function removeNotice() {
    var notice = document.getElementById('formyla-start-notice');
    if (notice) notice.remove();
  }
  function dismissNotice() {
    write(DISMISS_KEY, '1');
    removeNotice();
  }
  function updateNavigation() {
    var stored = Number(read(FIRST_KEY));
    if (stored > 0 && stored < firstVisit) firstVisit = stored;
    var remaining = HOUR - (Date.now() - firstVisit);
    var expired = remaining <= 0;
    document.documentElement.classList.toggle('formyla-start-expired', expired);
    document.querySelectorAll(navSelector).forEach(function (link) {
      var path = pathOf(link);
      if (path === START || path === ARTICLES) {
        link.setAttribute('data-formyla-material', path === START ? 'start' : 'articles');
      }
    });
    clearTimeout(expiryTimer);
    if (!expired) expiryTimer = setTimeout(updateNavigation, remaining);
    if (expired || read(DISMISS_KEY) === '1') removeNotice();
  }
  function addMiscCards() {
    var page = document.querySelector('.misc-page');
    if (!page) return;
    var group = document.createElement('div');
    group.className = 'misc-group';
    var heading = document.createElement('div');
    heading.className = 'misc-group-title';
    heading.textContent = '📚 Материалы';
    group.appendChild(heading);
    [[START, '📖 С чего начать', 'Первые шаги на платформе'],
     [ARTICLES, '📰 Статьи', 'Материалы для подготовки']].forEach(function (item) {
      var exists = Array.prototype.some.call(page.querySelectorAll('a[href]'), function (link) {
        return pathOf(link) === item[0];
      });
      if (exists) return;
      var row = document.createElement('div'); row.className = 'misc-row';
      var link = document.createElement('a'); link.href = item[0]; link.className = 'misc-link';
      var label = document.createElement('span'); label.className = 'misc-link-label'; label.textContent = item[1];
      var desc = document.createElement('span'); desc.className = 'misc-link-desc'; desc.textContent = item[2];
      link.appendChild(label); link.appendChild(desc); row.appendChild(link); group.appendChild(row);
    });
    if (group.children.length > 1) {
      var title = page.querySelector('h1');
      page.insertBefore(group, title ? title.nextSibling : page.firstChild);
    }
  }
  function showNotice() {
    if (Date.now() - firstVisit >= HOUR || read(DISMISS_KEY) === '1' ||
        document.getElementById('formyla-start-notice')) return;
    var notice = document.createElement('aside');
    notice.id = 'formyla-start-notice';
    notice.setAttribute('aria-label', 'Знакомство с платформой');
    notice.innerHTML = '<button type="button" class="formyla-start-close" aria-label="Закрыть уведомление">×</button>' +
      '<p role="status">Прочитайте раздел «С чего начать»</p>' +
      '<a href="/olympiad-start">Перейти →</a>';
    notice.querySelector('button').addEventListener('click', dismissNotice);
    notice.querySelector('a').addEventListener('click', function () { write(DISMISS_KEY, '1'); });
    document.body.appendChild(notice);
  }
  function init() {
    if (window.formylaMaterialsReady) return;
    window.formylaMaterialsReady = true;
    addMiscCards();
    if (!document.querySelector('.nav a[href="/misc"], .drawer-link[href="/misc"], .nav-item[href="/olympiad-start"]')) return;
    var saved = Number(read(FIRST_KEY)), now = Date.now();
    firstVisit = saved > 0 && saved <= now ? saved : now;
    if (firstVisit !== saved) write(FIRST_KEY, firstVisit);
    if (location.pathname.replace(/\/$/, '') === START) dismissNotice();
    updateNavigation();
    noticeTimer = setTimeout(showNotice, 1200);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) updateNavigation();
    });
    window.addEventListener('pageshow', updateNavigation);
    window.addEventListener('storage', function (event) {
      if (event.key === FIRST_KEY || event.key === DISMISS_KEY || event.key === null) updateNavigation();
    });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !event.defaultPrevented && document.getElementById('formyla-start-notice')) {
        dismissNotice();
      }
    });
  }
  var style = document.createElement('style');
  var navRoots = ['.nav ', '.drawer-link', '.bottom-nav-item', '.nav-item', '#pinnedNavItems '];
  var articleRules = [], startRules = [];
  navRoots.forEach(function (root) {
    var tag = root.slice(-1) === ' ' ? 'a' : '';
    ['', '/'].forEach(function (suffix) {
      articleRules.push(root + tag + '[href="' + ARTICLES + suffix + '"]');
      startRules.push('.formyla-start-expired ' + root + tag + '[href="' + START + suffix + '"]');
    });
  });
  style.textContent = articleRules.join(',') + ',[data-formyla-material="articles"]{display:none!important}' +
    startRules.join(',') + ',.formyla-start-expired [data-formyla-material="start"]{display:none!important}' +
    '#ft-onboard-arrow{display:none!important}' +
    '#formyla-start-notice{position:fixed;left:20px;bottom:calc(90px + env(safe-area-inset-bottom,0px));z-index:1100;width:min(360px,calc(100vw - 40px));box-sizing:border-box;padding:20px 42px 20px 20px;border:1px solid var(--border-mid,#475569);border-radius:16px;background:var(--surface-2,#1e293b);color:var(--text-main,#f1f5f9);box-shadow:0 12px 36px #0004;font:inherit}' +
    '#formyla-start-notice p{margin:0 0 12px;line-height:1.5}' +
    '#formyla-start-notice a{display:inline-block;padding:8px 14px;border-radius:8px;background:#6d28d9;color:#fff;text-decoration:none;font-weight:600}' +
    '#formyla-start-notice .formyla-start-close{position:absolute;right:4px;top:4px;width:36px;height:36px;border:0;background:transparent;color:inherit;cursor:pointer;font-size:24px}' +
    '#formyla-start-notice a:focus-visible,#formyla-start-notice button:focus-visible{outline:2px solid #a78bfa;outline-offset:3px}';
  document.head.appendChild(style);
  var initial = Number(read(FIRST_KEY));
  if (initial > 0 && Date.now() - initial >= HOUR) document.documentElement.classList.add('formyla-start-expired');
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
