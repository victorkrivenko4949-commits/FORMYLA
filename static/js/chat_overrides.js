/* FORMYLA — static/js/chat_overrides.js (CHAT_DOCS_V1, 15.10.2026)
 * Подключается автоматически на страницах чата (routes/chat_attachments.py).
 *  - убирает кнопку «Поделиться задачей» и её модалку;
 *  - кнопка вложения → 📎, принимает документы;
 *  - загрузка через /upload-file: фото до 20 МБ, документы, фикс фото без расширения;
 *  - тексты подсказок.
 * Размер контекстного меню уменьшает chat_overrides.css. */
(function () {
  'use strict';

  var ACCEPT = 'image/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.rtf,.odt,.ods,.odp,.csv,.zip,.rar,.7z';
  var DOC_RE = /\.(pdf|docx?|xlsx?|pptx?|txt|rtf|odt|ods|odp|csv|zip|rar|7z)$/i;
  var IMG_RE = /\.(jpe?g|png|webp|gif|bmp)$/i;
  var VID_RE = /\.(mp4|webm|mov|m4v|ogg)$/i;
  var MAX_FILE = 20 * 1024 * 1024;
  var MAX_VIDEO = 50 * 1024 * 1024;

  function classify(f) {
    var name = f.name || '', type = f.type || '';
    if (type.indexOf('video/') === 0 || VID_RE.test(name)) return 'video';
    if (type.indexOf('image/') === 0 || IMG_RE.test(name)) return 'image';
    if (type === 'application/pdf' || DOC_RE.test(name)) return 'doc';
    return null;
  }

  // У фото из буфера обмена / некоторых галерей нет расширения → сервер отвечал 400.
  function uploadName(f) {
    var n = f.name || '';
    if (/\.[a-z0-9]{2,5}$/i.test(n)) return n;
    var sub = ((f.type || '').split('/')[1] || 'png').replace('jpeg', 'jpg');
    return 'photo_' + Date.now() + '.' + sub;
  }

  async function doUpload(url, f) {
    var kind = classify(f);
    if (!kind) {
      alert('Поддерживаются картинки, видео и документы (PDF, Word, Excel, PowerPoint, TXT, ZIP)');
      return null;
    }
    var max = kind === 'video' ? MAX_VIDEO : MAX_FILE;
    if (f.size > max) { alert('Файл больше ' + (max / (1024 * 1024)) + ' МБ'); return null; }
    var fd = new FormData();
    fd.append('file', f, uploadName(f));
    try {
      var r = await fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' });
      var d = await r.json().catch(function () { return {}; });
      if (!r.ok || !d.attachment) { alert(d.error || ('Ошибка загрузки (' + r.status + ')')); return null; }
      return d.attachment;
    } catch (e) {
      console.error(e);
      alert('Ошибка соединения при загрузке файла');
      return null;
    }
  }

  function show(el) { if (el) { el.hidden = false; el.removeAttribute('hidden'); el.style.display = ''; } }
  function hide(el) { if (el) { el.hidden = true; } }

  /* ───── Личный чат ───── */
  if (document.getElementById('chatFileInput')) {
    document.querySelectorAll('.chat-composer .chat-btn.share').forEach(function (b) {
      var oc = b.getAttribute('onclick') || '';
      if (oc.indexOf('openTaskPicker') >= 0) { b.remove(); return; }
      if (oc.indexOf('chatFileInput') >= 0) {
        b.textContent = '📎';
        b.title = 'Прикрепить файл (фото, видео, документы)';
      }
    });
    var inp = document.getElementById('chatFileInput');
    inp.setAttribute('accept', ACCEPT);
    var tp = document.getElementById('taskPickerModal');
    if (tp) tp.remove();
    var hint = document.querySelector('#chatDropOverlay div:last-child');
    if (hint) hint.textContent = 'Фото и документы до 20 МБ, видео до 50 МБ';

    window.uploadAttachmentFile = async function (f) {
      if (!f || typeof currentFriendId === 'undefined' || !currentFriendId) return false;
      var bar = document.getElementById('attachPreviewBar');
      var nameEl = document.getElementById('attachPreviewName');
      if (nameEl) nameEl.textContent = 'Загрузка…';
      show(bar);
      var att = await doUpload('/api/chat/' + currentFriendId + '/upload-file', f);
      if (!att) { hide(bar); return false; }
      try { _pendingAttachment = att; } catch (e) { window._pendingAttachment = att; }
      if (nameEl) nameEl.textContent = '📎 ' + (att.name || 'file');
      return true;
    };
  }

  document.querySelectorAll('.chat-empty div').forEach(function (d) {
    if (d.textContent.indexOf('поделиться любой задачей') >= 0) {
      d.textContent = 'Можно отправлять текст, фото, видео и документы';
    }
  });

  /* ───── Групповой чат ───── */
  if (document.getElementById('gcFileInput')) {
    document.getElementById('gcFileInput').setAttribute('accept', ACCEPT);
    var gb = document.getElementById('gcAttachBtn');
    if (gb) { gb.textContent = '📎'; gb.title = 'Прикрепить файл (фото, видео, документы)'; }

    window.uploadGcAttachment = async function (file) {
      if (!file || typeof GID === 'undefined') return null;
      var att = await doUpload('/api/groups/' + GID + '/upload-file', file);
      if (!att) return null;
      try { gcPendingAttachment = att; } catch (e) { window.gcPendingAttachment = att; }
      var nm = document.getElementById('gcAttachName');
      if (nm) nm.textContent = '📎 ' + (att.name || 'file');
      show(document.getElementById('gcAttachPreview'));
      return att;
    };
  }
})();
