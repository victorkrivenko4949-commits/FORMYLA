# -*- coding: utf-8 -*-
"""Build base64 payload for chat.html WhatsApp-style features.

Generates _chat_html_payload.b64 in this directory.
Run once before _patch_chat_html.py."""
import os, base64, json

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_chat_html_payload.b64")

# ------------- New composer block (replaces messages-div + composer) -------------
COMPOSER_HTML = '''
      <!-- Reply / Edit preview bar (WA-style) -->
      <div id="chatActionBar" class="chat-action-bar" hidden>
        <div class="cab-icon" id="cabIcon">&#x21A9;</div>
        <div class="cab-body">
          <div class="cab-title" id="cabTitle">Ответ</div>
          <div class="cab-text" id="cabText">&mdash;</div>
        </div>
        <button class="cab-close" id="cabClose" type="button" title="Отмена"
                onclick="cancelAction()">&times;</button>
      </div>
      <div class="chat-composer">
        <button class="chat-btn share" title="Поделиться задачей" onclick="openTaskPicker()">&#128206;</button>
        <textarea id="chatText" placeholder="Напишите сообщение… (Enter — отправить, Shift+Enter — перенос)"
                  onkeydown="onChatKey(event)"></textarea>
        <button class="chat-btn send" id="chatSendBtn" onclick="sendMessage()" title="Отправить">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg>
        </button>
      </div>

      <!-- Message context menu (WA-style) -->
      <div id="msgCtxMenu" class="msg-ctx-menu" hidden>
        <button data-act="reply"  type="button"><span>&#x21A9;</span>Ответить</button>
        <button data-act="copy"   type="button"><span>&#128203;</span>Копировать</button>
        <button data-act="forward" type="button"><span>&#10140;</span>Переслать</button>
        <button data-act="edit"   type="button" data-mine-only="1"><span>&#9998;</span>Изменить</button>
        <button data-act="delete" type="button" data-mine-only="1" class="danger"><span>&#128465;</span>Удалить</button>
      </div>

      <!-- Forward picker -->
      <div id="fwdModal" class="fwd-modal-overlay" hidden onclick="if(event.target===this) closeForward()">
        <div class="fwd-modal">
          <div class="fwd-head">
            <h3>&#10140; Переслать</h3>
            <button type="button" onclick="closeForward()" class="fwd-close">&times;</button>
          </div>
          <input id="fwdSearch" type="text" placeholder="Поиск друга..." oninput="renderFwdList()">
          <div id="fwdList" class="fwd-list"></div>
          <div class="fwd-foot">
            <button type="button" onclick="closeForward()" class="fwd-btn-cancel">Отмена</button>
            <button type="button" id="fwdSend" onclick="doForward()" class="fwd-btn-send" disabled>Переслать</button>
          </div>
        </div>
      </div>
'''

# ------------- New renderMessages + helper JS -------------
# All braces inline; no template literals confusion.
NEW_JS = r'''function renderMessages(msgs){  /* CHAT_WA_FE_V1 */
  const box = document.getElementById('chatMessages');
  if (!box) return;
  box.innerHTML = '';
  window._lastMsgs = msgs;
  for (const m of msgs){
    const b = document.createElement('div');
    b.className = 'chat-bubble ' + (m.mine ? 'mine' : 'theirs') +
                  (m.deleted ? ' deleted' : '') +
                  (m.forwarded ? ' forwarded' : '');
    b.dataset.mid = m.id;
    b.dataset.mine = m.mine ? '1' : '0';
    b.dataset.kind = m.kind || 'text';

    // Reply preview (if this message is a reply to another)
    let replyHtml = '';
    if (m.reply && !m.deleted){
      const rb = m.reply.body || '';
      const rTxt = m.reply.deleted ? '<i>Сообщение удалено</i>' :
                   (m.reply.kind === 'task_share' ? '&#128206; Задача' : escHtml(rb).slice(0, 140));
      replyHtml = '<div class="bubble-reply" onclick="scrollToMsg(' + m.reply.id + ')">' +
                  '<div class="br-bar"></div>' +
                  '<div class="br-body">' + rTxt + '</div></div>';
    }

    let forwardedTag = m.forwarded ? '<div class="bubble-forwarded">&#10140; Переслано</div>' : '';

    if (m.deleted){
      b.innerHTML = forwardedTag + replyHtml +
                    '<i class="bubble-deleted">Сообщение удалено</i>' +
                    '<span class="ts">' + fmtTime(m.created_at) + '</span>';
    } else if (m.kind === 'task_share' && m.task){
      const t = m.task;
      let metaParts = [];
      if (t.source) metaParts.push(t.source);
      if (t.topic) metaParts.push(t.topic);
      if (t.grade) metaParts.push(t.grade + ' класс');
      if (t.difficulty) metaParts.push('L' + t.difficulty);
      const card =
        '<div class="chat-task-card">' +
          '<div class="title">&#128206; Задача' + (t.id ? ' #' + t.id : '') + '</div>' +
          (metaParts.length ? '<div class="meta">' + escHtml(metaParts.join(' \u00B7 ')) + '</div>' : '') +
          (t.preview ? '<div class="preview">' + escHtml(t.preview) + '</div>' : '') +
          (t.url ? '<a class="open-btn" href="' + escHtml(t.url) + '" target="_blank" rel="noopener">Открыть &rarr;</a>' : '') +
        '</div>';
      const editedTag = m.edited ? ' <span class="edited-tag" title="Изменено">(изм.)</span>' : '';
      b.innerHTML = forwardedTag + replyHtml +
                    (m.body ? escHtml(m.body) + '<br>' : '') +
                    card +
                    '<span class="ts">' + fmtTime(m.created_at) + editedTag + '</span>';
    } else {
      const editedTag = m.edited ? ' <span class="edited-tag" title="Изменено">(изм.)</span>' : '';
      b.innerHTML = forwardedTag + replyHtml +
                    escHtml(m.body || '') +
                    '<span class="ts">' + fmtTime(m.created_at) + editedTag + '</span>';
    }
    attachBubbleMenu(b, m);
    box.appendChild(b);
  }
  box.scrollTop = box.scrollHeight;
}

/* ===== WhatsApp-style context menu + actions ===== */
let _ctxMsg = null;       // currently-selected message
let _replyToId = null;    // id of message being replied to
let _editingId = null;    // id of message being edited
let _fwdMsgId = null;     // id of message being forwarded
let _fwdSelected = new Set();
let _fwdFriends = [];

function attachBubbleMenu(bubble, m){
  let pressTimer = null;
  bubble.addEventListener('contextmenu', function(e){
    e.preventDefault();
    showCtxMenu(e.clientX, e.clientY, m);
  });
  bubble.addEventListener('touchstart', function(e){
    pressTimer = setTimeout(() => {
      const t = e.touches[0];
      showCtxMenu(t.clientX, t.clientY, m);
    }, 500);
  }, {passive:true});
  bubble.addEventListener('touchend', () => { if (pressTimer) clearTimeout(pressTimer); });
  bubble.addEventListener('touchmove', () => { if (pressTimer) clearTimeout(pressTimer); });
  // Double-click on mobile is awkward; offer also a small "..." button on desktop hover.
  bubble.addEventListener('dblclick', function(e){
    if (m.deleted) return;
    e.preventDefault();
    startReply(m);
  });
}

function showCtxMenu(x, y, m){
  if (m.deleted) return;
  _ctxMsg = m;
  const menu = document.getElementById('msgCtxMenu');
  if (!menu) return;
  // Show/hide mine-only items
  menu.querySelectorAll('[data-mine-only]').forEach(btn => {
    btn.style.display = m.mine ? '' : 'none';
  });
  // Edit only for own text messages (kind === text)
  const editBtn = menu.querySelector('[data-act=edit]');
  if (editBtn) editBtn.style.display = (m.mine && m.kind === 'text') ? '' : 'none';

  menu.hidden = false;
  // Position with viewport clamp
  const vw = window.innerWidth, vh = window.innerHeight;
  menu.style.left = Math.min(x, vw - 220) + 'px';
  menu.style.top  = Math.min(y, vh - 260) + 'px';
}

function hideCtxMenu(){
  const menu = document.getElementById('msgCtxMenu');
  if (menu) menu.hidden = true;
  _ctxMsg = null;
}

document.addEventListener('click', function(e){
  const menu = document.getElementById('msgCtxMenu');
  if (!menu || menu.hidden) return;
  const btn = e.target.closest('#msgCtxMenu [data-act]');
  if (btn){
    const act = btn.dataset.act;
    const m = _ctxMsg;
    hideCtxMenu();
    if (!m) return;
    if (act === 'reply')   startReply(m);
    else if (act === 'copy')    copyMessage(m);
    else if (act === 'forward') openForward(m);
    else if (act === 'edit')    startEdit(m);
    else if (act === 'delete')  deleteMessage(m);
    return;
  }
  // Click outside menu — close
  if (!e.target.closest('#msgCtxMenu')) hideCtxMenu();
});

function startReply(m){
  _editingId = null;
  _replyToId = m.id;
  const bar = document.getElementById('chatActionBar');
  document.getElementById('cabTitle').textContent = 'Ответ';
  document.getElementById('cabIcon').innerHTML = '&#x21A9;';
  const preview = m.kind === 'task_share'
    ? '\u{1F4CE} Задача' + (m.task && m.task.id ? ' #' + m.task.id : '')
    : (m.body || '').slice(0, 140);
  document.getElementById('cabText').textContent = preview;
  bar.hidden = false;
  document.getElementById('chatText').focus();
}

function startEdit(m){
  if (m.kind !== 'text' || !m.mine) return;
  _replyToId = null;
  _editingId = m.id;
  const bar = document.getElementById('chatActionBar');
  document.getElementById('cabTitle').textContent = 'Редактирование';
  document.getElementById('cabIcon').innerHTML = '&#9998;';
  document.getElementById('cabText').textContent = (m.body || '').slice(0, 140);
  bar.hidden = false;
  const ta = document.getElementById('chatText');
  ta.value = m.body || '';
  ta.focus();
}

function cancelAction(){
  _replyToId = null;
  _editingId = null;
  document.getElementById('chatActionBar').hidden = true;
  document.getElementById('chatText').value = '';
}

async function copyMessage(m){
  let txt = m.body || '';
  if (m.kind === 'task_share' && m.task){
    const t = m.task;
    txt = (m.body ? m.body + '\n\n' : '') +
          'Задача' + (t.id ? ' #' + t.id : '') +
          (t.preview ? '\n' + t.preview : '') +
          (t.url ? '\n' + t.url : '');
  }
  try {
    if (navigator.clipboard && navigator.clipboard.writeText){
      await navigator.clipboard.writeText(txt);
      flashToast('Скопировано');
    } else {
      const ta = document.createElement('textarea');
      ta.value = txt; document.body.appendChild(ta);
      ta.select(); document.execCommand('copy'); ta.remove();
      flashToast('Скопировано');
    }
  } catch(e){ console.error(e); flashToast('Не удалось скопировать'); }
}

async function deleteMessage(m){
  if (!m.mine) return;
  if (!confirm('Удалить сообщение?')) return;
  try {
    const r = await fetch('/api/chat/message/' + m.id + '/delete', { method:'POST' });
    const d = await r.json().catch(() => ({}));
    if (!r.ok){ alert(d.error || 'Не удалось удалить'); return; }
    await loadMessages();
    loadConversations();
  } catch(e){ console.error(e); alert('Ошибка соединения'); }
}

function scrollToMsg(mid){
  const el = document.querySelector('.chat-bubble[data-mid="' + mid + '"]');
  if (!el) return;
  el.scrollIntoView({behavior:'smooth', block:'center'});
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1400);
}

function flashToast(text){
  let t = document.getElementById('_chatToast');
  if (!t){
    t = document.createElement('div');
    t.id = '_chatToast';
    t.className = 'chat-toast';
    document.body.appendChild(t);
  }
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 1600);
}

/* ===== Forward modal ===== */
async function openForward(m){
  _fwdMsgId = m.id;
  _fwdSelected = new Set();
  document.getElementById('fwdSearch').value = '';
  document.getElementById('fwdSend').disabled = true;
  document.getElementById('fwdModal').hidden = false;
  try {
    const r = await fetch('/api/chat/conversations');
    const data = await r.json().catch(() => ({}));
    _fwdFriends = (data.conversations || []).map(c => c.friend);
  } catch(e){ console.error(e); _fwdFriends = []; }
  renderFwdList{