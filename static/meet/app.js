/* app.js — маршрутизация, страницы, модальные окна, уведомления */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtDate = d => d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' });
  const fmtClock = d => d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

  const App = window.App = {
    user: { name: 'Алёна', initials: 'АК', color: 'linear-gradient(135deg,#38bdf8,#8b5cf6)', email: 'alena@formyla.net', pmi: '742 019 3385' },
    settings: { micOn: true, camOn: true, mirror: true, bg: 'none', micId: null, camId: null, spkId: null, hd: true, joinAudio: true, muteOnJoin: false, camOffOnJoin: false, notifications: true, theme: 'dark', lang: 'ru', autoRecord: false, recLocal: true, dualMonitor: false, showTimer: true, alwaysCaptions: false, captionSize: 'M', reactionsSkin: 'default', hotkeysGlobal: false },
    devices: { mics: [], cams: [], speakers: [] },
    meetings: SIM.meetings.slice(), recordings: SIM.recordings.slice(), history: [], contacts: SIM.contacts.slice(),
    wbPage: null,

    /* ---------- маршрутизация ---------- */
    routes: {},
    route() {
      const hash = location.hash.replace(/^#\/?/, '') || 'home';
      const [name, ...rest] = hash.split('/');
      const arg = rest.join('/');
      document.querySelectorAll('.fm-tab').forEach(a => a.classList.toggle('active', a.dataset.route === name));
      if (this.wbPage) { this.wbPage.destroy(); this.wbPage = null; }
      const page = this.routes[name] || this.routes.home;
      $('#app').innerHTML = '';
      page.call(this, arg);
      window.scrollTo(0, 0);
    },

    init() {
      window.addEventListener('hashchange', () => this.route());
      // Имя пользователя FORMYLA.net (задаётся шаблоном: window.FM_USER = {name, email})
      if (window.FM_USER && window.FM_USER.name) { this.user.name = window.FM_USER.name; this.user.initials = SIM.initials(window.FM_USER.name); if (window.FM_USER.email) this.user.email = window.FM_USER.email; }
      $('#headerNewMeeting').addEventListener('click', () => this.newMeeting());
      this.refreshDevices();
      navigator.mediaDevices && navigator.mediaDevices.addEventListener && navigator.mediaDevices.addEventListener('devicechange', () => this.refreshDevices());
      this.route();
      setInterval(() => { const c = $('#clockTime'); if (c) { c.textContent = fmtClock(new Date()); $('#clockDate').textContent = fmtDate(new Date()); } }, 10000);
    },
    async refreshDevices() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
      try {
        const list = await navigator.mediaDevices.enumerateDevices();
        this.devices.mics = list.filter(d => d.kind === 'audioinput'); this.devices.cams = list.filter(d => d.kind === 'videoinput'); this.devices.speakers = list.filter(d => d.kind === 'audiooutput');
      } catch (e) { /* нет доступа */ }
    },
    async requestMedia() {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { toast('Браузер не поддерживает доступ к камере и микрофону', 'bad'); return false; }
      if (!window.isSecureContext) { toast('Доступ к камере возможен только по HTTPS', 'bad', 5000); return false; }
      try {
        const s = await navigator.mediaDevices.getUserMedia({ audio: true, video: true });
        s.getTracks().forEach(t => t.stop());
        await this.refreshDevices(); toast('Доступ к камере и микрофону разрешён', 'ok'); return true;
      } catch (e) {
        if (e.name === 'NotAllowedError' || e.name === 'SecurityError') toast('Доступ запрещён. Разрешите камеру и микрофон через значок замка в адресной строке', 'bad', 6000);
        else if (e.name === 'NotFoundError') toast('Камера или микрофон не найдены', 'bad');
        else toast('Не удалось получить доступ: ' + e.name, 'bad');
        return false;
      }
    },
    linkify(t) { return t.replace(/((https?:\/\/|www\.)[^\s<]+|formyla\.net[^\s<]*)/g, m => `<a href="${m.startsWith('http') ? m : 'https://' + m}" target="_blank" rel="noopener noreferrer" style="color:#7dd3fc;text-decoration:underline">${m}</a>`); },

    /* ---------- действия ---------- */
    newMeeting(opts = {}) {
      this.modal('Новая встреча', `
        <label class="field">Тема<input type="text" id="nmTopic" value="${esc(opts.topic || 'Быстрая встреча ' + App.user.name)}"></label>
        <label class="check"><input type="checkbox" id="nmPmi"> Использовать личный идентификатор (${App.user.pmi})</label>
        <label class="check"><input type="checkbox" id="nmVideo" ${App.settings.camOn ? 'checked' : ''}> Начать с включённым видео</label>
        <label class="check"><input type="checkbox" id="nmWaiting" checked> Зал ожидания</label>
        <label class="check"><input type="checkbox" id="nmPw"> Требовать код доступа</label>`,
        [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Начать встречу', cls: 'btn-gradient', act: 'ok' }], null, () => {
          App.settings.camOn = $('#nmVideo').checked;
          Meeting.open({ topic: $('#nmTopic').value.trim() || 'Встреча FORMYLA', id: $('#nmPmi').checked ? App.user.pmi : genMeetingId(), host: true, waiting: $('#nmWaiting').checked, pw: $('#nmPw').checked ? String(rnd(1000, 9999)) : '' });
        });
    },
    joinMeeting(id, topic) {
      if (!id) return;
      const m = this.meetings.find(x => x.id === id) || null;
      Meeting.open({ id: m ? m.mid || (m.mid = genMeetingId()) : String(id).replace(/(\d{3})(\d{4})(\d{4})/, '$1 $2 $3'), topic: topic || (m ? m.topic : 'Встреча ' + id), host: !!m, pw: m ? m.pw : '', waiting: m ? m.waiting : true });
    },
    profileModal() {
      this.modal('Профиль', `
        <div style="display:flex;align-items:center;gap:16px"><span class="avatar avatar-lg" style="background:${App.user.color}">${App.user.initials}</span><div><b style="font-size:18px">${esc(App.user.name)}</b><br><span class="muted small">${esc(App.user.email)}</span><br><span class="tag violet" style="margin-top:6px">Тариф FORMYLA Pro · без лимита 40 мин</span></div></div>
        <label class="field">Отображаемое имя<input type="text" id="pfName" value="${esc(App.user.name)}"></label>
        <label class="field">Личный идентификатор встречи (PMI)<input type="text" id="pfPmi" value="${App.user.pmi}"></label>
        <label class="field">Статус<select id="pfStatus"><option>В сети</option><option>Не беспокоить</option><option>Отошёл</option><option>Невидимый</option></select></label>`,
        [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Сохранить', cls: 'btn-gradient', act: 'ok' }], null, () => {
          App.user.name = $('#pfName').value.trim() || App.user.name; App.user.initials = SIM.initials(App.user.name) || 'Я'; App.user.pmi = $('#pfPmi').value.trim() || App.user.pmi;
          toast('Профиль сохранён', 'ok'); this.route();
        });
    },

    /* ---------- модальные окна и тосты ---------- */
    modal(title, body, buttons = [{ label: 'Закрыть', cls: 'btn-ghost', act: 'close' }], setup, onOk, wide) {
      const root = $('#modalRoot');
      root.classList.remove('hidden');
      root.innerHTML = `<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="modal-head"><h3>${title}</h3><button class="btn-icon" data-close>${icon('x')}</button></div><div class="modal-body">${body}</div><div class="modal-foot">${buttons.map(b => `<button class="${b.cls}" data-act="${b.act}">${b.label}</button>`).join('')}</div></div>`;
      const close = () => { root.classList.add('hidden'); root.innerHTML = ''; document.removeEventListener('keydown', onKey); };
      const onKey = e => { if (e.key === 'Escape') close(); };
      document.addEventListener('keydown', onKey);
      root.querySelector('[data-close]').addEventListener('click', close);
      root.addEventListener('pointerdown', e => { if (e.target === root) close(); });
      root.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', () => { if (b.dataset.act === 'ok') { const r = onOk && onOk(); if (r !== false) close(); } else close(); }));
      setup && setup(root.querySelector('.modal'));
      const f = root.querySelector('input, select, textarea'); f && f.focus();
      return { close };
    },

    openSettingsModal(tab) {
      this.modal('Настройки', `<div id="settingsInline"></div>`, [{ label: 'Готово', cls: 'btn-gradient', act: 'close' }], m => this.renderSettings($('#settingsInline', m), tab || 'general', true), null, true);
    },

    /* ---------- страницы ---------- */
    pages: {},
  };

  window.toast = function (msg, kind = '', ms = 3200) {
    const t = document.createElement('div'); t.className = `toast ${kind}`;
    t.innerHTML = `${icon(kind === 'ok' ? 'check' : kind === 'bad' ? 'info' : 'bell')}<span>${msg}</span>`;
    $('#toasts').appendChild(t); setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, ms);
  };

  /* ===== Главная ===== */
  App.routes.home = function () {
    const upcoming = this.meetings.filter(m => m.when > new Date(Date.now() - 3600e3)).sort((a, b) => a.when - b.when);
    $('#app').innerHTML = `
      <h1 class="page-title">Видеовстречи FORMYLA</h1>
      <p class="page-subtitle">Занятия, консультации и вебинары с HD-видео, общей доской, чатом, залами и записью — в едином стиле FORMYLA.net.</p>
      <div class="home-grid">
        <div style="display:flex;flex-direction:column;gap:22px">
          <div class="action-tiles">
            <button class="tile" data-h="new"><span class="tile-icon orange">${icon('video')}</span><span class="tile-title">Новая встреча</span><span class="tile-desc">Начать сейчас с видео и залом ожидания</span></button>
            <button class="tile" data-h="join"><span class="tile-icon blue">${icon('plus')}</span><span class="tile-title">Подключиться</span><span class="tile-desc">По идентификатору или ссылке</span></button>
            <button class="tile" data-h="schedule"><span class="tile-icon violet">${icon('calendar')}</span><span class="tile-title">Запланировать</span><span class="tile-desc">Занятие, вебинар или повторяющуюся встречу</span></button>
            <button class="tile" data-h="share"><span class="tile-icon green">${icon('monitorUp')}</span><span class="tile-title">Показать экран</span><span class="tile-desc">Быстрая демонстрация без видео</span></button>
          </div>
          <div class="card">
            <div class="section-title">${icon('calendar')} Ближайшие встречи <a href="#/meetings" class="small" style="margin-left:auto;color:#7dd3fc;font-weight:700">Все встречи →</a></div>
            <div class="meeting-list">${upcoming.length ? upcoming.slice(0, 4).map(m => this.meetingRow(m)).join('') : `<div class="empty">${icon('calendar')}Запланированных встреч нет</div>`}</div>
          </div>
          <div class="card">
            <div class="section-title">${icon('sparkles')} Что умеет FORMYLA Meet</div>
            <div class="cards-grid" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px">
              ${[['🎥', 'HD-видео до 100 участников', 'галерея и вид докладчика, закрепление и центр внимания'], ['🖥️', 'Демонстрация экрана', 'экран, окно, вкладка, звук компьютера, вторая камера'], ['🧑‍🏫', 'Интерактивная доска', 'фигуры, стикеры, текст, страницы, экспорт PNG'], ['💬', 'Чат и файлы', 'общие и личные сообщения, реакции, эмодзи'], ['🔀', 'Сессионные залы', 'авто- и ручное распределение, сообщения залам'], ['📊', 'Опросы и викторины', 'анонимные опросы, итоги в чат'], ['⏺️', 'Запись', 'локальная запись галереи со звуком'], ['🔒', 'Безопасность', 'зал ожидания, блокировка, коды, E2EE'], ['📝', 'Субтитры', 'распознавание речи на русском'], ['✋', 'Реакции и рука', 'очередь вопросов, невербальная связь']].map(([e, t, d]) => `<div style="padding:12px 14px;border-radius:12px;background:rgba(15,23,42,.6);border:1px solid var(--border-soft)"><div style="font-size:22px">${e}</div><b style="font-size:14px">${t}</b><div class="small muted">${d}</div></div>`).join('')}
            </div>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:22px">
          <div class="card clock-card"><div class="clock-time" id="clockTime">${fmtClock(new Date())}</div><div class="clock-date" id="clockDate">${fmtDate(new Date())}</div></div>
          <div class="card pmi-card">
            <div class="section-title">${icon('hash')} Личный идентификатор</div>
            <div class="pmi-id">${App.user.pmi}</div>
            <p class="small muted" style="margin:6px 0 14px">Постоянная комната для ваших занятий. Ссылку можно выдать ученикам один раз.</p>
            <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn-gradient btn-sm" data-h="pmiStart">${icon('video')} Начать</button><button class="btn-ghost btn-sm" data-h="pmiCopy">${icon('copy')} Скопировать ссылку</button></div>
            <div class="stat-row"><div class="stat"><b>${this.history.length + 12}</b><span>встреч</span></div><div class="stat"><b>${this.recordings.length}</b><span>записей</span></div><div class="stat"><b>${this.contacts.filter(c => c.status === 'online').length}</b><span>в сети</span></div></div>
          </div>
          <div class="card">
            <div class="section-title">${icon('clock')} Недавние</div>
            <div class="meeting-list">${this.history.length ? this.history.slice(0, 3).map(h => `<div class="meeting-item"><div class="meeting-body"><h4>${esc(h.topic)}</h4><p>${fmtDate(h.date)} · ${h.dur} · ${h.participants} участник(ов)</p></div><button class="btn-ghost btn-sm" data-rejoin="${esc(h.topic)}">Снова</button></div>`).join('') : `<div class="empty small">${icon('clock')}Здесь появятся завершённые встречи</div>`}</div>
          </div>
        </div>
      </div>`;
    $('#app').querySelectorAll('[data-h]').forEach(b => b.addEventListener('click', () => this.homeAction(b.dataset.h)));
    $('#app').querySelectorAll('[data-rejoin]').forEach(b => b.addEventListener('click', () => Meeting.open({ topic: b.dataset.rejoin, host: true })));
    this.bindMeetingRows();
  };
  App.homeAction = function (a) {
    if (a === 'new') this.newMeeting();
    if (a === 'join') this.joinModal();
    if (a === 'schedule') location.hash = '#/meetings/new';
    if (a === 'share') { App.settings.camOn = false; Meeting.open({ topic: 'Демонстрация экрана', host: true, waiting: false }); }
    if (a === 'pmiStart') Meeting.open({ topic: `Комната ${App.user.name}`, id: App.user.pmi, host: true });
    if (a === 'pmiCopy') { const link = `${location.origin}${location.pathname}#/join/${App.user.pmi.replace(/\s/g, '')}`; navigator.clipboard ? navigator.clipboard.writeText(link).then(() => toast('Ссылка скопирована', 'ok')).catch(() => toast(link)) : toast(link); }
  };
  App.joinModal = function (prefill = '') {
    this.modal('Подключиться к встрече', `
      <label class="field">Идентификатор встречи или ссылка<input type="text" id="jmId" value="${esc(prefill)}" placeholder="Например: 742 019 3385" inputmode="numeric"></label>
      <label class="field">Ваше имя<input type="text" id="jmName" value="${esc(App.user.name)}"></label>
      <label class="check"><input type="checkbox" id="jmMic" ${App.settings.muteOnJoin ? 'checked' : ''}> Не подключать звук</label>
      <label class="check"><input type="checkbox" id="jmCam" ${App.settings.camOffOnJoin ? 'checked' : ''}> Выключить видео</label>
      <p class="small muted">Недавние: ${this.meetings.slice(0, 2).map(m => `<a href="#" data-recent="${m.id}" style="color:#7dd3fc">${esc(m.topic.slice(0, 40))}</a>`).join(' · ')}</p>`,
      [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Подключиться', cls: 'btn-gradient', act: 'ok' }], m => {
        m.querySelectorAll('[data-recent]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); $('#jmId').value = a.dataset.recent; }));
      }, () => {
        let id = $('#jmId').value.trim(); if (!id) { toast('Введите идентификатор', 'bad'); return false; }
        const mm = id.match(/join\/(\d{9,11})/); if (mm) id = mm[1];
        App.user.name = $('#jmName').value.trim() || App.user.name; App.user.initials = SIM.initials(App.user.name) || 'Я';
        App.settings.micOn = !$('#jmMic').checked; App.settings.camOn = !$('#jmCam').checked;
        if (this.meetings.find(x => x.id === id)) this.joinMeeting(id); else { const digits = id.replace(/\D/g, ''); if (digits.length < 9) { toast('Идентификатор должен содержать 9–11 цифр', 'bad'); return false; } Meeting.open({ id: digits.replace(/(\d{3})(\d{4})(\d{3,4})/, '$1 $2 $3'), topic: 'Встреча ' + digits.slice(0, 3), host: false, waiting: true }); }
      });
  };
  App.routes.join = function (arg) { this.routes.home.call(this); if (arg) this.joinModal(arg); else this.joinModal(); };

  App.meetingRow = function (m) {
    const past = m.when < new Date();
    return `<div class="meeting-item" data-mid="${m.id}">
      <div class="meeting-time"><b>${fmtClock(m.when)}</b><span>${m.when.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span></div>
      <div class="meeting-body"><h4>${esc(m.topic)}</h4><p>${m.dur} мин · ${esc(m.host)}${m.recurring ? ' · ' + m.recurring : ''}${m.pw ? ' · код ' + m.pw : ''}${m.waiting ? ' · зал ожидания' : ''}${m.record ? ' · автозапись' : ''}${past ? ' · <span style="color:#fbbf24">идёт сейчас</span>' : ''}</p></div>
      <div class="meeting-actions"><button class="btn-gradient btn-sm" data-start="${m.id}">${icon('video')} Начать</button><button class="btn-icon" data-copy="${m.id}" title="Скопировать приглашение">${icon('copy')}</button><button class="btn-icon" data-edit="${m.id}" title="Изменить">${icon('edit')}</button><button class="btn-icon" data-del="${m.id}" title="Удалить">${icon('trash')}</button></div></div>`;
  };
  App.bindMeetingRows = function () {
    const r = $('#app');
    r.querySelectorAll('[data-start]').forEach(b => b.addEventListener('click', () => this.joinMeeting(b.dataset.start)));
    r.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => { const m = this.meetings.find(x => x.id === b.dataset.copy); const t = `${m.host} приглашает вас на встречу FORMYLA Meet\nТема: ${m.topic}\nВремя: ${fmtDate(m.when)} ${fmtClock(m.when)}\nСсылка: ${location.origin}${location.pathname}#/join/${(m.mid || (m.mid = genMeetingId())).replace(/\s/g, '')}${m.pw ? '\nКод доступа: ' + m.pw : ''}`; navigator.clipboard ? navigator.clipboard.writeText(t).then(() => toast('Приглашение скопировано', 'ok')).catch(() => toast('Не удалось скопировать', 'bad')) : toast('Буфер обмена недоступен', 'bad'); }));
    r.querySelectorAll('[data-edit]').forEach(b => b.addEventListener('click', () => this.scheduleForm(this.meetings.find(x => x.id === b.dataset.edit))));
    r.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', () => { const m = this.meetings.find(x => x.id === b.dataset.del); this.modal('Удалить встречу?', `<p>«${esc(m.topic)}» будет удалена из расписания. Участники получат уведомление об отмене.</p>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Удалить', cls: 'btn-danger', act: 'ok' }], null, () => { this.meetings = this.meetings.filter(x => x !== m); toast('Встреча удалена'); this.route(); }); }));
  };

  /* ===== Встречи ===== */
  App.routes.meetings = function (arg) {
    const tab = arg === 'new' ? 'new' : arg === 'past' ? 'past' : arg === 'pmi' ? 'pmi' : 'upcoming';
    const up = this.meetings.slice().sort((a, b) => a.when - b.when);
    let body = '';
    if (tab === 'upcoming') body = `<div class="meeting-list">${up.length ? up.map(m => this.meetingRow(m)).join('') : `<div class="empty">${icon('calendar')}Нет запланированных встреч</div>`}</div>`;
    if (tab === 'past') body = `<div class="meeting-list">${this.history.length ? this.history.map(h => `<div class="meeting-item"><div class="meeting-time"><b>${fmtClock(h.date)}</b><span>${h.date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span></div><div class="meeting-body"><h4>${esc(h.topic)}</h4><p>${h.dur} · ${h.participants} участник(ов)</p></div><div class="meeting-actions"><button class="btn-ghost btn-sm" data-again="${esc(h.topic)}">Повторить</button></div></div>`).join('') : `<div class="empty">${icon('clock')}Завершённых встреч в этой сессии пока нет</div>`}</div>`;
    if (tab === 'pmi') body = `<div class="card" style="max-width:640px"><div class="pmi-id" style="font-size:34px;font-weight:900;letter-spacing:2px">${App.user.pmi}</div><p class="muted" style="margin:8px 0 16px">Личная комната всегда доступна по одной ссылке: <code style="color:#7dd3fc">${location.origin}${location.pathname}#/join/${App.user.pmi.replace(/\s/g, '')}</code></p>
      <div class="setting-row"><div><div class="setting-title">Зал ожидания</div><div class="setting-desc">Участники ждут разрешения организатора</div></div><label class="switch"><input type="checkbox" checked><span class="track"></span></label></div>
      <div class="setting-row"><div><div class="setting-title">Код доступа</div><div class="setting-desc">Требовать код для входа в личную комнату</div></div><label class="switch"><input type="checkbox"><span class="track"></span></label></div>
      <div class="setting-row"><div><div class="setting-title">Разрешить вход до организатора</div><div class="setting-desc">Ученики могут начать без вас</div></div><label class="switch"><input type="checkbox"><span class="track"></span></label></div>
      <div style="display:flex;gap:10px;margin-top:16px"><button class="btn-gradient" id="pmiStart2">${icon('video')} Начать в личной комнате</button></div></div>`;
    $('#app').innerHTML = `
      <h1 class="page-title">Встречи</h1>
      <p class="page-subtitle">Планируйте занятия, вебинары и консультации. Повторяющиеся встречи, коды доступа, зал ожидания и автозапись.</p>
      <div class="tabs">${[['upcoming', 'Предстоящие'], ['past', 'Прошедшие'], ['pmi', 'Личная комната'], ['new', '＋ Запланировать']].map(([k, l]) => `<a href="#/meetings${k === 'upcoming' ? '' : '/' + k}" class="tab ${tab === k ? 'active' : ''}">${l}</a>`).join('')}</div>
      <div id="meetBody">${body}</div>`;
    if (tab === 'new') this.scheduleForm(null, $('#meetBody'));
    this.bindMeetingRows();
    $('#app').querySelectorAll('[data-again]').forEach(b => b.addEventListener('click', () => Meeting.open({ topic: b.dataset.again, host: true })));
    const p2 = $('#pmiStart2'); p2 && p2.addEventListener('click', () => Meeting.open({ topic: `Комната ${App.user.name}`, id: App.user.pmi, host: true }));
  };
  App.scheduleForm = function (m, inline) {
    const d = m ? m.when : new Date(Date.now() + 3600e3); d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0);
    const pad = n => String(n).padStart(2, '0');
    const html = `
      <label class="field">Тема<input type="text" id="scTopic" value="${esc(m ? m.topic : '')}" placeholder="Например: Разбор задач дня · Геометрия"></label>
      <label class="field">Описание (необязательно)<textarea id="scDesc" placeholder="Что будет на занятии, что подготовить">${esc(m && m.desc || '')}</textarea></label>
      <div class="field-row"><label class="field">Дата<input type="date" id="scDate" value="${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}"></label><label class="field">Время<input type="time" id="scTime" value="${pad(d.getHours())}:${pad(d.getMinutes())}"></label></div>
      <div class="field-row"><label class="field">Длительность, мин<select id="scDur">${[30, 45, 60, 90, 120].map(x => `<option ${(m ? m.dur : 60) === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label><label class="field">Часовой пояс<select id="scTz"><option>Europe/Moscow (GMT+3)</option><option>Europe/Sofia (GMT+3)</option><option>Europe/Berlin (GMT+2)</option><option>Asia/Almaty (GMT+5)</option></select></label></div>
      <label class="field">Повтор<select id="scRec"><option value="">Не повторять</option><option ${m && m.recurring === 'Ежедневно' ? 'selected' : ''}>Ежедневно</option><option ${m && m.recurring && m.recurring.startsWith('Еженедельно') ? 'selected' : ''}>Еженедельно</option><option>По будням</option><option>Ежемесячно</option></select></label>
      <div class="field-row">
        <label class="field">Идентификатор<select id="scId"><option value="auto">Создать автоматически</option><option value="pmi">Личный ${App.user.pmi}</option></select></label>
        <label class="field">Код доступа<input type="text" id="scPw" value="${esc(m ? m.pw : String(rnd(1000, 9999)))}" maxlength="10"></label>
      </div>
      <div style="display:grid;gap:8px">
        <label class="check"><input type="checkbox" id="scWait" ${!m || m.waiting ? 'checked' : ''}> Зал ожидания</label>
        <label class="check"><input type="checkbox" id="scVideoHost" checked> Видео организатора включено</label>
        <label class="check"><input type="checkbox" id="scVideoPart"> Видео участников включено</label>
        <label class="check"><input type="checkbox" id="scMute" checked> Выключать звук участников при входе</label>
        <label class="check"><input type="checkbox" id="scRecord" ${m && m.record ? 'checked' : ''}> Автоматически записывать встречу</label>
        <label class="check"><input type="checkbox" id="scBefore"> Разрешить вход до организатора</label>
        <label class="check"><input type="checkbox" id="scAuth"> Только для авторизованных пользователей FORMYLA.net</label>
        <label class="check"><input type="checkbox" id="scCal" checked> Добавить в Google Календарь / iCal после сохранения</label>
      </div>
      <label class="field">Альтернативные организаторы<input type="text" id="scAlt" placeholder="Электронная почта через запятую"></label>`;
    const save = () => {
      const topic = $('#scTopic').value.trim(); if (!topic) { toast('Введите тему', 'bad'); return false; }
      const when = new Date(`${$('#scDate').value}T${$('#scTime').value || '12:00'}`); if (isNaN(when)) { toast('Проверьте дату и время', 'bad'); return false; }
      const data = { topic, desc: $('#scDesc').value, when, dur: +$('#scDur').value, recurring: $('#scRec').value || null, pw: $('#scPw').value.trim(), waiting: $('#scWait').checked, record: $('#scRecord').checked, host: App.user.name };
      if (m) Object.assign(m, data); else this.meetings.push({ id: 'm' + Date.now(), mid: $('#scId').value === 'pmi' ? App.user.pmi : genMeetingId(), ...data });
      toast(m ? 'Встреча обновлена' : 'Встреча запланирована. Приглашение готово к отправке', 'ok');
      if ($('#scCal').checked) { const ics = this.makeIcs(data); const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([ics], { type: 'text/calendar' })); a.download = 'formyla-meet.ics'; a.click(); }
      location.hash = '#/meetings'; this.route();
    };
    if (inline) {
      inline.innerHTML = `<div class="card" style="max-width:760px"><div class="section-title">${icon('calendar')} Запланировать встречу</div><div class="modal-body">${html}</div><div class="modal-foot" style="justify-content:flex-start"><button class="btn-gradient" id="scSave">Сохранить</button><a href="#/meetings" class="btn-ghost">Отмена</a></div></div>`;
      $('#scSave').addEventListener('click', save);
    } else this.modal('Изменить встречу', html, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Сохранить', cls: 'btn-gradient', act: 'ok' }], null, save);
  };
  App.makeIcs = function (d) {
    const f = x => x.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    const end = new Date(d.when.getTime() + d.dur * 60000);
    return `BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//FORMYLA Meet//RU\nBEGIN:VEVENT\nUID:${Date.now()}@formyla.net\nDTSTAMP:${f(new Date())}\nDTSTART:${f(d.when)}\nDTEND:${f(end)}\nSUMMARY:${d.topic}\nDESCRIPTION:FORMYLA Meet${d.pw ? ' · Код доступа: ' + d.pw : ''}\nEND:VEVENT\nEND:VCALENDAR`;
  };

  /* ===== Записи ===== */
  App.routes.recordings = function () {
    $('#app').innerHTML = `
      <h1 class="page-title">Записи</h1>
      <p class="page-subtitle">Локальные записи встреч сохраняются в браузере на время сессии. Записи, сделанные во встрече, появляются здесь сразу после остановки.</p>
      <div class="tabs"><span class="tab active">Все записи (${this.recordings.length})</span><span class="tab">Облачные</span><span class="tab">Локальные</span><span class="tab">Транскрипты</span></div>
      <div class="rec-grid">${this.recordings.map(r => `<div class="card rec-card" data-rid="${r.id}">
        ${r.src ? `<video src="${r.src}" controls preload="metadata"></video>` : `<div style="aspect-ratio:16/9;border-radius:12px;display:grid;place-items:center;background:linear-gradient(135deg,#172033,#0b1220);color:#94a3b8;font-weight:700;gap:6px">${icon('play')}<span class="small">Демо-запись</span></div>`}
        <div class="rec-meta"><div><b style="font-size:15px">${esc(r.topic)}</b><div class="small muted">${fmtDate(r.date)} · ${r.dur} · ${r.size}</div></div><div style="display:flex;gap:4px">${r.src ? `<a class="btn-icon" href="${r.src}" download="formyla-meet-${r.id}.webm" title="Скачать">${icon('download')}</a><a class="btn-icon" href="${r.src}" target="_blank" rel="noopener" title="Открыть в новой вкладке">${icon('maximize')}</a>` : ''}<button class="btn-icon" data-share="${r.id}" title="Поделиться ссылкой">${icon('link')}</button><button class="btn-icon" data-delrec="${r.id}" title="Удалить">${icon('trash')}</button></div></div>
        </div>`).join('')}
        ${this.recordings.length ? '' : `<div class="empty">${icon('record')}Записей пока нет</div>`}
      </div>`;
    $('#app').querySelectorAll('[data-delrec]').forEach(b => b.addEventListener('click', () => { const r = this.recordings.find(x => x.id === b.dataset.delrec); if (r && r.src) URL.revokeObjectURL(r.src); this.recordings = this.recordings.filter(x => x !== r); toast('Запись удалена'); this.route(); }));
    $('#app').querySelectorAll('[data-share]').forEach(b => b.addEventListener('click', () => toast('Ссылка на запись с кодом доступа скопирована (демо)', 'ok')));
  };

  /* ===== Контакты ===== */
  App.routes.contacts = function () {
    const st = { online: 'В сети', away: 'Отошёл', busy: 'Не беспокоить', offline: 'Не в сети' };
    $('#app').innerHTML = `
      <h1 class="page-title">Контакты</h1>
      <p class="page-subtitle">Ученики, преподаватели и родители. Позвоните напрямую или пригласите во встречу.</p>
      <div style="display:flex;gap:10px;align-items:center;margin-bottom:18px;flex-wrap:wrap"><div style="flex:1;min-width:220px;position:relative">${icon('search', 'muted')}<input type="search" id="cSearch" placeholder="Поиск по имени или роли" style="padding-left:40px"><span style="position:absolute;left:12px;top:12px;width:18px;height:18px;color:#94a3b8">${icon('search')}</span></div><button class="btn-ghost" id="cAdd">${icon('plus')} Добавить контакт</button><button class="btn-gradient" id="cGroup">${icon('users')} Групповой звонок</button></div>
      <div class="tabs">${['Все', 'В сети', 'Ученики', 'Преподаватели', 'Родители'].map((l, i) => `<button class="tab ${i === 0 ? 'active' : ''}" data-f="${l}">${l}</button>`).join('')}</div>
      <div class="contact-grid" id="cGrid"></div>`;
    const grid = $('#cGrid'); let filter = 'Все', q = '';
    const render = () => {
      const list = this.contacts.filter(c => (filter === 'Все' || (filter === 'В сети' && c.status === 'online') || (filter === 'Ученики' && /Учени/.test(c.role)) || (filter === 'Преподаватели' && /Преподав|Куратор|Методист/.test(c.role)) || (filter === 'Родители' && /Родител/.test(c.role))) && (c.name + c.role).toLowerCase().includes(q));
      grid.innerHTML = list.map(c => `<div class="contact"><span class="avatar" style="background:${c.color}">${c.initials}</span><div style="flex:1;min-width:0"><div class="name">${esc(c.name)}</div><div class="role"><span class="status-dot ${c.status}"></span>${st[c.status]} · ${esc(c.role)}</div></div><button class="btn-icon" data-call="${c.id}" title="Позвонить">${icon('video')}</button><button class="btn-icon" data-msg="${c.id}" title="Сообщение">${icon('chat')}</button></div>`).join('') || `<div class="empty">${icon('users')}Никого не найдено</div>`;
      grid.querySelectorAll('[data-call]').forEach(b => b.addEventListener('click', () => { const c = this.contacts.find(x => x.id === b.dataset.call); toast(`Звоним ${c.name}…`); setTimeout(() => Meeting.open({ topic: `Звонок: ${c.name}`, host: true, waiting: false }), 900); }));
      grid.querySelectorAll('[data-msg]').forEach(b => b.addEventListener('click', () => { const c = this.contacts.find(x => x.id === b.dataset.msg); this.modal(`Сообщение для ${esc(c.name)}`, `<textarea id="dmText" placeholder="Напишите сообщение…"></textarea>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Отправить', cls: 'btn-gradient', act: 'ok' }], null, () => { if (!$('#dmText').value.trim()) return false; toast(`Сообщение отправлено ${c.name}`, 'ok'); }); }));
    };
    render();
    $('#cSearch').addEventListener('input', e => { q = e.target.value.toLowerCase(); render(); });
    $('#app').querySelectorAll('[data-f]').forEach(b => b.addEventListener('click', () => { filter = b.dataset.f; $('#app').querySelectorAll('[data-f]').forEach(x => x.classList.toggle('active', x === b)); render(); }));
    $('#cAdd').addEventListener('click', () => this.modal('Новый контакт', `<label class="field">Имя<input type="text" id="ncName"></label><label class="field">Роль<input type="text" id="ncRole" placeholder="Ученик · 9 класс"></label><label class="field">Электронная почта<input type="text" id="ncMail"></label>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Добавить', cls: 'btn-gradient', act: 'ok' }], null, () => { const n = $('#ncName').value.trim(); if (!n) return false; const i = this.contacts.length; this.contacts.push({ id: 'c' + Date.now(), name: n, role: $('#ncRole').value.trim() || 'Контакт', status: 'offline', initials: SIM.initials(n), color: SIM.palette[i % 8], solid: SIM.solid[i % 8] }); toast('Контакт добавлен', 'ok'); render(); }));
    $('#cGroup').addEventListener('click', () => this.modal('Групповой звонок', `<p class="muted small">Выберите участников:</p><div style="display:grid;gap:6px;max-height:300px;overflow:auto">${this.contacts.map(c => `<label class="check"><input type="checkbox" value="${c.id}" ${c.status === 'online' ? 'checked' : ''}> <span class="avatar avatar-sm" style="background:${c.color}">${c.initials}</span> ${esc(c.name)}</label>`).join('')}</div>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Позвонить', cls: 'btn-gradient', act: 'ok' }], null, () => { Meeting.open({ topic: 'Групповой звонок', host: true, waiting: false }); }));
  };

  /* ===== Доска (отдельная страница) ===== */
  App.routes.whiteboard = function () {
    $('#app').innerHTML = `
      <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:14px;flex-wrap:wrap"><div><h1 class="page-title" style="font-size:34px;margin:0">Доска</h1><p class="muted">Перо, фигуры, стрелки, текст, стикеры, страницы, масштаб, экспорт. Ту же доску можно открыть во встрече кнопкой «Доска».</p></div><button class="btn-gradient" id="wbStart">${icon('video')} Начать встречу с этой доской</button></div>
      <div class="wb-page" id="wbHost"></div>`;
    this.wbPage = new Whiteboard($('#wbHost'), { title: 'Моя доска' });
    $('#wbStart').addEventListener('click', () => { const pages = this.wbPage.pages; Meeting.open({ topic: 'Занятие у доски', host: true, waiting: false }); const w = setInterval(() => { if (Meeting.S && Meeting.S.joined) { clearInterval(w); Meeting.S.wb = { pages, page: 0, title: 'Моя доска', bg: 'dots', destroy() { } }; Meeting.toggleWhiteboard(true); } }, 500); setTimeout(() => clearInterval(w), 120000); });
  };

  /* ===== Настройки ===== */
  App.routes.settings = function (arg) {
    $('#app').innerHTML = `<h1 class="page-title">Настройки</h1><p class="page-subtitle">Устройства, видео, звук, фон, запись, горячие клавиши и доступность.</p><div id="settingsPage"></div>`;
    this.renderSettings($('#settingsPage'), arg || 'general');
  };
  App.renderSettings = function (root, tab, compact) {
    const S = this.settings;
    const sections = [['general', 'settings', 'Общие'], ['video', 'video', 'Видео'], ['audio', 'mic', 'Звук'], ['bg', 'sparkles', 'Фон и эффекты'], ['share', 'monitor', 'Демонстрация'], ['record', 'record', 'Запись'], ['keys', 'keyboard', 'Горячие клавиши'], ['access', 'captions', 'Доступность'], ['stats', 'wifi', 'Статистика']];
    const sw = (k, t, d) => `<div class="setting-row"><div><div class="setting-title">${t}</div>${d ? `<div class="setting-desc">${d}</div>` : ''}</div><label class="switch"><input type="checkbox" data-set="${k}" ${S[k] ? 'checked' : ''}><span class="track"></span></label></div>`;
    const sel = (k, t, opts) => `<div class="setting-row"><div class="setting-title">${t}</div><select data-set="${k}" style="width:auto;min-width:200px">${opts.map(([v, l]) => `<option value="${v}" ${S[k] == v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>`;
    const dev = (k, t, arr) => `<div class="setting-row"><div class="setting-title">${t}</div><select data-set="${k}" style="width:auto;min-width:220px">${arr.length ? arr.map(x => `<option value="${x.deviceId}" ${S[k] === x.deviceId ? 'selected' : ''}>${esc(x.label || 'Устройство')}</option>`).join('') : '<option value="">Разрешите доступ, чтобы увидеть устройства</option>'}</select></div>`;
    const noLabels = !(this.devices.cams.some(d => d.label) || this.devices.mics.some(d => d.label));
    const perm = noLabels ? `<div class="perm-box" style="margin-bottom:12px">${icon('shield')}<div><b>Нужен доступ к камере и микрофону</b><div class="small muted">Разрешите доступ, чтобы выбрать устройства и проверить их. Браузер покажет запрос один раз.</div><div class="perm-actions"><button class="btn-gradient btn-sm" data-act="askPerm">${icon('mic')} Разрешить доступ</button></div></div></div>` : '';
    const content = {
      general: sw('joinAudio', 'Автоматически подключать звук компьютера') + sw('muteOnJoin', 'Выключать мой микрофон при входе') + sw('camOffOnJoin', 'Выключать моё видео при входе') + sw('notifications', 'Уведомления о начале встреч', 'Напоминание за 5 минут') + sw('showTimer', 'Показывать длительность встречи') + sw('dualMonitor', 'Режим двух мониторов') + sel('theme', 'Тема', [['dark', 'Тёмная (FORMYLA)'], ['auto', 'Как в системе']]) + sel('lang', 'Язык', [['ru', 'Русский'], ['en', 'English'], ['bg', 'Български']]),
      video: perm + dev('camId', 'Камера', this.devices.cams) + sw('mirror', 'Зеркальное отображение моего видео') + sw('hd', 'HD-видео (720p)', 'Требует больше трафика') + sw('camOffOnJoin', 'Выключать видео при входе') + `<div class="setting-row"><div class="setting-title">Предпросмотр</div><button class="btn-ghost btn-sm" data-act="camTest">${icon('video')} Проверить камеру</button></div>`,
      audio: perm + dev('micId', 'Микрофон', this.devices.mics) + dev('spkId', 'Динамики', this.devices.speakers) + sw('joinAudio', 'Подключать звук компьютера автоматически') + sw('muteOnJoin', 'Выключать микрофон при входе') + `<div class="setting-row"><div><div class="setting-title">Подавление фонового шума</div><div class="setting-desc">Автоматически, на основе noiseSuppression</div></div><select style="width:auto"><option>Авто</option><option>Слабое</option><option>Среднее</option><option>Сильное</option></select></div>` + `<div class="setting-row"><div class="setting-title">Проверка</div><button class="btn-ghost btn-sm" data-act="micTest">${icon('volume')} Проверить микрофон и динамики</button></div>`,
      bg: `<p class="muted small" style="margin-bottom:10px">Выбранный фон применяется к вашему видео во всех встречах.</p><div class="cards-grid" style="grid-template-columns:repeat(3,1fr)">${[['none', 'Без фона', 'linear-gradient(135deg,#1e293b,#0f172a)'], ['blur', 'Размытие', 'linear-gradient(135deg,#334155,#64748b)'], ['soft', 'Мягкий свет', 'linear-gradient(135deg,#fbbf24,#f472b6)'], ['formyla', 'FORMYLA', 'radial-gradient(circle at 30% 30%,rgba(56,189,248,.5),transparent 50%),radial-gradient(circle at 70% 70%,rgba(139,92,246,.5),transparent 50%),#0f172a'], ['board', 'Аудитория', 'linear-gradient(180deg,#1e3a5f,#0b1220)'], ['geo', 'Геометрия', 'repeating-linear-gradient(45deg,#1e293b 0 10px,#0f172a 10px 20px)']].map(([k, l, bg]) => `<button class="tile" data-bgset="${k}" style="padding:10px;gap:8px;${S.bg === k ? 'border-color:#8b5cf6' : ''}"><span style="display:block;width:100%;aspect-ratio:16/9;border-radius:10px;background:${bg}"></span><span class="tile-title" style="font-size:13px">${l}</span></button>`).join('')}</div>` + sw('reactionsSkin', 'Анимированные реакции', 'Показывать эмодзи поверх видео'),
      share: sw('allowShareSound', 'Передавать звук компьютера при демонстрации') + sw('optimizeVideo', 'Оптимизировать для видеоклипов') + sw('shareSideBySide', 'Режим «рядом»: экран и участники') + sw('shareWbAuto', 'Открывать доску в полноэкранном режиме') + sel('shareWindowMode', 'При демонстрации окна', [['fit', 'Подгонять под окно'], ['orig', 'Исходный размер']]),
      record: sw('autoRecord', 'Автоматически записывать встречи, которые я организую') + sw('recLocal', 'Локальная запись (WebM)', 'Сохраняется в браузере, доступна в разделе «Записи»') + sw('recAudioSeparate', 'Отдельная аудиодорожка каждого участника') + sw('recTimestamp', 'Добавлять метку времени в запись') + sw('recNames', 'Показывать имена участников') + sw('recChat', 'Сохранять чат вместе с записью'),
      keys: `<ul style="display:grid;gap:6px;font-size:14px">${[['Alt + A', 'Микрофон вкл/выкл'], ['Alt + V', 'Видео вкл/выкл'], ['Пробел (удерж.)', 'Временно включить микрофон'], ['Alt + S', 'Демонстрация экрана'], ['Alt + R', 'Запись'], ['Alt + H', 'Чат'], ['Alt + U', 'Участники'], ['Alt + Y', 'Поднять руку'], ['Alt + W', 'Доска'], ['Alt + C', 'Субтитры'], ['Alt + F', 'Полный экран'], ['Esc', 'Закрыть панели']].map(([k, v]) => `<li style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border-soft)"><span>${v}</span><kbd style="font-family:inherit;font-weight:800;background:rgba(255,255,255,.08);padding:2px 8px;border-radius:6px">${k}</kbd></li>`).join('')}</ul>` + sw('hotkeysGlobal', 'Глобальные горячие клавиши', 'Работают, даже когда окно не в фокусе'),
      access: sw('alwaysCaptions', 'Всегда включать субтитры') + sel('captionSize', 'Размер субтитров', [['S', 'Маленький'], ['M', 'Средний'], ['L', 'Крупный']]) + sw('screenReader', 'Оповещения для программ чтения с экрана') + sw('highContrast', 'Высокая контрастность') + sw('reduceMotion', 'Уменьшить анимацию'),
      stats: `<div class="stat-row" style="margin-top:0"><div class="stat"><b>${(navigator.hardwareConcurrency || 4)} ядер</b><span>Процессор</span></div><div class="stat"><b>${navigator.deviceMemory ? navigator.deviceMemory + ' ГБ' : '—'}</b><span>Память</span></div><div class="stat"><b>${(navigator.connection && navigator.connection.effectiveType) || 'wifi'}</b><span>Сеть</span></div></div><div class="stat-row"><div class="stat"><b>${this.devices.cams.length}</b><span>Камер</span></div><div class="stat"><b>${this.devices.mics.length}</b><span>Микрофонов</span></div><div class="stat"><b>${this.devices.speakers.length}</b><span>Динамиков</span></div></div><p class="small muted" style="margin-top:12px">Браузер: ${esc(navigator.userAgent.split(') ').pop() || '')}</p>`,
    };
    root.innerHTML = `<div class="settings-layout ${compact ? 'compact' : ''}" style="${compact ? 'grid-template-columns:200px 1fr' : ''}"><nav class="settings-nav">${sections.map(([k, i, l]) => `<button data-tab="${k}" class="${tab === k ? 'active' : ''}">${icon(i)} ${l}</button>`).join('')}</nav><div class="card" id="setBody">${content[tab] || content.general}</div></div>`;
    root.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { if (compact) this.renderSettings(root, b.dataset.tab, true); else location.hash = '#/settings/' + b.dataset.tab; }));
    root.querySelectorAll('[data-set]').forEach(el => el.addEventListener('change', () => { S[el.dataset.set] = el.type === 'checkbox' ? el.checked : el.value; if (el.dataset.set === 'mirror' && Meeting.S) { Meeting.S.mirror = S.mirror; Meeting.attachSelf(); } if ((el.dataset.set === 'camId' || el.dataset.set === 'micId') && Meeting.S) Meeting.getMedia(); toast('Сохранено', 'ok', 1200); }));
    root.querySelectorAll('[data-bgset]').forEach(b => b.addEventListener('click', () => { S.bg = b.dataset.bgset; root.querySelectorAll('[data-bgset]').forEach(x => x.style.borderColor = x === b ? '#8b5cf6' : ''); if (Meeting.S) { Meeting.S.bg = S.bg; Meeting.attachSelf(); Meeting.applyFrameBg(); } toast('Фон сохранён', 'ok', 1200); }));
    const ap = root.querySelector('[data-act=askPerm]'); ap && ap.addEventListener('click', () => this.requestMedia().then(ok => { if (ok) this.renderSettings(root, tab, compact); }));
    const ct = root.querySelector('[data-act=camTest]'); ct && ct.addEventListener('click', async () => {
      try { const s = await navigator.mediaDevices.getUserMedia({ video: true }); this.modal('Проверка камеры', `<div class="preview-box" id="camPrev"></div>`, [{ label: 'Закрыть', cls: 'btn-gradient', act: 'close' }], m => { const v = document.createElement('video'); v.autoplay = true; v.muted = true; v.playsInline = true; v.srcObject = s; $('#camPrev', m).appendChild(v); if (S.mirror) v.style.transform = 'scaleX(-1)'; }); this.refreshDevices(); const obs = new MutationObserver(() => { if ($('#modalRoot').classList.contains('hidden')) { s.getTracks().forEach(t => t.stop()); obs.disconnect(); } }); obs.observe($('#modalRoot'), { attributes: true }); } catch (e) { toast('Камера недоступна: ' + e.name, 'bad'); }
    });
    const mt = root.querySelector('[data-act=micTest]'); mt && mt.addEventListener('click', async () => {
      try {
        const s = await navigator.mediaDevices.getUserMedia({ audio: true }); this.refreshDevices();
        const ctx = new (window.AudioContext || window.webkitAudioContext)(); const an = ctx.createAnalyser(); ctx.createMediaStreamSource(s).connect(an); const data = new Uint8Array(an.frequencyBinCount);
        this.modal('Проверка микрофона', `<p class="muted small">Скажите что-нибудь — индикатор должен двигаться.</p><div class="level-meter" style="height:12px"><i id="micLvl"></i></div><button class="btn-ghost btn-sm" id="spkTest" style="margin-top:8px">${icon('volume')} Проверить динамики</button>`, [{ label: 'Закрыть', cls: 'btn-gradient', act: 'close' }], m => { $('#spkTest', m).addEventListener('click', () => Meeting.testAudio()); });
        const tick = () => { if ($('#modalRoot').classList.contains('hidden')) { s.getTracks().forEach(t => t.stop()); ctx.close(); return; } an.getByteFrequencyData(data); const l = data.reduce((a, b) => a + b, 0) / data.length / 128; const el = $('#micLvl'); if (el) el.style.width = Math.min(100, l * 100) + '%'; requestAnimationFrame(tick); }; tick();
      } catch (e) { toast('Микрофон недоступен: ' + e.name, 'bad'); }
    });
  };

  App.init();
})();
