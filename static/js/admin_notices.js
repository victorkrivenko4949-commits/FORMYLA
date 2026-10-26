/* ADMIN_NOTICES_V2 — простая карточка-уведомление в правом верхнем углу, один раз на пользователя.
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

  function injectCss() {
    if (document.getElementById('ft-notice-css')) return;
    var st = document.createElement('style');
    st.id = 'ft-notice-css';
    st.textContent =
      '#ft-notice{position:fixed;top:84px;right:18px;z-index:30500;width:340px;max-width:calc(100vw - 24px);' +
      'background:var(--card,#141a2e);color:var(--text,#e2e8f0);border:1px solid rgba(255,255,255,.12);border-radius:14px;' +
      'box-shadow:0 14px 40px rgba(0,0,0,.45);padding:14px 14px 12px;font-size:14px;line-height:1.45;' +
      'transform:translateY(-8px);opacity:0;transition:transform .25s ease,opacity .25s ease}' +
      '#ft-notice.is-in{transform:none;opacity:1}' +
      '#ft-notice .ft-n-head{display:flex;align-items:center;gap:10px;margin-bottom:6px}' +
      '#ft-notice .ft-n-ico{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:17px;flex:none}' +
      '#ft-notice .ft-n-ico.support{background:rgba(168,85,247,.18)}' +
      '#ft-notice .ft-n-ico.curator{background:rgba(76,125,255,.18)}' +
      '#ft-notice .ft-n-from{font-weight:700;font-size:13px}' +
      '#ft-notice .ft-n-sub{font-size:11px;color:rgba(255,255,255,.45)}' +
      '#ft-notice .ft-n-x{margin-left:auto;background:none;border:0;color:rgba(255,255,255,.45);font-size:18px;line-height:1;cursor:pointer;padding:2px 4px}' +
      '#ft-notice .ft-n-body{white-space:pre-wrap;color:var(--text,#e2e8f0);margin:2px 0 10px}' +
      '#ft-notice .ft-n-link{display:block;width:100%;padding:11px 0;margin:2px 0 6px;border:0;border-radius:10px;font-weight:800;cursor:pointer;text-decoration:none;text-align:center;font-size:14px;background:linear-gradient(135deg,#38bdf8,#8b5cf6);color:#fff}' +
      '#ft-notice .ft-n-link:hover{filter:brightness(1.1)}' +
      '#ft-notice.ft-n-premium{border-color:rgba(139,92,246,.7);box-shadow:0 14px 46px rgba(139,92,246,.35)}' +
      '#ft-notice .ft-n-ok{display:block;width:100%;padding:9px 0;border:0;border-radius:9px;font-weight:700;cursor:pointer;' +
      'background:rgba(255,255,255,.08);color:#e2e8f0}' +
      '#ft-notice .ft-n-ok:hover{background:rgba(255,255,255,.14)}' +
      '@media (max-width:640px){#ft-notice{top:auto;bottom:76px;left:12px;right:12px;width:auto}}';
    document.head.appendChild(st);
  }

  function show(n) {
    if (document.getElementById('ft-notice')) return;
    injectCss();
    var isCurator = n.sender === 'curator';
    // NOTICE_PREMIUM_V1: анонс со словом «Premium» получает премиальный акцент
    var isPremium = /premium/i.test(String(n.body || ''));
    var box = document.createElement('div');
    box.id = 'ft-notice';
    if (isPremium) box.className = 'ft-n-premium';
    box.setAttribute('role', 'status');
    var linkHtml = '';
    if (n.link_url) {
      linkHtml = '<a class="ft-n-link" href="' + esc(n.link_url) + '">' +
                esc(n.link_text || 'Открыть') + '</a>';
    }
    box.innerHTML =
      '<div class="ft-n-head">' +
        '<div class="ft-n-ico ' + (isCurator ? 'curator' : 'support') + '">' + (isCurator ? '\uD83C\uDF93' : '\uD83D\uDCAC') + '</div>' +
        '<div><div class="ft-n-from">' + esc(n.sender_label || (isCurator ? 'Куратор' : 'Поддержка')) + '</div>' +
        '<div class="ft-n-sub">FORMYLA.net</div></div>' +
        '<button type="button" class="ft-n-x" aria-label="Закрыть">×</button>' +
      '</div>' +
      '<div class="ft-n-body">' + esc(n.body) + '</div>' +
      linkHtml +
      '<button type="button" class="ft-n-ok">Ок</button>';
    document.body.appendChild(box);
    requestAnimationFrame(function () { box.classList.add('is-in'); });
    // Клик по кнопке-ссылке тоже отмечает уведомление увиденным
    var linkEl = box.querySelector('.ft-n-link');
    if (linkEl) linkEl.addEventListener('click', function () { markSeen(n.id); });
    function close() {
      box.classList.remove('is-in');
      markSeen(n.id).catch(function () {}).then(function () {
        setTimeout(function () { if (box.parentNode) box.parentNode.removeChild(box); }, 250);
      });
    }
    box.querySelector('.ft-n-ok').addEventListener('click', close);
    box.querySelector('.ft-n-x').addEventListener('click', close);
  }

  function run() {
    fetch('/api/admin-notices/pending', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d && d.pending && d.notice) show(d.notice); })
      .catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(run, 1000); });
  } else {
    setTimeout(run, 1000);
  }
})();
