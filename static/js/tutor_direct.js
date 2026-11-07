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
        var chevronIcon = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>';
        var HELP_KEY = 'fa_tutor_help_collapsed';
        var isMobile = window.matchMedia('(max-width: 768px)').matches;
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
#ai-tutor-popup.fa-direct-chat .tutor-direct-help{flex-shrink:0;padding:10px 18px;border-bottom:1px solid var(--border-mid,#334155);background:var(--surface-2,rgba(148,163,184,.06));color:var(--text-muted,#94a3b8);font-size:13px;line-height:1.6}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help p{margin:0}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help-head span{font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--text-muted,#94a3b8);text-transform:uppercase}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help-toggle{font:inherit;display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;padding:0;border:0;border-radius:8px;background:transparent;color:var(--text-muted,#94a3b8);cursor:pointer}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help-toggle:hover{background:rgba(148,163,184,.15);color:var(--text-main,#e2e8f0)}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help-toggle svg{transition:transform .2s}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help.is-collapsed .tutor-direct-help-toggle svg{transform:rotate(-180deg)}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help-body{margin-top:6px}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help.is-collapsed .tutor-direct-help-body{display:none}
#ai-tutor-popup.fa-direct-chat .tutor-direct-help.is-collapsed{padding-top:6px;padding-bottom:6px}
#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts button{font:inherit;font-size:12px;color:var(--text-main,#e2e8f0);background:transparent;border:1px solid var(--border-mid,#475569);border-radius:9px;padding:5px 10px;cursor:pointer;min-height:30px;white-space:nowrap}
#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts button:hover{border-color:var(--accent-2,#38bdf8);background:rgba(56,189,248,.08)}
#ai-tutor-popup.fa-direct-chat button:focus-visible,#ai-tutor-popup.fa-direct-chat textarea:focus-visible{outline:2px solid var(--accent-2,#38bdf8);outline-offset:2px}
#ai-tutor-popup.fa-direct-chat #tutorInput{font-size:16px;line-height:1.5;min-width:0;max-height:150px;box-sizing:border-box}
#tutorBtn[data-direct-chat="1"]{display:flex;align-items:center;justify-content:center}
@media(max-width:768px){#ai-tutor-popup.fa-direct-chat{left:12px!important;right:12px!important;bottom:88px!important;width:calc(100vw - 24px)!important;height:calc(100dvh - 112px)!important;max-height:calc(100dvh - 100px)!important;border-radius:16px!important}#ai-tutor-popup.fa-direct-chat #chatScreen>div:first-child{padding-top:10px!important;padding-bottom:10px!important}#ai-tutor-popup.fa-direct-chat #currentAgentName{font-size:14px}#ai-tutor-popup.fa-direct-chat #currentAgentName+*{font-size:11px!important}#ai-tutor-popup.fa-direct-chat .tutor-direct-help{padding:6px 12px;font-size:11px;line-height:1.45}#ai-tutor-popup.fa-direct-chat .tutor-direct-help.is-collapsed{padding-top:4px;padding-bottom:4px}#ai-tutor-popup.fa-direct-chat .tutor-direct-help-head span{font-size:10px}#ai-tutor-popup.fa-direct-chat .tutor-direct-help-body{margin-top:4px}#ai-tutor-popup.fa-direct-chat .tutor-direct-help-body p{display:none}#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts{margin-top:0;flex-wrap:nowrap;overflow-x:auto;gap:5px;padding-bottom:2px;scrollbar-width:none;-webkit-overflow-scrolling:touch}#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts::-webkit-scrollbar{display:none}#ai-tutor-popup.fa-direct-chat .tutor-direct-prompts button{font-size:11px;padding:3px 8px;min-height:24px;border-radius:7px;flex-shrink:0}}
@media(max-height:550px){#ai-tutor-popup.fa-direct-chat .tutor-direct-help-body{display:none}#ai-tutor-popup.fa-direct-chat .tutor-direct-help{padding:4px 12px;font-size:11px}}
`;
        document.head.appendChild(style);

        var help = document.createElement('div');
        help.className = 'tutor-direct-help';
        var helpHead = document.createElement('div'); helpHead.className = 'tutor-direct-help-head';
        var helpLabel = document.createElement('span'); helpLabel.textContent = 'Быстрые команды';
        var helpToggle = document.createElement('button'); helpToggle.type = 'button';
        helpToggle.className = 'tutor-direct-help-toggle'; helpToggle.innerHTML = chevronIcon;
        helpToggle.setAttribute('aria-controls', 'tutorDirectHelpBody');
        helpHead.appendChild(helpLabel); helpHead.appendChild(helpToggle);
        help.appendChild(helpHead);
        var helpBody = document.createElement('div'); helpBody.className = 'tutor-direct-help-body'; helpBody.id = 'tutorDirectHelpBody';
        var intro = document.createElement('p');
        intro.textContent = 'Пришлите условие или фото задачи — разберём по шагам. Можно попросить подсказку или проверить своё решение.';
        helpBody.appendChild(intro);
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
        helpBody.appendChild(prompts);
        help.appendChild(helpBody);
        function setHelpCollapsed(collapsed, persist) {
            help.classList.toggle('is-collapsed', collapsed);
            helpToggle.setAttribute('aria-expanded', String(!collapsed));
            helpToggle.setAttribute('aria-label', collapsed ? 'Показать быстрые команды' : 'Скрыть быстрые команды');
            helpToggle.title = collapsed ? 'Показать команды' : 'Скрыть команды';
            if (persist) { try { localStorage.setItem(HELP_KEY, collapsed ? '1' : '0'); } catch (e) {} }
        }
        var saved = null;
        try { saved = localStorage.getItem(HELP_KEY); } catch (e) {}
        // On phones the panel is collapsed by default until the user opens it.
        setHelpCollapsed(saved === null ? isMobile : saved === '1', false);
        helpToggle.addEventListener('click', function () { setHelpCollapsed(!help.classList.contains('is-collapsed'), true); });
        helpLabel.addEventListener('click', function () { helpToggle.click(); });
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
