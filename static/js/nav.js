/**
 * FORMYLA - Dropdown Navigation
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
    '/problems', '/matstat', '/'];
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
