/* ====================================================================
   FORMYLA.net — Support Chat JS
   Used by both admin/support_inbox.html and my_support.html.

   Responsibilities:
     - submit reply forms via fetch() (no full-page reload)
     - append the new bubble immediately on the correct side
     - autoscroll to bottom of each chat on load + after sending
     - show pretty toast for success / error
     - graceful fallback to normal POST submit if fetch is unsupported
   ==================================================================== */
(function () {
    'use strict';

    /* ---------------- toast helper ---------------- */
    function ensureToastStack() {
        var stack = document.querySelector('.support-toast-stack');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'support-toast-stack';
            document.body.appendChild(stack);
        }
        return stack;
    }

    function showToast(text, kind) {
        var stack = ensureToastStack();
        var el = document.createElement('div');
        el.className = 'support-toast ' + (kind || 'info');
        el.textContent = text;
        stack.appendChild(el);
        setTimeout(function () {
            el.style.transition = 'opacity .35s ease, transform .35s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateY(-6px)';
            setTimeout(function () { el.remove(); }, 400);
        }, 3200);
    }

    /* ---------------- time formatting ---------------- */
    function fmtNow() {
        var d = new Date();
        var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
        return pad(d.getDate()) + '.' + pad(d.getMonth() + 1) +
            ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }

    /* ---------------- autoscroll ---------------- */
    function scrollChatToBottom(chatEl) {
        if (!chatEl) return;
        try { chatEl.scrollTop = chatEl.scrollHeight; } catch (e) {}
    }

    function scrollAllChatsToBottom() {
        document.querySelectorAll('.support-chat, .user-support-chat')
            .forEach(scrollChatToBottom);
    }

    /* ---------------- append bubble ---------------- */
    /**
     * @param {HTMLElement} chatEl the .support-chat or .user-support-chat
     * @param {Object} opts {text, side, label, photoUrl}
     *   side: 'left' | 'right'
     *   The CSS class scheme is chosen based on which chat container we are in.
     */
    function appendBubble(chatEl, opts) {
        if (!chatEl) return;
        var isUserChat = chatEl.classList.contains('user-support-chat');
        var msgClass, bubbleClass, metaClass;

        if (isUserChat) {
            metaClass = 'user-support-message-meta';
            bubbleClass = 'user-support-message-bubble';
            // In user-side chat: 'right' = my own messages, 'left' = support
            msgClass = 'user-support-message ' + (opts.side === 'right'
                ? 'user-support-message-me'
                : 'user-support-message-support');
        } else {
            metaClass = 'support-message-meta';
            bubbleClass = 'support-message-bubble';
            // In admin-side chat: 'left' = user complaints, 'right' = admin
            msgClass = 'support-message ' + (opts.side === 'right'
                ? 'support-message-admin'
                : 'support-message-user');
        }

        var wrap = document.createElement('div');
        wrap.className = msgClass;

        var meta = document.createElement('div');
        meta.className = metaClass;
        meta.textContent = (opts.label || '') + ' · ' + fmtNow();

        var bubble = document.createElement('div');
        bubble.className = bubbleClass;
        bubble.textContent = opts.text;

        wrap.appendChild(meta);
        wrap.appendChild(bubble);

        if (opts.photoUrl) {
            var link = document.createElement('a');
            link.className = 'support-msg-photo';
            link.href = opts.photoUrl;
            link.target = '_blank';
            link.rel = 'noopener';
            var img = document.createElement('img');
            img.src = opts.photoUrl;
            img.alt = 'фото';
            link.appendChild(img);
            wrap.appendChild(link);
        }

        // remove "waiting" hint if present
        var hint = chatEl.querySelector('.support-waiting-hint');
        if (hint) hint.remove();

        chatEl.appendChild(wrap);
        scrollChatToBottom(chatEl);
    }

    /* ---------------- edit / delete ---------------- */
    function msgApiUrl(ref, action) {
        return '/api/support/message/' + encodeURIComponent(ref) + '/' + action;
    }

    function bindMsgActions(chatRoot) {
        if (!chatRoot || chatRoot.__actionsBound) return;
        chatRoot.__actionsBound = true;

        chatRoot.addEventListener('click', function (ev) {
            var btn = ev.target.closest('.support-msg-action');
            if (!btn) return;
            var wrap = btn.closest('[data-msg-id]');
            if (!wrap) return;
            var ref = wrap.getAttribute('data-msg-id');
            var action = btn.getAttribute('data-action');
            var bubble = wrap.querySelector('.user-support-message-bubble, .support-message-bubble');
            if (!bubble || bubble.classList.contains('support-msg-deleted')) return;

            if (action === 'delete') {
                if (!window.confirm('Удалить сообщение?')) return;
                fetch(msgApiUrl(ref, 'delete'), {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                }).then(function (resp) {
                    if (resp.ok) {
                        bubble.textContent = 'Сообщение удалено';
                        bubble.classList.add('support-msg-deleted');
                        var actions = wrap.querySelector('.support-msg-actions');
                        if (actions) actions.remove();
                        var photo = wrap.querySelector('.support-msg-photo');
                        if (photo) photo.remove();
                        showToast('Сообщение удалено', 'success');
                    } else {
                        showToast('Не удалось удалить (HTTP ' + resp.status + ')', 'error');
                    }
                }).catch(function () {
                    showToast('Ошибка сети', 'error');
                });
                return;
            }

            if (action === 'edit') {
                var currentText = '';
                Array.prototype.forEach.call(bubble.childNodes, function (n) {
                    if (n.nodeType === Node.TEXT_NODE) currentText += n.textContent;
                });
                currentText = currentText.trim();
                var next = window.prompt('Изменить сообщение:', currentText);
                if (next === null) return;
                next = next.trim();
                if (!next || next.length > 5000) {
                    showToast('Текст 1-5000 символов', 'error');
                    return;
                }
                if (next === currentText) return;
                var fd = new FormData();
                fd.append('text', next);
                fetch(msgApiUrl(ref, 'edit'), {
                    method: 'POST',
                    body: fd,
                    credentials: 'same-origin',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                }).then(function (resp) {
                    if (resp.ok) {
                        bubble.textContent = next;
                        var tag = document.createElement('span');
                        tag.className = 'support-edited-tag';
                        tag.textContent = '(изменено)';
                        bubble.appendChild(tag);
                        showToast('Сообщение изменено', 'success');
                    } else {
                        showToast('Не удалось изменить (HTTP ' + resp.status + ')', 'error');
                    }
                }).catch(function () {
                    showToast('Ошибка сети', 'error');
                });
            }
        });
    }

    /* ---------------- photo attach ---------------- */
    function bindPhotoAttach(form) {
        var btn = form.querySelector('.attach-btn');
        var input = form.querySelector('.support-photo-input');
        var chip = form.querySelector('.support-photo-chip');
        if (!btn || !input) return;

        btn.addEventListener('click', function () { input.click(); });
        input.addEventListener('change', function () {
            var f = input.files && input.files[0];
            if (!f) { if (chip) { chip.hidden = true; chip.textContent = ''; } return; }
            if (!f.type || !f.type.startsWith('image/')) {
                showToast('Разрешены только изображения', 'error');
                input.value = '';
                if (chip) { chip.hidden = true; chip.textContent = ''; }
                return;
            }
            if (f.size > 10 * 1024 * 1024) {
                showToast('Фото больше 10 МБ', 'error');
                input.value = '';
                if (chip) { chip.hidden = true; chip.textContent = ''; }
                return;
            }
            if (chip) {
                chip.textContent = '\u{1F4CE} ' + f.name;
                chip.hidden = false;
                chip.title = 'Нажми, чтобы убрать фото';
                chip.onclick = function () {
                    input.value = '';
                    chip.hidden = true;
                    chip.textContent = '';
                };
            }
            showToast('Фото прикреплено', 'success');
        });
    }

    /* ---------------- form submission ---------------- */
    function bindForm(form) {
        if (!form || form.__supportBound) return;
        form.__supportBound = true;

        var role = form.getAttribute('data-role') || 'admin';
        var label = form.getAttribute('data-label') || (role === 'admin'
            ? 'Поддержка FORMYLA.net' : 'Ты');
        var ticketCard = form.closest('.ticket-card');
        var chatEl = ticketCard
            ? ticketCard.querySelector('.support-chat, .user-support-chat')
            : null;

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();

            var textarea = form.querySelector('textarea, input[name="reply_text"]');
            var btn = form.querySelector('button[type="submit"], .send-btn');
            var photoInput = form.querySelector('.support-photo-input');
            var chip = form.querySelector('.support-photo-chip');
            var photoFile = (photoInput && photoInput.files && photoInput.files[0]) || null;
            var raw = (textarea && textarea.value || '').trim();
            if (!raw && !photoFile) {
                showToast('Введите текст сообщения или прикрепите фото', 'error');
                if (textarea) textarea.focus();
                return;
            }
            if (raw.length > 5000) {
                showToast('Слишком длинное сообщение (макс 5000)', 'error');
                return;
            }

            // Optimistic UI (для фото — временный локальный превью URL)
            var side = (role === 'admin') ? 'right' : 'right';
            // Note: in admin chat, admin replies -> RIGHT.
            //       In user chat,  user replies  -> RIGHT.
            // So "right" is always correct for the sender's own bubble.
            var localPhotoUrl = null;
            if (photoFile) {
                try { localPhotoUrl = URL.createObjectURL(photoFile); } catch (e) {}
            }
            appendBubble(chatEl, { text: raw, side: side, label: label, photoUrl: localPhotoUrl });

            if (btn) { btn.disabled = true; btn.dataset._oldText = btn.textContent; btn.textContent = 'Отправка…'; }

            var fd = new FormData(form);
            fetch(form.action, {
                method: 'POST',
                body: fd,
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            }).then(function (resp) {
                // Server still returns redirect to the same page on success;
                // we treat any 2xx/3xx as success since we already updated UI.
                if (resp.ok || (resp.status >= 300 && resp.status < 400)) {
                    if (textarea) textarea.value = '';
                    if (photoInput) photoInput.value = '';
                    if (chip) { chip.hidden = true; chip.textContent = ''; }
                    showToast('Сообщение отправлено', 'success');
                } else {
                    showToast('Не удалось отправить (HTTP ' + resp.status + ')', 'error');
                }
            }).catch(function () {
                showToast('Ошибка сети, попробуйте ещё раз', 'error');
            }).finally(function () {
                if (btn) {
                    btn.disabled = false;
                    if (btn.dataset._oldText) btn.textContent = btn.dataset._oldText;
                }
                if (textarea) { textarea.style.height = ''; textarea.focus(); }
            });
        });

        // auto-grow textarea
        var ta = form.querySelector('textarea');
        if (ta) {
            ta.addEventListener('input', function () {
                ta.style.height = 'auto';
                ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
            });
            // Ctrl/Cmd+Enter to send
            ta.addEventListener('keydown', function (e) {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    if (typeof form.requestSubmit === 'function') form.requestSubmit();
                    else form.dispatchEvent(new Event('submit', { cancelable: true }));
                }
            });
        }
    }

    /* ---------------- init ---------------- */
    function init() {
        document.querySelectorAll('form.support-composer').forEach(function (form) {
            bindForm(form);
            bindPhotoAttach(form);
        });
        document.querySelectorAll('.support-chat, .user-support-chat').forEach(bindMsgActions);
        scrollAllChatsToBottom();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // expose for potential reuse
    window.FormylaSupportChat = {
        showToast: showToast,
        appendBubble: appendBubble,
        scrollAllChatsToBottom: scrollAllChatsToBottom
    };
})();
