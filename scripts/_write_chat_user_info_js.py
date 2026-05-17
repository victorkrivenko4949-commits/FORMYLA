"""Helper script to write static/js/chat_user_info.js.

Inline string-write approach in the tool layer was being mangled by the
streaming layer when the JS contained certain template/brace patterns,
so we generate the file from a Python source instead.
"""
from pathlib import Path

JS = r"""// CHAT_USER_INFO_V1 -- side-sheet "User info" for personal chat (chat.html).
// Renders a slide-in panel with profile data of the current peer.
(function initUserInfo() {
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      })[c];
    });
  }
  function fmtDate(iso) {
    if (!iso) return '\u2014';
    try {
      var d = new Date(iso);
      return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
    } catch (_) { return '\u2014'; }
  }
  function fmtRelative(iso) {
    if (!iso) return '\u2014';
    try {
      var d = new Date(iso);
      var diff = (Date.now() - d.getTime()) / 1000;
      if (diff < 60) return 'just now';
      if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
      if (diff < 86400) return Math.floor(diff / 3600) + ' h ago';
      if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' d ago';
      return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch (_) { return '\u2014'; }
  }

  function ensurePanel() {
    var panel = document.getElementById('uiPanel');
    if (panel) return panel;
    // Build it lazily if template did not include it (defensive).
    panel = document.createElement('div');
    panel.id = 'uiPanel';
    panel.className = 'ui-bg';
    panel.hidden = true;
    panel.innerHTML = ''
      + '<aside class="ui-panel" role="dialog" aria-label="User info">'
      +   '<div class="ui-head">'
      +     '<h3>Information</h3>'
      +     '<button type="button" class="ui-close" title="Close">&times;</button>'
      +   '</div>'
      +   '<div class="ui-body" id="uiBody">'
      +     '<div class="ui-loading">Loading\u2026</div>'
      +   '</div>'
      + '</aside>';
    panel.addEventListener('click', function (e) {
      if (e.target === panel) window.closeUserInfo();
    });
    panel.querySelector('.ui-close').addEventListener('click', window.closeUserInfo);
    document.body.appendChild(panel);
    return panel;
  }

  window.openUserInfo = async function openUserInfo(ev) {
    if (ev && ev.stopPropagation) ev.stopPropagation();
    var uid =
      (typeof currentFriendId !== 'undefined' && currentFriendId) ? currentFriendId :
      (typeof ACTIVE_FRIEND_ID !== 'undefined' ? ACTIVE_FRIEND_ID : null);
    if (!uid) return;
    var panel = ensurePanel();
    var body = document.getElementById('uiBody');
    panel.hidden = false;
    if (body) body.innerHTML = '<div class="ui-loading">\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430\u2026</div>';
    try {
      var r = await fetch('/api/users/' + uid + '/info');
      if (!r.ok) {
        if (body) body.innerHTML = '<div class="ui-loading">\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u0438\u0442\u044c \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u044e</div>';
        return;
      }
      var d = await r.json();
      var u = d.user || {};
      var avInner = u.avatar_url
        ? '<img src="' + esc(u.avatar_url) + '" alt="">'
        : esc((u.name || '?')[0].toUpperCase());
      var nickRow = u.nickname
        ? '<div class="ui-row"><span class="ico">@</span><span class="lbl">\u041d\u0438\u043a\u043d\u0435\u0439\u043c</span><span class="val">@' + esc(u.nickname) + '</span></div>'
        : '';
      var emailRow = u.email
        ? '<div class="ui-row"><span class="ico">\u2709\ufe0f</span><span class="lbl">Email</span><span class="val">' + esc(u.email) + '</span></div>'
        : '';
      var html = ''
        + '<div class="ui-hero">'
        +   '<div class="ui-hero-av">' + avInner + '</div>'
        +   '<div class="ui-hero-name">' + esc(u.name || '\u2014') + '</div>'
        +   '<div class="ui-hero-sub">\u0423\u0440\u043e\u0432\u0435\u043d\u044c ' + (u.level || 1) + ' \u00b7 ' + (u.xp || 0) + ' XP</div>'
        + '</div>'
        + '<div class="ui-section">'
        +   '<div class="ui-section-title">\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430</div>'
        +   '<div class="ui-stats">'
        +     '<div class="ui-stat"><div class="v">' + (u.problems_solved || 0) + '</div><div class="l">\u0420\u0435\u0448\u0435\u043d\u043e \u0437\u0430\u0434\u0430\u0447</div></div>'
        +     '<div class="ui-stat"><div class="v">' + (u.adaptive_tests_completed || 0) + '</div><div class="l">\u0410\u0434\u0430\u043f\u0442\u0438\u0432\u043d\u044b\u0445 \u0442\u0435\u0441\u0442\u043e\u0432</div></div>'
        +     '<div class="ui-stat"><div class="v">' + (u.mock_exams_passed || 0) + '</div><div class="l">\u041f\u0440\u043e\u0431\u043d\u0438\u043a\u043e\u0432 \u003e80%</div></div>'
        +     '<div class="ui-stat"><div class="v">' + (u.streak_days || 0) + '</div><div class="l">\u0414\u043d\u0435\u0439 \u043f\u043e\u0434\u0440\u044f\u0434</div></div>'
        +   '</div>'
        + '</div>'
        + '<div class="ui-section">'
        +   '<div class="ui-section-title">\u041e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435</div>'
        +   nickRow
        +   emailRow
        +   '<div class="ui-row"><span class="ico">\ud83d\udcc5</span><span class="lbl">\u0421 \u043d\u0430\u043c\u0438 \u0441</span><span class="val">' + fmtDate(u.created_at) + '</span></div>'
        +   '<div class="ui-row"><span class="ico">\ud83d\udd52</span><span class="lbl">\u0411\u044b\u043b \u0432 \u0441\u0435\u0442\u0438</span><span class="val">' + fmtRelative(u.last_login) + '</span></div>'
        +   '<div class="ui-row"><span class="ico">\ud83c\udfaf</span><span class="lbl">\u041c\u0430\u043a\u0441 \u0441\u043b\u043e\u0436\u043d\u043e\u0441\u0442\u044c</span><span class="val">' + (u.highest_difficulty_solved || 0) + '</span></div>'
        + '</div>'
        + '<div class="ui-section">'
        +   '<div class="ui-row action" data-act="profile"><span class="ico">\ud83d\udc64</span><span class="lbl">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u043b\u043d\u044b\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c</span><span class="val">\u203a</span></div>'
        + '</div>';
      body.innerHTML = html;
      var profBtn = body.querySelector('[data-act="profile"]');
      if (profBtn && u.profile_url) {
        profBtn.addEventListener('click', function () { window.location.href = u.profile_url; });
      }
    } catch (e) {
      console.error(e);
      if (body) body.innerHTML = '<div class="ui-loading">\u041e\u0448\u0438\u0431\u043a\u0430 \u0441\u043e\u0435\u0434\u0438\u043d\u0435\u043d\u0438\u044f</div>';
    }
  };

  window.closeUserInfo = function closeUserInfo() {
    var panel = document.getElementById('uiPanel');
    if (panel) panel.hidden = true;
  };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      var p = document.getElementById('uiPanel');
      if (p && !p.hidden) window.closeUserInfo();
    }
  });
})();
"""

target = Path('static/js/chat_user_info.js')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(JS, encoding='utf-8')
print('Wrote', target, len(JS), 'bytes')
