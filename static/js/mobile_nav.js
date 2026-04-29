/**
 * FORMYLA — Mobile App-Like Navigation
 * Drawer menu + Bottom navigation bar
 */

(function () {
  'use strict';

  /* ── DRAWER ── */

  function openDrawer() {
    var drawer = document.getElementById('mobileDrawer');
    var overlay = document.getElementById('drawerOverlay');
    if (!drawer || !overlay) return;

    drawer.classList.add('open');
    overlay.classList.add('open');
    document.body.classList.add('drawer-open');

    // Update burger aria
    var burger = document.querySelector('.nav-burger');
    if (burger) {
      burger.classList.add('active');
      burger.setAttribute('aria-expanded', 'true');
    }
  }

  function closeDrawer() {
    var drawer = document.getElementById('mobileDrawer');
    var overlay = document.getElementById('drawerOverlay');
    if (!drawer || !overlay) return;

    drawer.classList.remove('open');
    overlay.classList.remove('open');
    document.body.classList.remove('drawer-open');

    // Update burger aria
    var burger = document.querySelector('.nav-burger');
    if (burger) {
      burger.classList.remove('active');
      burger.setAttribute('aria-expanded', 'false');
    }
  }

  function toggleDrawer() {
    var drawer = document.getElementById('mobileDrawer');
    if (!drawer) return;

    if (drawer.classList.contains('open')) {
      closeDrawer();
    } else {
      openDrawer();
    }
  }

  /* ── BOTTOM NAV ACTIVE STATE ── */

  function highlightBottomNav() {
    var path = window.location.pathname;
    var items = document.querySelectorAll('.bottom-nav-item[data-path]');

    items.forEach(function (item) {
      var paths = item.getAttribute('data-path').split(',');
      var isActive = paths.some(function (p) {
        p = p.trim();
        if (p.endsWith('*')) {
          return path.indexOf(p.slice(0, -1)) === 0;
        }
        return path === p;
      });

      if (isActive) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });
  }

  /* ── DRAWER ACTIVE STATE ── */

  function highlightDrawerLinks() {
    var path = window.location.pathname;
    document.querySelectorAll('.drawer-link[href]').forEach(function (link) {
      var href = link.getAttribute('href');
      if (href && href !== '#' && path === href) {
        link.classList.add('active');
      }
    });
  }

  /* ── SWIPE GESTURE (open drawer by swiping right from left edge) ── */

  var touchStartX = 0;
  var touchStartY = 0;
  var touchStartTime = 0;
  var isSwiping = false;

  function handleTouchStart(e) {
    var touch = e.touches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
    touchStartTime = Date.now();
    // Only track swipe if starting from left edge (within 30px)
    isSwiping = touchStartX < 30;
  }

  function handleTouchEnd(e) {
    if (!isSwiping) return;
    isSwiping = false;

    var touch = e.changedTouches[0];
    var deltaX = touch.clientX - touchStartX;
    var deltaY = Math.abs(touch.clientY - touchStartY);
    var elapsed = Date.now() - touchStartTime;

    // Swipe right: deltaX > 60px, mostly horizontal, within 400ms
    if (deltaX > 60 && deltaY < 100 && elapsed < 400) {
      var drawer = document.getElementById('mobileDrawer');
      if (drawer && !drawer.classList.contains('open')) {
        openDrawer();
      }
    }
  }

  /* ── SWIPE TO CLOSE DRAWER ── */

  var drawerTouchStartX = 0;

  function handleDrawerTouchStart(e) {
    drawerTouchStartX = e.touches[0].clientX;
  }

  function handleDrawerTouchEnd(e) {
    var deltaX = e.changedTouches[0].clientX - drawerTouchStartX;
    // Swipe left to close
    if (deltaX < -60) {
      closeDrawer();
    }
  }

  /* ── INIT ── */

  document.addEventListener('DOMContentLoaded', function () {
    // Highlight active states
    highlightBottomNav();
    highlightDrawerLinks();

    // Close drawer on link click
    document.querySelectorAll('.drawer-link').forEach(function (link) {
      link.addEventListener('click', function () {
        // Small delay for visual feedback
        setTimeout(closeDrawer, 150);
      });
    });

    // Close drawer on overlay click
    var overlay = document.getElementById('drawerOverlay');
    if (overlay) {
      overlay.addEventListener('click', closeDrawer);
    }

    // Close drawer on Escape
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeDrawer();
    });

    // Swipe gestures (only on mobile)
    if ('ontouchstart' in window || navigator.maxTouchPoints > 0) {
      document.addEventListener('touchstart', handleTouchStart, { passive: true });
      document.addEventListener('touchend', handleTouchEnd, { passive: true });

      var drawer = document.getElementById('mobileDrawer');
      if (drawer) {
        drawer.addEventListener('touchstart', handleDrawerTouchStart, { passive: true });
        drawer.addEventListener('touchend', handleDrawerTouchEnd, { passive: true });
      }
    }
  });

  /* ── EXPORTS ── */
  window.toggleDrawer = toggleDrawer;
  window.openDrawer = openDrawer;
  window.closeDrawer = closeDrawer;

  // Legacy compat: old burger button calls toggleMobileNav
  window.toggleMobileNav = toggleDrawer;
  window.closeMobileNav = closeDrawer;

})();
