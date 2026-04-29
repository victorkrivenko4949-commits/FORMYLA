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
  document.querySelectorAll('.nav-item, .nav-menu a').forEach(function (a) {
    var href = a.getAttribute('href');
    if (href && href !== '#' && path === href) {
      a.classList.add('active');
      var parent = a.closest('.nav-dropdown');
      if (parent) {
        var parentToggle = parent.querySelector('.nav-toggle');
        if (parentToggle) parentToggle.classList.add('active');
      }
    }
  });

});
