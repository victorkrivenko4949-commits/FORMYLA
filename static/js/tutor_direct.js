/* FORMYLA: open the existing math tutor directly, without the agent picker. */
(function () {
    'use strict';
    function init() {
        var popup = document.getElementById('ai-tutor-popup');
        var chat = document.getElementById('chatScreen');
        var picker = document.getElementById('agentSelectionScreen');
        var button = document.getElementById('tutorBtn');
        var input = document.getElementById('tutorInput');
        if (!popup || !chat || !picker || !button || !input || popup.dataset.directChat === '1') return;
        if (typeof window.toggleTutorPopup !== 'function' || typeof window.selectAgent !== 'function' || typeof window.showAgentSelection !== 'function') return;

        var originalToggle = window.toggleTutorPopup;
        var originalSelect = window.selectAgent;
        var opener = null;
        var title = 'Помощник по математике';
        var closeIcon = '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
        var chatIcon = '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M20 11.5a8 8 0 01-8 8H4l1.7-4A8 8 0 1120 11.5z"/><path d="M8 10h8M8 14h5"/></svg>';
        function isOpen() { return typeof popupOpen !== 'undefined' ? popupOpen : popup.style.display === 'flex'; }
        function refreshLabels() {
            var name = document.getElementById('currentAgentName');
            if (name) {
                name.textContent = title;
                if (name.nextElementSibling) name.nextElementSibling.textContent = 'Задачи, подсказки и разбор решения';
            }
            var open = isOpen();
            button.innerHTML = open ? closeIcon : chatIcon;
            button.setAttribute('aria-label', open ? 'Закрыть ИИ-тьютора' : 'ИИ-тьютор: открыть чат');
            button.setAttribute('aria-expanded', String(open));
            button.setAttribute('aria-controls', 'ai-tutor-popup');
            button.title = open ? 'Закрыть чат' : 'Помощник по математике';
            popup.setAttribute('aria-hidden', String(!open));
        }
        function revealChat() {
            picker.style.display = 'none';
            chat.style.display = 'flex';
            refreshLabels();
        }
        window.selectAgent = function () {
            var args = Array.prototype.slice.call(arguments);
            if (args[0] === 'general') args[1] = title;
            var result = originalSelect.apply(this, args);
            revealChat();
            return result;
        };
        window.showAgentSelection = function () {
            // Do not reload history or reset attachments/draft when reopening.
            if (typeof currentAgent === 'undefined' || !currentAgent) {
                return window.selectAgent('general', title);
            }
            revealChat();
        };
        window.toggleTutorPopup = function () {
            var wasOpen = isOpen();
            if (!wasOpen) opener = document.activeElement;
            var result = originalToggle.apply(this, arguments);
            refreshLabels();
            if (!isOpen() && opener && document.contains(opener)) opener.focus();
            return result;
        };

        var style = document.createElement('style');
        style.textContent = `
#ai-tutor-popup.fa-direct-chat{position:fixed!important;right:24px!important;left:auto!important;bottom:96px!important;width:min(600px,calc(100vw - 48px))!important;height:min(720px,calc(100dvh - 128px))!important;min-width:0!important;min-height:0!important;max-width:calc(100vw - 24px)!important;max-height:calc(100dvh - 110px)!important;resize:none!important;overflow:hidden!important;border-radius:20px!important;box-sizing:border-box;box-shadow:0 20px 65px #0005!important}
#ai-tutor-popup.fa-direct-chat #agentSelectionScreen{display:none!important}
#ai-tutor-popup.fa-direct-chat #chatScreen{display:flex!important;flex-direction:column;height:100%;min-height:0;min-width:0}
#ai-tutor-popup.fa-direct-chat #chatScreen>div{min-height:0}
#ai-tutor-popup.fa-direct-chat #chatScreen>div:first-child{flex-shrink:0}
#ai-tutor-popup.fa-direct-chat #chatScreen>div:last-child{flex-shrink:0}
#ai-tutor-popup.fa-direct-chat #currentAgentName{font-size:16px;line-height:1.4}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help{flex-shrink:0;padding:13px 18px;border-bottom:1px solid var(--border-mid,#334155);background:var(--surface-2,rgba(148,163,184,.06));color:var(--text-muted,#94a3b8);font-size:13px;line-height:1.6}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help p{margin:0}
#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts button{font:inherit;font-size:12px;color:var(--text-main,#e2e8f0);background:transparent;border:1px solid var(--border-mid,#475569);border-radius:9px;padding:6px 10px;cursor:pointer;min-height:32px}
#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts button:hover{border-color:var(--accent-2,#38bdf8);background:rgba(56,189,248,.08)}
#ai-tutor-popup.fa-direct-chat button:focus-visible,#ai-tutor-popup.fa-direct-chat textarea:focus-visible{outline:2px solid var(--accent-2,#38bdf8);outline-offset:2px}
#ai-tutor-popup.fa-direct-chat #tutorInput{font-size:16px;line-height:1.5;min-width:0;max-height:150px;box-sizing:border-box}
#tutorBtn[data-direct-chat="1"]{display:flex;align-items:center;justify-content:center}
@media(max-width:768px){#ai-tutor-popup.fa-direct-chat{left:12px!important;right:12px!important;bottom:88px!important;width:calc(100vw - 24px)!important;height:calc(100dvh - 112px)!important;max-height:calc(100dvh - 100px)!important;border-radius:16px!important}#ai-tutor-popup.fa-direct-chat .tutor-direct-help{padding:10px 14px;font-size:12px}#ai-tutor-popup.fa-direct-chat #currentAgentName{font-size:14px}}
@media(max-height:550px){#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts{display:none}#ai-tutor-popup.fa-direct-chat .tutor-direct-help{padding:7px 12px;font-size:11px}}
`;
        document.head.appendChild(style);
        var help = document.createElement('div');
        help.className = 'tutor-direct-help';
        var intro = document.createElement('p');
        intro.textContent = 'Пришлите условие или фото задачи — разберём по шагам. Можно попросить подсказку или проверить своё решение.';
        help.appendChild(intro);
        var prompts = document.createElement('div'); prompts.className = 'tutor-direct-prompts';
        [
            ['Дай подсказку', 'Дай подсказку к задаче, не раскрывая полное решение.'],
            ['Объясни шаг', 'Объясни подробнее этот шаг решения: '],
            ['Проверь решение', 'Проверь моё решение и объясни, где я ошибся: ']
        ].forEach(function (item) {
            var b = document.createElement('button'); b.type = 'button'; b.textContent = item[0];
            b.addEventListener('click', function () {
                if (input.disabled) return;
                if (!input.value.trim()) input.value = item[1];
                else input.value += '\n' + item[1];
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
            });
            prompts.appendChild(b);
        });
        help.appendChild(prompts);
        chat.insertBefore(help, chat.children[1] || null);
        input.placeholder = 'Напишите задачу или прикрепите фото…';
        input.setAttribute('aria-label', 'Сообщение ИИ-тьютору');
        popup.setAttribute('role', 'dialog');
        popup.setAttribute('aria-label', title);
        chat.querySelectorAll('[onclick*="showAgentSelection"]').forEach(function (b) {
            b.innerHTML = closeIcon; b.title = 'Закрыть чат'; b.setAttribute('aria-label', 'Закрыть чат');
            b.onclick = function () { if (isOpen()) window.toggleTutorPopup(); };
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isOpen() && !e.defaultPrevented) {
                e.preventDefault(); window.toggleTutorPopup();
            }
        });
        button.dataset.directChat = '1'; popup.dataset.directChat = '1';
        popup.classList.add('fa-direct-chat');
        refreshLabels();
        if (isOpen()) window.showAgentSelection();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
    else init();
})();
