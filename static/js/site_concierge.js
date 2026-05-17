/* Site Concierge — AI-помощник по сайту FORMYLA.
 *
 * НЕ путать с виджетом ИИ-тьютора (#tutorBtn) — это отдельный концьерж по UX.
 * Виджет читает /api/concierge/intents для quick-replies и стучится в
 * /api/concierge/ask для ответов. История кэшируется в localStorage.
 */
(function () {
    'use strict';

    // ── Anti-collision: not on /drawing in board mode ──────────────────────
    function shouldHideOnThisPage() {
        var path = window.location.pathname || '';
        if (path.startsWith('/drawing')) {
            // Прячем только в режиме "доска" (?mode=board).
            var mode = new URLSearchParams(window.location.search).get('mode');
            if (mode === 'board' || mode === null || mode === '') {
                // По умолчанию /drawing открывается как доска → прячем.
                return true;
            }
        }
        return false;
    }

    // ── LocalStorage history ───────────────────────────────────────────────
    var LS_KEY = 'formyla_concierge_history_v1';
    var MAX_HISTORY = 20;
    function loadHistory() {
        try {
            var raw = localStorage.getItem(LS_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch (_e) { return []; }
    }
    function saveHistory(items) {
        try {
            var trimmed = items.slice(-MAX_HISTORY);
            localStorage.setItem(LS_KEY, JSON.stringify(trimmed));
        } catch (_e) {}
    }

    var history = loadHistory();
    var intents = [];           // [{id, intent, icon}]
    var showAllIntents = false;
    var root, panel, body, input, sendBtn, fab;

    // ── Render helpers ─────────────────────────────────────────────────────
    function escapeHtml(s) {
        return String(s || '').replace(/[&<>"']/g, function (c) {
            return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'})[c];
        });
    }

    function renderMessage(item) {
        var div = document.createElement('div');
        div.className = 'scf-msg ' + (item.role === 'user' ? 'user' : 'bot') +
                        (item.source === 'redirect' ? ' redirect' : '');
        div.innerHTML = escapeHtml(item.text);
        if (item.actions && item.actions.length) {
            var actionsWrap = document.createElement('div');
            actionsWrap.className = 'scf-actions';
            item.actions.forEach(function (a) {
                if (!a.url || !a.label) return;
                var link = document.createElement('a');
                link.className = 'scf-action';
                link.href = a.url;
                link.textContent = a.label;
                actionsWrap.appendChild(link);
            });
            div.appendChild(actionsWrap);
        }
        return div;
    }

    function renderQuickReplies() {
        var existing = body.querySelector('.scf-quick-wrap');
        if (existing) existing.remove();

        if (!intents.length) return;

        var wrap = document.createElement('div');
        wrap.className = 'scf-quick-wrap';

        var hint = document.createElement('div');
        hint.className = 'scf-msg bot';
        hint.textContent = 'Привет! Я помогу разобраться с сайтом. Что вы хотите сделать?';
        wrap.appendChild(hint);

        var grid = document.createElement('div');
        grid.className = 'scf-quick-grid';
        var shown = showAllIntents ? intents : intents.slice(0, 6);
        shown.forEach(function (it) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'scf-quick-btn';

            var icon = document.createElement('span');
            icon.className = 'qr-icon';
            icon.textContent = it.icon || '💬';

            var label = document.createElement('span');
            label.className = 'qr-label';
            label.textContent = it.intent || '';

            btn.appendChild(icon);
            btn.appendChild(label);
            btn.addEventListener('click', function () { ask(it.intent); });
            grid.appendChild(btn);
        });
        wrap.appendChild(grid);

        if (!showAllIntents && intents.length > 6) {
            var moreBtn = document.createElement('button');
            moreBtn.type = 'button';
            moreBtn.className = 'scf-more';
            moreBtn.textContent = '↓ Ещё варианты (' + (intents.length - 6) + ')';
            moreBtn.addEventListener('click', function () {
                showAllIntents = true;
                renderQuickReplies();
            });
            wrap.appendChild(moreBtn);
        }
        body.appendChild(wrap);
        scrollToBottom();
    }

    function renderHistory() {
        body.innerHTML = '';
        history.forEach(function (item) {
            body.appendChild(renderMessage(item));
        });
        renderQuickReplies();
    }

    function scrollToBottom() {
        body.scrollTop = body.scrollHeight;
    }

    function setTyping(on) {
        var existing = body.querySelector('.scf-typing');
        if (on && !existing) {
            var div = document.createElement('div');
            div.className = 'scf-typing';
            div.textContent = '…ищу ответ';
            body.appendChild(div);
            scrollToBottom();
        } else if (!on && existing) {
            existing.remove();
        }
    }

    function pushMessage(item) {
        history.push(item);
        saveHistory(history);
        body.appendChild(renderMessage(item));
        scrollToBottom();
    }

    // ── API ────────────────────────────────────────────────────────────────
    function ask(message) {
        if (!message || !message.trim()) return;
        var clean = message.trim();

        // Скрыть quick-replies после первого вопроса.
        var qr = body.querySelector('.scf-quick-wrap');
        if (qr) qr.remove();

        pushMessage({role: 'user', text: clean});
        if (input) input.value = '';
        if (sendBtn) sendBtn.disabled = true;
        setTyping(true);

        fetch('/api/concierge/ask', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
            credentials: 'same-origin',
            body: JSON.stringify({
                message: clean,
                current_url: window.location.pathname + window.location.search
            })
        }).then(function (r) {
            if (r.status === 429) {
                return {answer: 'Слишком много запросов за час. Попробуй чуть позже или загляни в /about.',
                        suggested_actions: [{label: '📖 О сервисе', url: '/about'}],
                        source: 'rate_limit'};
            }
            return r.json();
        }).then(function (data) {
            setTyping(false);
            pushMessage({
                role: 'bot',
                text: data.answer || 'Хм, не удалось ответить. Попробуй переформулировать.',
                actions: data.suggested_actions || [],
                source: data.source || 'unknown'
            });
        }).catch(function (err) {
            setTyping(false);
            pushMessage({
                role: 'bot',
                text: 'Ошибка сети. Попробуй чуть позже.',
                source: 'error'
            });
        }).then(function () {
            if (sendBtn) sendBtn.disabled = false;
            if (input) input.focus();
        });
    }

    function loadIntents() {
        fetch('/api/concierge/intents', {credentials: 'same-origin'})
            .then(function (r) { return r.json(); })
            .then(function (data) {
                intents = (data && data.intents) || [];
                renderQuickReplies();
            })
            .catch(function () { /* silent */ });
    }

    // ── Wiring ─────────────────────────────────────────────────────────────
    function openPanel() {
        panel.classList.add('is-open');
        fab.classList.add('is-open');
        if (history.length === 0) renderQuickReplies();
        setTimeout(function () { if (input) input.focus(); }, 60);
    }
    function closePanel() {
        panel.classList.remove('is-open');
        fab.classList.remove('is-open');
    }

    function init() {
        if (shouldHideOnThisPage()) {
            var r = document.getElementById('siteConciergeRoot');
            if (r) r.style.display = 'none';
            return;
        }
        root  = document.getElementById('siteConciergeRoot');
        if (!root) return;
        fab   = root.querySelector('.site-concierge-fab');
        panel = root.querySelector('.site-concierge-panel');
        body  = root.querySelector('.scf-body');
        input = root.querySelector('.scf-input-row input');
        sendBtn = root.querySelector('.scf-send');
        var closeBtn = root.querySelector('.scf-close');

        if (!fab || !panel || !body) return;

        fab.addEventListener('click', function () {
            if (panel.classList.contains('is-open')) closePanel();
            else openPanel();
        });
        if (closeBtn) closeBtn.addEventListener('click', closePanel);

        if (sendBtn && input) {
            sendBtn.addEventListener('click', function () { ask(input.value); });
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') { e.preventDefault(); ask(input.value); }
            });
        }

        renderHistory();
        loadIntents();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
