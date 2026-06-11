/* ====================================================================
   FORMYLA — Support Chat JS
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
     * @param {Object} opts {text, side, label}
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

        // remove "waiting" hint if present
        var hint = chatEl.querySelector('.support-waiting-hint');
        if (hint) hint.remove();

        chatEl.appendChild(wrap);
        scrollChatToBottom(chatEl);
    }

    /* ---------------- form submission ---------------- */
    function bindForm(form) {
        if (!form || form.__supportBound) return;
        form.__supportBound = true;

        var role = form.getAttribute('data-role') || 'admin';
        var label = form.getAttribute('data-label') || (role === 'admin'
            ? 'Поддержка FORMYLA' : 'Ты');
        var ticketCard = form.closest('.ticket-card');
        var chatEl = ticketCard
            ? ticketCard.querySelector('.support-chat, .user-support-chat')
            : null;

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();

            var textarea = form.querySelector('textarea, input[name="reply_text"]');
            var btn = form.querySelector('button[type="submit"], .send-btn');
            var raw = (textarea && textarea.value || '').trim();
            if (!raw) {
                showToast('Введите текст сообщения', 'error');
                if (textarea) textarea.focus();
                return;
            }
            if (raw.length > 5000) {
                showToast('Слишком длинное сообщение (макс 5000)', 'error');
                return;
            }

            // Optimistic UI
            var side = (role === 'admin') ? 'right' : 'right';
            // Note: in admin chat, admin replies -> RIGHT.
            //       In user chat,  user replies  -> RIGHT.
            // So "right" is always correct for the sender's own bubble.
            appendBubble(chatEl, { text: raw, side: side, label: label });

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
        document.querySelectorAll('form.support-composer').forEach(bindForm);
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
