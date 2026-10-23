/* persist.js — cookie + localStorage: имя, личный ID, история подключений и вход «в одну кнопку» */
(function () {
  if (!window.App || !window.Meeting) return;
  const KEY = 'fm_meet';
  const MAX = 10;
  const YEAR = 365 * 24 * 3600;
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ico = n => (typeof icon === 'function' ? icon(n) : '');
  const say = (m, k, t) => (typeof toast === 'function' ? toast(m, k, t) : console.log(m));

  /* ---------- хранилище: cookie (основное, читается на всех страницах сайта) + localStorage ---------- */
  function readCookie() {
    const m = document.cookie.match(new RegExp('(?:^|; )' + KEY + '=([^;]*)'));
    if (!m) return null;
    try { return JSON.parse(decodeURIComponent(m[1])); } catch (e) { return null; }
  }
  function writeCookie(obj) {
    try {
      const v = encodeURIComponent(JSON.stringify(obj));
      document.cookie = KEY + '=' + v + '; path=/; max-age=' + YEAR + '; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
    } catch (e) { /* cookie запрещены */ }
  }
  function load() {
    let d = null;
    try { d = JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { /* нет localStorage */ }
    const c = readCookie();
    if (c && (!d || (c.ts || 0) > (d.ts || 0))) d = c;
    if (!d || typeof d !== 'object') d = {};
    return { name: d.name || '', pmi: d.pmi || '', rooms: Array.isArray(d.rooms) ? d.rooms : [], history: Array.isArray(d.history) ? d.history : [] };
  }
  function save() {
    const d = {
      ts: Date.now(),
      name: App.user.name || '',
      pmi: App.user.pmi || '',
      rooms: (App.rooms || []).slice(0, MAX).map(r => ({ id: String(r.id), topic: String(r.topic || '').slice(0, 60), host: !!r.host, pw: String(r.pw || '').slice(0, 10), waiting: r.waiting !== false, date: +new Date(r.date || Date.now()), n: r.n || 1 })),
      history: (App.history || []).slice(0, MAX).map(h => ({ topic: String(h.topic || '').slice(0, 60), id: h.id ? String(h.id) : '', date: +new Date(h.date || Date.now()), dur: h.dur || '', participants: h.participants || 1 }))
    };
    try { localStorage.setItem(KEY, JSON.stringify(d)); } catch (e) { /* нет localStorage */ }
    writeCookie(d);
  }
  function clearAll() {
    App.rooms = [];
    try { localStorage.removeItem(KEY); } catch (e) {}
    document.cookie = KEY + '=; path=/; max-age=0; SameSite=Lax';
    save();
  }
  window.FMPersist = { load, save, clear: clearAll };

  /* ---------- восстановление состояния ---------- */
  const saved = load();
  App.rooms = saved.rooms.map(r => Object.assign({}, r, { date: new Date(r.date) }));
  const hist = saved.history.map(h => Object.assign({}, h, { date: new Date(h.date) }));
  hist.unshift = function () {
    const r = Array.prototype.unshift.apply(this, arguments);
    const e = this[0];
    if (e && App.lastJoin && !e.id) { e.id = App.lastJoin.id; e.pw = App.lastJoin.pw; e.host = App.lastJoin.host; }
    if (this.length > MAX) this.length = MAX;
    save();
    return r;
  };
  App.history = hist;
  const siteName = window.FM_USER && window.FM_USER.name;
  if (saved.name && (!siteName || siteName === 'Гость')) {
    App.user.name = saved.name;
    App.user.initials = (window.SIM && SIM.initials(saved.name)) || 'Я';
  }
  if (saved.pmi) App.user.pmi = saved.pmi;

  /* ---------- учёт подключений ---------- */
  function rememberRoom(j) {
    const prev = (App.rooms || []).find(r => r.id === j.id);
    App.rooms = (App.rooms || []).filter(r => r.id !== j.id);
    App.rooms.unshift(Object.assign({}, j, { date: new Date(), n: (prev ? prev.n || 1 : 0) + 1 }));
    if (App.rooms.length > MAX) App.rooms.length = MAX;
    save();
  }
  const origOpen = Meeting.open.bind(Meeting);
  Meeting.open = function (opts) {
    const o = Object.assign({}, opts || {});
    if (!o.id) o.id = (typeof genMeetingId === 'function') ? genMeetingId() : String(Date.now());
    App.lastJoin = { id: o.id, topic: o.topic || 'Встреча FORMYLA', host: o.host !== false, pw: o.pw || '', waiting: o.waiting !== false };
    rememberRoom(App.lastJoin);
    return origOpen(o);
  };
  App.rejoin = function (id) {
    const rooms = App.rooms || [];
    const r = id ? rooms.find(x => x.id === id) : rooms[0];
    if (!r) { say('Сохранённых подключений пока нет', 'bad'); App.joinModal(); return; }
    Meeting.open({ id: r.id, topic: r.topic, host: r.host, pw: r.pw, waiting: r.waiting });
  };
  App.routes.rejoin = function (arg) {
    this.routes.home.call(this);
    let id = '';
    try { id = decodeURIComponent(arg || ''); } catch (e) { id = arg || ''; }
    App.rejoin(id.trim());
  };

  /* ---------- сохраняем имя/PMI при любой перерисовке ---------- */
  const origRoute = App.route;
  App.route = function () { const r = origRoute.apply(this, arguments); save(); return r; };

  /* ---------- карточка «Недавние подключения» на главной /meet ---------- */
  const origHome = App.routes.home;
  App.routes.home = function () {
    origHome.call(this);
    const app = $('#app'); const grid = app && app.querySelector('.home-grid');
    if (!grid) return;
    const rooms = App.rooms || [];
    const when = d => new Date(d).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    const card = document.createElement('div');
    card.className = 'card'; card.id = 'fmRecentRooms'; card.style.marginBottom = '22px';
    card.innerHTML = `<div class="section-title">${ico('clock')} Недавние подключения <span class="small muted" style="margin-left:auto;font-weight:400">хранятся в cookie этого браузера</span></div>` + (rooms.length ? `
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:12px">
        <button class="btn-gradient" data-fm-rejoin="${esc(rooms[0].id)}">${ico('video')} Подключиться снова: ${esc(String(rooms[0].topic).slice(0, 40))}</button>
        <button class="btn-ghost btn-sm" data-fm-clear>Очистить историю</button>
      </div>
      <div class="meeting-list">${rooms.map(r => `<div class="meeting-item">
        <div class="meeting-body"><h4>${esc(r.topic)}</h4><p>ID ${esc(r.id)} · ${when(r.date)} · подключений: ${r.n || 1} · ${r.host ? 'организатор' : 'участник'}${r.pw ? ' · код ' + esc(r.pw) : ''}</p></div>
        <div class="meeting-actions"><button class="btn-gradient btn-sm" data-fm-rejoin="${esc(r.id)}">${ico('video')} Войти</button><button class="btn-icon" title="Скопировать ссылку" data-fm-copy="${esc(r.id)}">${ico('copy')}</button><button class="btn-icon" title="Убрать из истории" data-fm-del="${esc(r.id)}">${ico('trash')}</button></div>
      </div>`).join('')}</div>`
      : `<div class="empty small">${ico('clock')}Подключитесь к встрече — она появится здесь, и в следующий раз хватит одной кнопки, в том числе с главной страницы сайта</div>`);
    app.insertBefore(card, grid);
    card.querySelectorAll('[data-fm-rejoin]').forEach(b => b.addEventListener('click', () => App.rejoin(b.dataset.fmRejoin)));
    card.querySelectorAll('[data-fm-copy]').forEach(b => b.addEventListener('click', () => {
      const link = `${location.origin}${location.pathname}#/rejoin/${encodeURIComponent(b.dataset.fmCopy)}`;
      navigator.clipboard ? navigator.clipboard.writeText(link).then(() => say('Ссылка скопирована', 'ok')).catch(() => say(link)) : say(link);
    }));
    card.querySelectorAll('[data-fm-del]').forEach(b => b.addEventListener('click', () => { App.rooms = App.rooms.filter(r => r.id !== b.dataset.fmDel); save(); App.route(); }));
    const cl = card.querySelector('[data-fm-clear]');
    cl && cl.addEventListener('click', () => { clearAll(); say('История подключений очищена'); App.route(); });
  };

  /* ---------- если приложение уже отрисовалось до загрузки этого скрипта — перерисовать ---------- */
  function kick() { const a = $('#app'); if (a && a.children.length) App.route(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(kick, 0));
  else setTimeout(kick, 0);
})();
