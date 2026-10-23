// CHAT_GROUPS_SIDEBAR_V2
// Renders group conversations in the chat sidebar list (/chat).
// Groups are saved on the server (POST /api/groups). The original
// sidebar template iterates only over friends, so created groups
// have to be injected client-side via this script.
//
// V2 changes:
//  - flat layout: group items are inserted directly into #convList
//    (no extra wrapper container), so they inherit existing
//    .chat-list-item CSS without needing extra rules
//  - inline-styled section headers ("Группы" / "Друзья") that don't
//    depend on any external CSS class being present
//  - explicit console logging so the user can verify behavior in
//    DevTools when something goes wrong
//  - retries fetch on transient failures and falls back gracefully
(function initGroupsSidebar(){
  'use strict';
  var TAG = '[groups-sidebar]';

  function log(){
    try {
      var args = Array.prototype.slice.call(arguments);
      args.unshift(TAG);
      console.log.apply(console, args);
    } catch(_){}
  }
  function warn(){
    try {
      var args = Array.prototype.slice.call(arguments);
      args.unshift(TAG);
      console.warn.apply(console, args);
    } catch(_){}
  }

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[c];
    });
  }

  var HEADER_STYLE = [
    'padding:10px 16px 6px',
    'font-size:11px',
    'font-weight:700',
    'letter-spacing:.08em',
    'text-transform:uppercase',
    'color:rgba(255,255,255,.45)',
    'user-select:none',
  ].join(';');

  function buildHeader(id, text){
    var h = document.createElement('div');
    h.id = id;
    h.className = 'chat-list-section-title';
    h.setAttribute('style', HEADER_STYLE);
    h.textContent = text;
    return h;
  }

  function buildGroupItem(g){
    var av = esc(g.avatar_emoji || '\ud83d\udc65');
    var preview = g.last_message
      ? esc(g.last_message)
      : '\u041d\u0435\u0442 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439';
    var el = document.createElement('div');
    el.className = 'chat-list-item chat-list-group';
    el.setAttribute('data-group-id', String(g.id));
    el.addEventListener('click', function(){
      window.location.href = '/groups/' + g.id;
    });
    el.innerHTML = ''
      + '<div class="chat-avatar chat-avatar-group" '
      +   'style="background:linear-gradient(135deg,#6c5ce7,#4aa8ff);'
      +   'display:flex;align-items:center;justify-content:center;'
      +   'width:42px;height:42px;border-radius:50%;font-size:20px;flex-shrink:0;">'
      +   av
      + '</div>'
      + '<div class="chat-list-meta">'
      +   '<div class="chat-list-name">' + esc(g.name || 'Group') + '</div>'
      +   '<div class="chat-list-preview">' + preview + '</div>'
      + '</div>';
    return el;
  }

  function clearOldGroupNodes(list){
    // Remove any previously injected nodes so we don't duplicate on refresh.
    var stale = list.querySelectorAll(
      '[data-groups-injected="1"], .chat-list-group'
    );
    for (var i = 0; i < stale.length; i++){
      stale[i].parentNode && stale[i].parentNode.removeChild(stale[i]);
    }
  }

  function render(groups){
    var list = document.getElementById('convList');
    if (!list){
      warn('#convList not found in DOM');
      return;
    }
    clearOldGroupNodes(list);

    if (!groups.length){
      log('no groups to render');
      return;
    }

    var frag = document.createDocumentFragment();
    var groupsHeader = buildHeader('groupsHeading', '\u0413\u0440\u0443\u043f\u043f\u044b');
    groupsHeader.setAttribute('data-groups-injected', '1');
    frag.appendChild(groupsHeader);
    for (var i = 0; i < groups.length; i++){
      frag.appendChild(buildGroupItem(groups[i]));
    }

    // Insert all group nodes at the very top of the list.
    list.insertBefore(frag, list.firstChild);

    // Add a "Друзья" heading before the first non-group item, if any.
    var items = list.querySelectorAll('.chat-list-item');
    var firstFriend = null;
    for (var j = 0; j < items.length; j++){
      if (!items[j].classList.contains('chat-list-group')){
        firstFriend = items[j];
        break;
      }
    }
    if (firstFriend){
      var existing = document.getElementById('friendsHeading');
      if (existing && existing.parentNode){
        existing.parentNode.removeChild(existing);
      }
      var friendsHeader = buildHeader('friendsHeading', '\u0414\u0440\u0443\u0437\u044c\u044f');
      friendsHeader.setAttribute('data-groups-injected', '1');
      list.insertBefore(friendsHeader, firstFriend);
    }

    // Bump the count in the sidebar header to include groups.
    var cnt = document.getElementById('convCount');
    if (cnt){
      var friendsItems = list.querySelectorAll(
        '.chat-list-item:not(.chat-list-group)'
      ).length;
      cnt.textContent = String(friendsItems + groups.length);
    }
    log('rendered', groups.length, 'group(s)');
  }

  async function loadGroups(){
    try {
      log('fetching /api/groups …');
      var r = await fetch('/api/groups', {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' },
      });
      if (!r.ok){
        warn('GET /api/groups failed with status', r.status);
        return;
      }
      var d = await r.json();
      var groups = (d && d.groups) || [];
      log('received', groups.length, 'group(s):', groups);
      render(groups);
    } catch(e){
      warn('error while loading groups:', e);
    }
  }

  function start(){
    loadGroups();
    // Refresh periodically together with the rest of the sidebar.
    setInterval(loadGroups, 15000);
    // Refresh when the tab regains focus.
    window.addEventListener('focus', loadGroups);
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  // Expose for manual debugging from the console.
  window.__reloadGroupsSidebar = loadGroups;
})();
