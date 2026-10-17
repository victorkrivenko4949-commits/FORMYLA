/* ADMIN_NOTICES_V1 — показывает уведомление от админа один раз на пользователя.
   Сервер: GET /api/admin-notices/pending, POST /api/admin-notices/seen {id}. */
(function () {
  if (window.__ftAdminNoticesInit) return;
  window.__ftAdminNoticesInit = true;

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function markSeen(id) {
    try {
      return fetch('/api/admin-notices/seen', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id })
      });
    } catch (e) { return Promise.resolve(); }
  }

  function show(n) {
    if (document.getElementById('ft-admin-notice-overlay')) return;
    var ov = document.createElement('div');
    ov.id = 'ft-admin-notice-overlay';
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-modal', 'true');
    ov.style.cssText = 'position:fixed;inset:0;z-index:30500;background:rgba(2,6,23,.72);' +
      'backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;';
    var link = '';
    if (n.link_url) {
      link = '<a href="' + esc(n.link_url) + '" id="ft-admin-notice-link" style="display:inline-block;' +
        'padding:11px 18px;border-radius:10px;font-weight:700;text-decoration:none;' +
        'background:linear-gradient(135deg,#38bdf8,#818cf8);color:#0b1020;">' +
        esc(n.link_text || 'Открыть') + '</a>';
    }
    ov.innerHTML =
      '<div style="width:100%;max-width:520px;background:var(--card,#141a2e);border:1px solid rgba(244,185,66,.45);' +
      'border-radius:18px;padding:22px 22px 18px;box-shadow:0 20px 60px rgba(0,0,0,.5);color:var(--text,#e2e8f0);">' +
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">' +
          '<span style="font-size:22px;">🔔</span>' +
          '<h3 style="margin:0;font-size:19px;line-height:1.25;">' + esc(n.title) + '</h3>' +
        '</div>' +
        '<div style="white-space:pre-wrap;line-height:1.5;font-size:15px;color:var(--text,#e2e8f0);margin:0 0 18px;">' +
          esc(n.body) + '</div>' +
        '<div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end;">' + link +
          '<button type="button" id="ft-admin-notice-ok" style="padding:11px 18px;border:1px solid rgba(255,255,255,.14);' +
          'border-radius:10px;background:rgba(255,255,255,.06);color:#e2e8f0;font-weight:700;cursor:pointer;">Понятно</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(ov);
    function close() {
      markSeen(n.id).catch(function(){}).then(function () {
        if (ov.parentNode) ov.parentNode.removeChild(ov);
      });
    }
    var ok = document.getElementById('ft-admin-notice-ok');
    if (ok) ok.addEventListener('click', close);
    var lk = document.getElementById('ft-admin-notice-link');
    if (lk) lk.addEventListener('click', function () { markSeen(n.id); });
  }

  function run() {
    fetch('/api/admin-notices/pending', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.pending && d.notice) show(d.notice); })
      .catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(run, 1200); });
  } else {
    setTimeout(run, 1200);
  }
})();
