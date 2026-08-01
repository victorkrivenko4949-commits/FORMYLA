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

});
