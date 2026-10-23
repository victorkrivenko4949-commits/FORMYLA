/* OLYMP_CATALOG_V3.2 — общий JS раздела /olymp-catalog: фильтры, копирование, лайтбокс, ИИ-тьютор */
(function () {
  'use strict';
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ---------- toast ---------- */
  let toastEl;
  function toast(msg) {
    if (!toastEl) { toastEl = document.createElement('div'); toastEl.className = 'oc-toast'; document.body.appendChild(toastEl); }
    toastEl.textContent = msg; toastEl.classList.add('on');
    clearTimeout(toastEl._t); toastEl._t = setTimeout(() => toastEl.classList.remove('on'), 1600);
  }

  /* ---------- копирование ---------- */
  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); toast('Скопировано'); }
    catch (e) { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); toast('Скопировано'); }
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-copy]');
    if (!b) return;
    e.preventDefault();
    const sel = b.getAttribute('data-copy');
    const card = b.closest('.oc-task');
    let text = '';
    if (sel === 'task' && card) {
      const t = $('.oc-text', card), a = $('.oc-ans', card), s = $('.oc-sol', card);
      text = (t ? t.textContent.trim() : '') + (a ? '\n\nОтвет. ' + a.textContent.trim() : '') + (s && b.hasAttribute('data-with-sol') ? '\n\nРешение. ' + s.textContent.trim() : '');
    } else if (sel === 'link') { text = b.getAttribute('data-href') || location.href; }
    else if (sel === 'statement' && card) { const t = $('.oc-text', card); text = t ? t.textContent.trim() : ''; }
    copyText(text);
  });

  /* ---------- dropdown ---------- */
  document.addEventListener('click', (e) => {
    const tg = e.target.closest('[data-dd]');
    $$('.oc-dd.open').forEach(d => { if (!d.contains(e.target)) d.classList.remove('open'); });
    if (tg) { e.preventDefault(); tg.closest('.oc-dd').classList.toggle('open'); }
  });

  /* ---------- lightbox ---------- */
  let lb;
  document.addEventListener('click', (e) => {
    const img = e.target.closest('img.oc-fig');
    if (!img) return;
    if (!lb) { lb = document.createElement('div'); lb.className = 'oc-lb'; lb.innerHTML = '<img alt="">'; lb.onclick = () => lb.classList.remove('on'); document.body.appendChild(lb); }
    $('img', lb).src = img.src; lb.classList.add('on');
  });

  /* ---------- фильтры на странице олимпиады ---------- */
  const filterBar = $('#oc-filter');
  if (filterBar) {
    const sel = $('#oc-year-jump');
    if (sel) sel.addEventListener('change', () => { const el = document.getElementById(sel.value); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); sel.value = ''; });
    $$('[data-toggle-sol]').forEach(b => b.addEventListener('click', (e) => {
      e.preventDefault(); const open = b.getAttribute('data-toggle-sol') === 'open';
      $$('details.oc-sol-wrap, details.oc-ans-wrap').forEach(d => d.open = open);
      b.setAttribute('data-toggle-sol', open ? 'close' : 'open'); b.textContent = open ? 'Скрыть всё' : 'Раскрыть все ответы и решения';
    }));
  }

  /* ---------- Markdown + LaTeX ---------- */
  function protectMath(src) {
    const store = [];
    const put = (m) => { store.push(m); return '\u0000' + (store.length - 1) + '\u0000'; };
    let s = src.replace(/\$\$[\s\S]*?\$\$/g, put).replace(/\\\[[\s\S]*?\\\]/g, put).replace(/\\\([\s\S]*?\\\)/g, put)
      .replace(/(^|[^\\$])\$(?!\s)([^$\n]*?[^\\\s$])\$(?!\d)/g, (m, pre, body) => pre + put('$' + body + '$'));
    return { s, store };
  }
  function restoreMath(html, store) { return html.replace(/\u0000(\d+)\u0000/g, (m, i) => store[+i]); }
  function escapeHtml(s) { return s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  function renderMd(text) {
    const { s, store } = protectMath(text || '');
    let html;
    if (window.marked) { try { html = marked.parse(s, { breaks: true, gfm: true }); } catch (e) { html = escapeHtml(s).replace(/\n/g, '<br>'); } }
    else html = escapeHtml(s).replace(/\n/g, '<br>');
    html = restoreMath(html, store);
    if (window.DOMPurify) html = DOMPurify.sanitize(html, { ADD_ATTR: ['target'] });
    return html;
  }
  /* V3.2: формулы рендерит KaTeX (общий для сайта). ocRenderMath (из _style.html) сначала нормализует \( \) -> $ $,
     потом вызывает renderMathInElement; если его нет — пробуем глобальный reRenderMath из base.html. */
  function typeset(el) {
    try {
      if (window.ocRenderMath && window.ocRenderMath(el)) return Promise.resolve();
      if (typeof window.reRenderMath === 'function') window.reRenderMath(el);
    } catch (e) { console.warn('[oc] typeset error', e); }
    return Promise.resolve();
  }

  /* ---------- ИИ-тьютор ---------- */
  const tutor = $('#oc-tutor');
  if (!tutor) return;
  const slug = tutor.dataset.slug, uid = tutor.dataset.uid, model = tutor.dataset.model || 'deepseek-v4-pro';
  const apiBase = (tutor.dataset.apiBase || '/olymp-catalog').replace(/\/+$/, '');
  const KEY = 'oc_chat_' + uid.slice(0, 12);
  const msgs = $('#oc-msgs'), ta = $('#oc-input'), send = $('#oc-send'), status = $('#oc-status'), briefWrap = $('#oc-brief'), briefBody = $('#oc-brief-body');
  let history = [];
  try { history = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch (e) { history = []; }
  let ready = false, busy = false;

  function setStatus(kind, text) { status.className = 'oc-status ' + kind; status.innerHTML = '<i></i>' + text; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(history.slice(-40))); } catch (e) {} }
  function scroll() { msgs.scrollTop = msgs.scrollHeight; }
  function addMsg(role, text) {
    const d = document.createElement('div'); d.className = 'oc-msg ' + role;
    if (role === 'a') { d.innerHTML = renderMd(text); typeset(d).then(scroll); }
    else d.textContent = text;
    msgs.appendChild(d); scroll(); return d;
  }
  function addTyping() { const d = document.createElement('div'); d.className = 'oc-msg a'; d.innerHTML = '<span class="oc-typing"><i></i><i></i><i></i></span>'; msgs.appendChild(d); scroll(); return d; }
  function autosize() { ta.style.height = 'auto'; ta.style.height = Math.min(160, ta.scrollHeight) + 'px'; }

  if (history.length) { history.forEach(m => addMsg(m.role === 'user' ? 'u' : 'a', m.content)); addMsg('sys', 'История восстановлена · ' + new Date().toLocaleDateString('ru')); }
  else addMsg('sys', 'Тьютор получает условие и эталонное решение задачи и готовится к вашим вопросам…');

  async function api(path, body) {
    const r = await fetch(apiBase + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' });
    let data = null; try { data = await r.json(); } catch (e) {}
    if (!r.ok || !data || !data.ok) { const err = new Error((data && (data.detail || data.error)) || ('HTTP ' + r.status)); err.code = data && data.error; throw err; }
    return data;
  }

  async function prepare(force) {
    setStatus('prep', force ? 'Перечитывает задачу…' : 'Изучает задачу…');
    send.disabled = true;
    const t0 = Date.now();
    try {
      const d = await api('/api/tutor/prepare', { slug, uid, force: !!force });
      ready = true;
      const secs = d.cached ? 'из кэша' : ((Date.now() - t0) / 1000).toFixed(0) + ' с';
      setStatus('ready', 'Готов · ' + model + ' · ' + secs);
      if (d.brief) { briefBody.innerHTML = renderMd(d.brief); typeset(briefBody); briefWrap.style.display = ''; }
      if (!history.length) { msgs.innerHTML = ''; addMsg('sys', 'Тьютор разобрал задачу и готов отвечать. Спросите что угодно: подсказку, идею, разбор шага или проверьте своё решение.'); }
      send.disabled = false;
    } catch (e) {
      ready = false;
      setStatus('err', 'Не удалось подготовиться');
      addMsg('err', 'Ошибка подготовки: ' + e.message + '. Можно всё равно задать вопрос — тьютор разберёт задачу по ходу.');
      send.disabled = false;
    }
  }

  async function ask(text) {
    text = (text || '').trim();
    if (!text || busy) return;
    busy = true; send.disabled = true; ta.value = ''; autosize();
    addMsg('u', text); history.push({ role: 'user', content: text }); save();
    const typing = addTyping();
    try {
      const d = await api('/api/tutor/chat', { slug, uid, messages: history.slice(-24) });
      typing.remove();
      addMsg('a', d.reply); history.push({ role: 'assistant', content: d.reply }); save();
      if (!ready) { ready = true; setStatus('ready', 'Готов · ' + model); }
    } catch (e) {
      typing.remove();
      history.pop(); save();
      addMsg('err', 'Ошибка: ' + e.message);
    } finally { busy = false; send.disabled = false; ta.focus(); }
  }

  send.addEventListener('click', () => ask(ta.value));
  ta.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(ta.value); } });
  ta.addEventListener('input', autosize);
  $$('[data-quick]', tutor).forEach(b => b.addEventListener('click', () => ask(b.getAttribute('data-quick'))));
  const clr = $('#oc-clear'); if (clr) clr.addEventListener('click', () => { history = []; save(); msgs.innerHTML = ''; addMsg('sys', 'Диалог очищен. Тьютор по-прежнему помнит разбор задачи.'); });
  const re = $('#oc-reprep'); if (re) re.addEventListener('click', () => prepare(true));
  const cp = $('#oc-copychat'); if (cp) cp.addEventListener('click', () => copyText(history.map(m => (m.role === 'user' ? 'Я: ' : 'Тьютор: ') + m.content).join('\n\n')));

  prepare(false);
  if (location.hash === '#tutor') setTimeout(() => ta.focus(), 300);
})();
