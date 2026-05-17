"""Write static/js/chat_groups_sidebar.js (renders groups in the chat sidebar).

The JS body is stored as a single raw triple-quoted string and then
written to disk so the streaming layer does not have to deal with the
brace patterns inline in the tool call.
"""
from pathlib import Path

JS = r"""// CHAT_GROUPS_SIDEBAR_V1
// Renders group conversations in the chat sidebar list (/chat).
// Groups are saved on the server (POST /api/groups) but the original
// sidebar template only iterated over friends, so created groups
// stayed invisible.  This script fetches /api/groups and prepends a
// "Groups" section to the conversation list.
(function initGroupsSidebar(){
  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[c];
    });
  }

  function buildItem(g){
    var av = esc(g.avatar_emoji || '\ud83d\udc65');
    var preview = g.last_message ? esc(g.last_message) : '\u041d\u0435\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439';
    var el = document.createElement('div');
    el.className = 'chat-list-item chat-list-group';
    el.setAttribute('data-group-id', String(g.id));
    el.addEventListener('click', function(){ window.location.href = '/groups/' + g.id; });
    el.innerHTML = ''
      + '<div class="chat-avatar chat-avatar-group">' + av + '</div>'
      + '<div class="chat-list-meta">'
      +   '<div class="chat-list-name">' + esc(g.name || 'Group') + '</div>'
      +   '<div class="chat-list-preview">' + preview + '</div>'
      + '</div>';
    return el;
  }

  function ensureGroupSection(){
    var list = document.getElementById('convList');
    if (!list) return null;
    var sec = document.getElementById('groupsSection');
    if (sec) return sec;
    sec = document.createElement('div');
    sec.id = 'groupsSection';
    sec.className = 'chat-list-section';
    sec.innerHTML = '<div class="chat-list-section-title">\u0413\u0440\u0443\u043f\u043f\u044b</div>'
                  + '<div class="chat-list-section-body" id="groupsSectionBody"></div>';
    // Insert at the top of the conv list
    list.insertBefore(sec, list.firstChild);
    return sec;
  }

  function ensureFriendsHeading(){
    var list = document.getElementById('convList');
    if (!list) return;
    if (document.getElementById('friendsHeading')) return;
    // Find the first plain friend item (one without data-group-id).
    var items = list.querySelectorAll('.chat-list-item');
    var firstFriend = null;
    for (var i = 0; i < items.length; i++){
      if (!items[i].classList.contains('chat-list-group')){
        firstFriend = items[i];
        break;
      }
    }
    if (!firstFriend) return;
    var h = document.createElement('div');
    h.id = 'friendsHeading';
    h.className = 'chat-list-section-title';
    h.textContent = '\u0414\u0440\u0443\u0437\u044c\u044f';
    list.insertBefore(h, firstFriend);
  }

  async function loadGroups(){
    try{
      var r = await fetch('/api/groups');
      if (!r.ok) return;
      var d = await r.json();
      var groups = (d && d.groups) || [];
      var sec = ensureGroupSection();
      if (!sec) return;
      var body = document.getElementById('groupsSectionBody');
      if (!body) return;
      // Remove "no groups" placeholder if any
      body.innerHTML = '';
      if (!groups.length){
        sec.hidden = true;
        return;
      }
      sec.hidden = false;
      for (var i = 0; i < groups.length; i++){
        body.appendChild(buildItem(groups[i]));
      }
      ensureFriendsHeading();
      // Bump the count in the sidebar header to include groups.
      var cnt = document.getElementById('convCount');
      if (cnt){
        var friendsItems = document.querySelectorAll('#convList .chat-list-item:not(.chat-list-group)').length;
        cnt.textContent = String(friendsItems + groups.length);
      }
    }catch(e){ console.error('[groups-sidebar]', e); }
  }

  function start(){
    loadGroups();
    // Refresh periodically together with the rest of the sidebar.
    setInterval(loadGroups, 15000);
  }
  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
"""

target = Path('static/js/chat_groups_sidebar.js')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(JS, encoding='utf-8')
print('Wrote', target, len(JS), 'bytes')
