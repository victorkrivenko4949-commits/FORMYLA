/* meeting.js — комната видеовстречи: предпросмотр, сетка, панель инструментов, боковые панели, доска, запись */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtTime = s => `${String(Math.floor(s / 3600)).padStart(2, '0')}:${String(Math.floor(s % 3600 / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  const now = () => new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

  const M = {
    layer: null, S: null, selfVideo: null, shareVideo: null, timers: [],

    /* =============== ВХОД =============== */
    async open(opts) {
      this.layer = $('#meetingLayer');
      this.layer.classList.remove('hidden');
      document.body.classList.add('in-meeting');
      const user = App.user;
      this.S = {
        id: opts.id || genMeetingId(), topic: opts.topic || 'Встреча FORMYLA', pw: opts.pw || '', isHost: opts.host !== false,
        name: user.name, mic: App.settings.micOn, cam: App.settings.camOn, joined: false, secs: 0,
        view: 'gallery', panel: null, pinned: null, spotlight: null, hand: false,
        sharing: null, wbShared: false, recording: false, recPaused: false, captions: false, captionText: '',
        locked: false, waitingRoom: opts.waiting !== false, allowShare: true, allowChat: true, allowRename: true, allowUnmute: true, muteOnEntry: false,
        participants: [], waiting: [], chat: [], polls: [], rooms: [], chatTo: 'all', unread: 0,
        bg: App.settings.bg || 'none', mirror: App.settings.mirror !== false, hd: true, noise: true,
        stream: null, displayStream: null, recorder: null, recChunks: [], wb: null, activePop: null, ended: false,
      };
      this.renderPrejoin();
      await this.getMedia();
    },

    async getMedia() {
      const S = this.S;
      try {
        if (S.stream) S.stream.getTracks().forEach(t => t.stop());
        const constraints = { video: S.cam ? { width: { ideal: S.hd ? 1280 : 640 }, height: { ideal: S.hd ? 720 : 360 }, deviceId: App.settings.camId ? { exact: App.settings.camId } : undefined } : false, audio: S.mic || !S.joined ? { echoCancellation: true, noiseSuppression: S.noise, deviceId: App.settings.micId ? { exact: App.settings.micId } : undefined } : false };
        if (!constraints.video && !constraints.audio) { S.stream = null; this.attachSelf(); return; }
        S.stream = await navigator.mediaDevices.getUserMedia(constraints);
        S.mediaError = null; S.permState = 'granted';
        this.attachSelf(); this.renderPermBox();
        this.startLevelMeter();
        App.refreshDevices && App.refreshDevices();
      } catch (e) {
        S.stream = null; S.mediaError = e.name; S.permState = (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? 'denied' : 'error';
        this.attachSelf(); this.renderPermBox();
        if (e.name === 'NotFoundError') toast('Камера или микрофон не найдены', 'bad');
      }
    },

    attachSelf() {
      const S = this.S;
      if (!this.selfVideo) { this.selfVideo = document.createElement('video'); this.selfVideo.autoplay = true; this.selfVideo.muted = true; this.selfVideo.playsInline = true; }
      const v = this.selfVideo;
      const hasVideo = S.stream && S.stream.getVideoTracks().length && S.cam;
      v.srcObject = hasVideo ? S.stream : null;
      v.classList.toggle('mirror', S.mirror);
      v.style.filter = S.bg === 'blur' ? 'blur(6px) saturate(1.1)' : S.bg === 'soft' ? 'brightness(1.05) contrast(1.05)' : '';
      const holders = this.layer.querySelectorAll('[data-self-video]');
      holders.forEach(h => { h.innerHTML = ''; if (hasVideo) h.appendChild(v); else h.innerHTML = `<div class="avatar-wrap"><span class="avatar avatar-lg" style="background:${App.user.color}">${App.user.initials}</span></div>`; });
      const pv = $('.preview-box', this.layer);
      if (pv) { $('.preview-off', pv) && $('.preview-off', pv).classList.toggle('hidden', !!hasVideo); }
      if (S.stream) S.stream.getAudioTracks().forEach(t => t.enabled = S.mic);
    },

    startLevelMeter() {
      const S = this.S; if (!S.stream || !S.stream.getAudioTracks().length) return;
      try {
        S.audioCtx && S.audioCtx.close();
        S.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const src = S.audioCtx.createMediaStreamSource(S.stream); const an = S.audioCtx.createAnalyser(); an.fftSize = 256; src.connect(an);
        const data = new Uint8Array(an.frequencyBinCount);
        const tick = () => {
          if (!S.stream || this.S !== S) return;
          an.getByteFrequencyData(data); const lvl = data.reduce((a, b) => a + b, 0) / data.length / 128;
          const m = this.layer.querySelector('.level-meter i'); if (m) m.style.width = Math.min(100, lvl * 100) + '%';
          const me = this.layer.querySelector('.tile-v[data-id=me]'); if (me) me.classList.toggle('speaking', S.mic && lvl > 0.18);
          requestAnimationFrame(tick);
        }; tick();
      } catch (e) { /* без индикатора */ }
    },

    renderPrejoin() {
      const S = this.S;
      this.layer.innerHTML = `
        <div class="room-top"><div class="left"><span class="room-title">${icon('shield')} ${esc(S.topic)}</span><span class="tag">ID ${S.id}</span></div>
        <div class="right"><button class="btn-ghost btn-sm" data-a="cancel">${icon('x')} Отмена</button></div></div>
        <div class="prejoin">
          <div class="preview-box">
            <div data-self-video style="position:absolute;inset:0"></div>
            <div class="preview-off"><span class="avatar avatar-xl" style="background:${App.user.color}">${App.user.initials}</span><span>Камера выключена</span></div>
            <div class="preview-controls">
              <button class="tool ${S.mic ? '' : 'off'}" data-a="mic">${icon(S.mic ? 'mic' : 'micOff')}<span class="lbl">${S.mic ? 'Микрофон' : 'Вкл. микрофон'}</span></button>
              <button class="tool ${S.cam ? '' : 'off'}" data-a="cam">${icon(S.cam ? 'video' : 'videoOff')}<span class="lbl">${S.cam ? 'Камера' : 'Вкл. камеру'}</span></button>
              <button class="tool" data-a="bg">${icon('sparkles')}<span class="lbl">Фон</span></button>
            </div>
          </div>
          <div class="prejoin-form">
            <h2>Готовы подключиться?</h2>
            <p class="muted">${S.isHost ? 'Вы организатор этой встречи. Участники ' + (S.waitingRoom ? 'будут ждать вашего разрешения в зале ожидания.' : 'подключаются сразу.') : 'Организатор: Мария Иванова. Никто больше не подключился — вы первые.'}</p>
            <div class="form-stack">
              <div id="permBox"></div>
              <label class="field">Ваше имя<input type="text" id="pjName" value="${esc(S.name)}" maxlength="40"></label>
              ${S.pw && !S.isHost ? `<label class="field">Код доступа<input type="password" id="pjPw" placeholder="Введите код"></label>` : ''}
              <div><div class="small muted" style="margin-bottom:6px">Уровень микрофона</div><div class="level-meter"><i></i></div></div>
              <label class="check"><input type="checkbox" id="pjRemember" checked> Запомнить настройки микрофона и камеры</label>
              <label class="check"><input type="checkbox" id="pjAudio" checked> Подключиться со звуком компьютера</label>
              <div style="display:flex;gap:10px;flex-wrap:wrap">
                <button class="btn-gradient" data-a="join" style="padding:13px 30px;font-size:15px">${S.isHost ? 'Начать встречу' : 'Подключиться'}</button>
                <button class="btn-ghost" data-a="copy">${icon('copy')} Скопировать приглашение</button>
              </div>
            </div>
          </div>
        </div>`;
      this.attachSelf();
      this.layer.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', () => this.prejoinAction(b.dataset.a)));
      this.renderPermBox();
    },

    /* ---------- Разрешения на камеру и микрофон ---------- */
    inFrame() { try { return window.self !== window.top; } catch (e) { return true; } },
    async queryPermissions() {
      if (!navigator.permissions || !navigator.permissions.query) return null;
      try {
        const [c, m] = await Promise.all([navigator.permissions.query({ name: 'camera' }), navigator.permissions.query({ name: 'microphone' })]);
        return { camera: c.state, microphone: m.state };
      } catch (e) { return null; }
    },
    async requestPermissions() {
      const S = this.S;
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) { toast('Браузер не поддерживает доступ к камере и микрофону', 'bad'); return; }
      if (!window.isSecureContext) { toast('Доступ к камере возможен только по HTTPS', 'bad', 5000); return; }
      toast('Разрешите доступ в окне браузера', 'info', 3000);
      await this.getMedia();
      if (S.permState === 'granted') toast('Доступ к камере и микрофону разрешён', 'ok');
    },
    async renderPermBox() {
      const S = this.S; const box = this.layer && this.layer.querySelector('#permBox'); if (!box) return;
      const perm = await this.queryPermissions();
      const granted = S.permState === 'granted' || (perm && perm.camera === 'granted' && perm.microphone === 'granted' && S.stream);
      const denied = S.permState === 'denied' || (perm && (perm.camera === 'denied' || perm.microphone === 'denied'));
      const frame = this.inFrame();
      if (granted) {
        box.innerHTML = `<div class="perm-box ok">${icon('check')}<div><b>Камера и микрофон подключены</b><div class="small muted">Доступ разрешён. Устройства можно сменить в настройках микрофона и камеры.</div></div></div>`;
        return;
      }
      const why = !window.isSecureContext ? 'Страница открыта не по HTTPS — браузер не даст доступ к устройствам.' : denied ? 'Браузер заблокировал доступ. Нажмите на значок замка или камеры в адресной строке, разрешите камеру и микрофон и нажмите «Запросить снова».' : S.permState === 'error' ? 'Не удалось запустить камеру или микрофон: устройство не найдено или занято другим приложением.' : 'Нажмите «Разрешить доступ» и подтвердите запрос браузера — иначе участники не увидят и не услышат вас.';
      box.innerHTML = `<div class="perm-box ${denied ? 'bad' : ''}">${icon(denied ? 'videoOff' : 'shield')}<div><b>${denied ? 'Доступ к камере и микрофону запрещён' : 'Нужен доступ к камере и микрофону'}</b><div class="small muted">${why}${frame ? ' Приложение открыто во встроенном окне: если запрос не появляется, откройте его в отдельной вкладке.' : ''}</div>
        <div class="perm-actions"><button class="btn-gradient btn-sm" data-p="ask">${icon('mic')} ${denied ? 'Запросить снова' : 'Разрешить доступ'}</button>${frame ? `<button class="btn-ghost btn-sm" data-p="tab">${icon('maximize')} Открыть в отдельной вкладке</button>` : ''}<button class="btn-ghost btn-sm" data-p="skip">Продолжить без камеры</button></div></div></div>`;
      box.querySelector('[data-p="ask"]').onclick = () => this.requestPermissions();
      const t = box.querySelector('[data-p="tab"]'); if (t) t.onclick = () => window.open(location.href, '_blank', 'noopener');
      box.querySelector('[data-p="skip"]').onclick = () => { S.cam = false; S.mic = false; box.innerHTML = ''; this.renderPrejoin(); };
    },
    prejoinAction(a) {
      const S = this.S;
      if (a === 'cancel') return this.close();
      if (a === 'mic') { S.mic = !S.mic; this.renderPrejoin(); this.attachSelf(); if (S.stream) this.startLevelMeter(); }
      if (a === 'cam') { S.cam = !S.cam; this.getMedia().then(() => this.renderPrejoin()); }
      if (a === 'bg') this.bgModal();
      if (a === 'copy') this.copyInvite();
      if (a === 'join') {
        const n = $('#pjName').value.trim(); if (!n) return toast('Введите имя', 'bad');
        const pw = $('#pjPw'); if (pw && S.pw && pw.value !== S.pw) return toast('Неверный код доступа', 'bad');
        S.name = n; App.user.name = n; App.user.initials = SIM.initials(n) || 'Я';
        if ($('#pjRemember').checked) { App.settings.micOn = S.mic; App.settings.camOn = S.cam; }
        this.join();
      }
    },

    /* =============== КОМНАТА =============== */
    join() {
      const S = this.S; S.joined = true;
      S.participants = SIM.makeParticipants(5);
      S.participants[0].host = !S.isHost; S.participants[0].cohost = S.isHost;
      S.chat.push({ sys: true, text: `Вы подключились к встрече · ${now()}` });
      this.renderRoom();
      this.timers.push(setInterval(() => { S.secs++; const t = $('.room-timer', this.layer); if (t) t.textContent = fmtTime(S.secs); }, 1000));
      this.startSimulation();
      toast(`Вы в встрече «${S.topic}»`, 'ok');
      if (S.muteOnEntry) S.participants.forEach(p => p.mic = false);
    },

    renderRoom() {
      const S = this.S;
      this.layer.innerHTML = `
        <div class="room">
          <div class="room-top">
            <div class="left">
              <span class="room-title"><span class="shield" title="Сквозное шифрование включено">${icon('shield')}</span>${esc(S.topic)}</span>
              <button class="btn-icon" data-a="info" title="Информация о встрече">${icon('info')}</button>
              <span class="room-timer">${fmtTime(S.secs)}</span>
              <span class="rec-badge ${S.recording ? '' : 'hidden'}" id="recBadge"><i></i> ${S.recPaused ? 'ПАУЗА' : 'ЗАПИСЬ'}</span>
            </div>
            <div class="right">
              <div class="view-switch">
                <button class="${S.view === 'gallery' ? 'active' : ''}" data-a="view:gallery">${icon('grid')} Галерея</button>
                <button class="${S.view === 'speaker' ? 'active' : ''}" data-a="view:speaker">${icon('speaker')} Докладчик</button>
              </div>
              <button class="btn-icon" data-a="fullscreen" title="Полный экран">${icon('maximize')}</button>
              <button class="btn-icon fm-mini-open" data-a="minimize" title="Вернуться на FORMYLA — звонок продолжится в мини-окне">🏠</button>
            </div>
          </div>
          <div class="room-body">
            <div class="stage" id="stage"></div>
            <aside class="side-panel ${S.panel ? '' : 'hidden'}" id="sidePanel"></aside>
          </div>
          <div class="toolbar" id="toolbar"></div>
          <!-- MINI_MODE_V1: полоса управления в мини-окне -->
          <div class="mini-bar ${S.mini ? '' : 'hidden'}" id="miniBar">
            <span class="mini-title">${esc(S.topic)}</span>
            <button class="btn-icon" data-mb="mic" title="Микрофон">${icon(S.mic ? 'mic' : 'micOff')}</button>
            <button class="btn-icon" data-mb="expand" title="Развернуть встречу">${icon('maximize')}</button>
            <button class="btn-icon" data-mb="close" title="Покинуть встречу">${icon('x')}</button>
          </div>
        </div>`;
      this.renderStage(); this.renderToolbar(); this.renderPanel();
      // MINI_MODE_V1: после перерисовки комнаты восстанавливаем мини-режим
      if (S.mini) { this.layer.classList.add('mini-mode'); document.body.classList.remove('in-meeting'); }
      this.layer.querySelectorAll('.room-top [data-a]').forEach(b => b.addEventListener('click', () => this.action(b.dataset.a)));
      this.layer.querySelectorAll('#miniBar [data-mb]').forEach(b => b.addEventListener('click', e => {
        e.stopPropagation();
        const a = b.dataset.mb;
        if (a === 'expand') this.toggleMini(false);
        else if (a === 'close') { this.toggleMini(false); this.end(false); }
        else if (a === 'mic') { this.action('mic'); b.innerHTML = icon(this.S && this.S.mic ? 'mic' : 'micOff'); }
      }));
      document.onkeydown = e => this.keys(e);
    },

    /* MINI_MODE_V1: свернуть встречу в маленькое окно поверх сайта.
       Звонок продолжается: потоки и таймеры не трогаем. */
    toggleMini(on) {
      const S = this.S; if (!S) return;
      S.mini = on === undefined ? !S.mini : !!on;
      this.layer.classList.toggle('mini-mode', S.mini);
      document.body.classList.toggle('in-meeting', !S.mini);
      const bar = $('#miniBar', this.layer);
      if (bar) bar.classList.toggle('hidden', !S.mini);
    },

    /* ---------- сцена ---------- */
    renderStage() {
      const S = this.S, st = $('#stage', this.layer); if (!st) return;
      const all = [{ id: 'me', name: S.name + ' (Вы)', initials: App.user.initials, color: App.user.color, mic: S.mic, cam: S.cam && !!(S.stream && S.stream.getVideoTracks().length), hand: S.hand, host: S.isHost, me: true, pinned: S.pinned === 'me', spotlight: S.spotlight === 'me' }, ...S.participants];
      const tile = (p, extra = '') => `
        <div class="tile-v ${p.speaking ? 'speaking' : ''} ${p.pinned ? 'pinned' : ''} ${p.hand ? 'has-hand' : ''}" data-id="${p.id}" ${extra}>
          ${p.me ? `<div data-self-video style="position:absolute;inset:0"></div>` : (p.cam ? `<div class="video-bars"></div><div class="avatar-wrap"><span class="avatar avatar-lg" style="background:${p.color}">${p.initials}</span></div>` : `<div class="avatar-wrap"><span class="avatar avatar-lg" style="background:${p.color};filter:grayscale(.4)">${p.initials}</span></div>`)}
          <div class="badges">${p.host ? `<span class="badge">${icon('crown')} Организатор</span>` : ''}${p.cohost ? `<span class="badge">Соорганизатор</span>` : ''}${p.spotlight ? `<span class="badge">${icon('star')} В центре</span>` : ''}${p.pinned ? `<span class="badge">${icon('pin')}</span>` : ''}${p.room ? `<span class="badge">Зал ${p.room}</span>` : ''}</div>
          ${p.hand ? `<span class="hand" title="Поднята рука">✋</span>` : ''}
          <div class="tile-menu">
            <button data-t="pin:${p.id}" title="${p.pinned ? 'Открепить' : 'Закрепить'}">${icon('pin')}</button>
            ${S.isHost && !p.me ? `<button data-t="menu:${p.id}" title="Ещё">${icon('moreV')}</button>` : ''}
          </div>
          <span class="name-tag">${p.mic ? icon('mic') : icon('micOff', 'mic-off')} ${esc(p.name)}</span>
          ${!p.me ? `<span class="connection ${p.poor ? 'poor' : ''}" title="Качество связи"><i></i><i></i><i></i><i></i></span>` : ''}
        </div>`;

      let html = '';
      if (S.sharing || S.wbShared) {
        html = `<div class="share-stage">
          <div class="share-main" id="shareMain">${S.wbShared ? '' : `<span class="share-label">${S.sharing === 'me' ? 'Вы демонстрируете экран' : esc(S.sharing) + ' демонстрирует экран'}</span><div class="share-actions">${S.annot ? '' : `<button class="btn-ghost btn-sm" data-a="annotate" title="Рисовать поверх экрана">${icon('pen')} Комментировать</button>`}${S.sharing === 'me' ? `<button class="btn-danger btn-sm" data-a="share">${icon('stop')} Стоп показ</button>` : ''}</div>`}</div>
          <div class="share-side">${all.map(p => tile(p)).join('')}</div></div>`;
      } else if (S.view === 'speaker') {
        const mainId = S.spotlight || S.pinned || (S.participants.find(p => p.speaking) || {}).id || S.participants[0]?.id || 'me';
        const main = all.find(p => p.id === mainId) || all[0];
        html = `<div class="video-grid speaker">${tile(main)}<div class="strip">${all.filter(p => p !== main).map(p => tile(p)).join('')}</div></div>`;
      } else {
        const n = all.length; let cols = n <= 1 ? 1 : n <= 4 ? 2 : n <= 9 ? 3 : 4; if (window.innerWidth < 640) cols = Math.min(cols, 2);
        html = `<div class="video-grid" style="grid-template-columns:repeat(${cols},1fr);grid-auto-rows:minmax(0,1fr)">${all.map(p => tile(p)).join('')}</div>`;
      }
      html += `<div class="captions ${S.captions && S.captionText ? '' : 'hidden'}" id="captions">${S.captionText}</div>`;
      st.innerHTML = html;
      this.attachSelf();
      if (S.sharing === 'me' && S.displayStream) {
        if (!this.shareVideo) { this.shareVideo = document.createElement('video'); this.shareVideo.autoplay = true; this.shareVideo.muted = true; this.shareVideo.playsInline = true; }
        this.shareVideo.srcObject = S.displayStream; $('#shareMain', st).appendChild(this.shareVideo);
      } else if (S.sharing && S.sharing !== 'me') {
        $('#shareMain', st).insertAdjacentHTML('beforeend', `<div style="position:absolute;inset:0;display:grid;place-items:center;background:linear-gradient(135deg,#0f172a,#1e1b4b);color:#94a3b8;font-weight:700">Демонстрация экрана участника (демо)</div>`);
      }
      if (S.wbShared) this.mountWhiteboard($('#shareMain', st));
      if (S.sharing && !S.wbShared && S.annot) this.mountAnnotations($('#shareMain', st));
      st.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', e => { e.stopPropagation(); this.action(b.dataset.a, b); }));
      st.querySelectorAll('[data-t]').forEach(b => b.addEventListener('click', e => { e.stopPropagation(); this.tileAction(b.dataset.t, b); }));
      st.querySelectorAll('.tile-v').forEach(t => t.addEventListener('dblclick', () => { S.view = 'speaker'; S.pinned = t.dataset.id; this.renderRoom(); }));
    },

    tileAction(t, btn) {
      const S = this.S; const [act, id] = t.split(':');
      if (act === 'pin') { S.pinned = S.pinned === id ? null : id; if (S.pinned && S.view === 'gallery') S.view = 'speaker'; this.renderRoom(); }
      if (act === 'menu') this.participantMenu(id, btn);
    },

    participantMenu(id, anchor) {
      const S = this.S, p = S.participants.find(x => x.id === id); if (!p) return;
      this.popover(anchor, `
        <h5>${esc(p.name)}</h5>
        <button data-pm="mute">${icon(p.mic ? 'micOff' : 'mic')} ${p.mic ? 'Выключить микрофон' : 'Попросить включить микрофон'}</button>
        <button data-pm="cam">${icon(p.cam ? 'videoOff' : 'video')} ${p.cam ? 'Остановить видео' : 'Попросить включить видео'}</button>
        <button data-pm="spot">${icon('star')} ${p.spotlight ? 'Убрать из центра' : 'Показать всем в центре'}</button>
        <button data-pm="chat">${icon('chat')} Личное сообщение</button>
        <button data-pm="rename">${icon('edit')} Переименовать</button>
        <button data-pm="host">${icon('crown')} ${p.cohost ? 'Снять соорганизатора' : 'Назначить соорганизатором'}</button>
        <button data-pm="hand" ${p.hand ? '' : 'disabled'}>${icon('hand')} Опустить руку</button>
        <hr>
        <button data-pm="waiting">${icon('clock')} Отправить в зал ожидания</button>
        <button data-pm="remove" class="danger-text">${icon('userX')} Удалить из встречи</button>`, m => {
        m.querySelectorAll('[data-pm]').forEach(b => b.addEventListener('click', () => {
          const a = b.dataset.pm; this.closePop();
          if (a === 'mute') { if (p.mic) { p.mic = false; toast(`Микрофон ${p.name} выключен`); } else { toast(`Запрос отправлен: ${p.name} включит микрофон`); setTimeout(() => { p.mic = true; this.renderStage(); this.renderPanel(); }, 2500); } }
          if (a === 'cam') { p.cam = !p.cam; }
          if (a === 'spot') { S.participants.forEach(x => x.spotlight = false); p.spotlight = !p.spotlight; S.spotlight = p.spotlight ? p.id : null; if (p.spotlight) S.view = 'speaker'; }
          if (a === 'chat') { S.chatTo = p.id; S.panel = 'chat'; }
          if (a === 'rename') { const n = prompt('Новое имя участника', p.name); if (n) { p.name = n.trim(); p.initials = SIM.initials(p.name); } }
          if (a === 'host') { p.cohost = !p.cohost; toast(p.cohost ? `${p.name} — соорганизатор` : `${p.name} больше не соорганизатор`); }
          if (a === 'hand') p.hand = false;
          if (a === 'waiting') { S.participants.splice(S.participants.indexOf(p), 1); S.waiting.push({ id: p.id, name: p.name, initials: p.initials, color: p.color }); toast(`${p.name} перемещён в зал ожидания`); }
          if (a === 'remove') { S.participants.splice(S.participants.indexOf(p), 1); S.chat.push({ sys: true, text: `${p.name} удалён организатором` }); toast(`${p.name} удалён из встречи`); }
          this.renderRoom();
        }));
      });
    },

    /* ---------- панель инструментов ---------- */
    renderToolbar() {
      const S = this.S, tb = $('#toolbar', this.layer); if (!tb) return;
      const hands = S.participants.filter(p => p.hand).length + (S.hand ? 1 : 0);
      const tool = (a, ic, lbl, cls = '', extra = '') => `<button class="tool ${cls}" data-a="${a}" title="${lbl}">${icon(ic)}<span class="lbl">${lbl}</span>${extra}</button>`;
      tb.innerHTML = `
        <div class="group left">
          <div class="tool-split">${tool('mic', S.mic ? 'mic' : 'micOff', S.mic ? 'Выкл. звук' : 'Вкл. звук', S.mic ? '' : 'off')}<button class="caret" data-a="micMenu" title="Настройки звука">${icon('chevUp')}</button></div>
          <div class="tool-split">${tool('cam', S.cam ? 'video' : 'videoOff', S.cam ? 'Стоп видео' : 'Вкл. видео', S.cam ? '' : 'off')}<button class="caret" data-a="camMenu" title="Настройки видео">${icon('chevUp')}</button></div>
        </div>
        <div class="group center">
          ${S.isHost ? tool('security', S.locked ? 'lock' : 'shield', 'Безопасность') : ''}
          ${tool('panel:participants', 'users', 'Участники', S.panel === 'participants' ? 'active' : '', `<span class="count">${S.participants.length + 1}</span>${S.waiting.length ? '<span class="dot"></span>' : ''}`)}
          ${tool('panel:chat', 'chat', 'Чат', S.panel === 'chat' ? 'active' : '', S.unread && S.panel !== 'chat' ? `<span class="count">${S.unread}</span>` : '')}
          <div class="tool-split">${tool('share', S.sharing === 'me' ? 'stop' : 'monitorUp', S.sharing === 'me' ? 'Стоп показ' : 'Демонстрация', S.sharing === 'me' ? 'active' : '')}<button class="caret" data-a="shareMenu" title="Варианты демонстрации">${icon('chevUp')}</button></div>
          ${tool('record', S.recording ? 'stop' : 'record', S.recording ? 'Стоп запись' : 'Запись', S.recording ? 'active' : '')}
          ${tool('reactions', 'smile', 'Реакции')}
          ${tool('hand', 'hand', S.hand ? 'Опустить руку' : 'Поднять руку', S.hand ? 'active' : '', hands ? `<span class="count">${hands}</span>` : '')}
          ${tool('whiteboard', 'board', 'Доска', S.wbShared ? 'active' : '')}
          ${tool('panel:polls', 'poll', 'Опросы', S.panel === 'polls' ? 'active' : '')}
          ${tool('panel:rooms', 'split', 'Залы', S.panel === 'rooms' ? 'active' : '')}
          ${tool('captions', 'captions', 'Субтитры', S.captions ? 'active' : '')}
          ${tool('more', 'more', 'Ещё')}
        </div>
        <div class="group right"><button class="leave-btn" data-a="leave">${S.isHost ? 'Завершить' : 'Выйти'}</button></div>`;
      tb.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', e => this.action(b.dataset.a, b)));
    },

    action(a, btn) {
      const S = this.S;
      const [act, arg] = a.split(':');
      switch (act) {
        case 'mic': S.mic = !S.mic; if (S.stream) S.stream.getAudioTracks().forEach(t => t.enabled = S.mic); if (S.mic && !(S.stream && S.stream.getAudioTracks().length)) this.getMedia(); toast(S.mic ? 'Микрофон включён' : 'Микрофон выключен'); break;
        case 'cam': S.cam = !S.cam; this.getMedia().then(() => this.renderStage()); break;
        case 'micMenu': return this.micMenu(btn);
        case 'camMenu': return this.camMenu(btn);
        case 'security': return this.securityMenu(btn);
        case 'panel': S.panel = S.panel === arg ? null : arg; if (arg === 'chat') S.unread = 0; break;
        case 'share': return S.sharing === 'me' ? this.stopShare() : this.startShare();
        case 'shareMenu': return this.shareMenu(btn);
        case 'record': return S.recording ? this.stopRecording() : this.startRecording();
        case 'reactions': return this.reactionsMenu(btn);
        case 'hand': S.hand = !S.hand; S.chat.push({ sys: true, text: S.hand ? 'Вы подняли руку' : 'Вы опустили руку' }); break;
        case 'whiteboard': return this.toggleWhiteboard();
        case 'annotate': return this.toggleAnnotations();
        case 'captions': return this.toggleCaptions();
        case 'more': return this.moreMenu(btn);
        case 'view': S.view = arg; break;
        case 'fullscreen': { const on = this.layer.classList.toggle('focus-mode'); toast(on ? 'Режим фокуса: верхняя панель скрыта (Esc — вернуть)' : 'Обычный режим', 'ok', 1800); return; }
        case 'info': return this.infoModal();
        case 'leave': return this.leaveMenu(btn);
        case 'minimize': return this.toggleMini(true);
      }
      this.renderRoom();
    },

    /* ---------- всплывающие меню ---------- */
    popover(anchor, html, setup, cls = '') {
      this.closePop();
      const pop = document.createElement('div'); pop.className = `popover ${cls}`; pop.innerHTML = html;
      const holder = anchor.closest('.tool-split') || anchor.closest('.tile-v') || anchor.closest('.group') || anchor;
      holder.style.position = 'relative'; holder.appendChild(pop);
      if (anchor.closest('.tile-v')) { pop.style.bottom = 'auto'; pop.style.top = '44px'; pop.style.left = 'auto'; pop.style.right = '8px'; pop.style.transform = 'none'; }
      if (anchor.closest('.group')) {
        const r = anchor.getBoundingClientRect(), hr = holder.getBoundingClientRect();
        pop.style.left = (r.left - hr.left + r.width / 2) + 'px';
      }
      setup && setup(pop);
      this.S.activePop = pop;
      setTimeout(() => {
        const rect = pop.getBoundingClientRect();
        if (rect.left < 8) { pop.style.left = 'auto'; pop.style.transform = 'none'; pop.style.right = 'auto'; pop.style.left = '8px'; }
        if (rect.right > window.innerWidth - 8) { pop.style.left = 'auto'; pop.style.transform = 'none'; pop.style.right = '8px'; }
        const off = e => { if (!pop.contains(e.target)) { this.closePop(); document.removeEventListener('pointerdown', off); } };
        document.addEventListener('pointerdown', off);
      }, 0);
    },
    closePop() { if (this.S && this.S.activePop) { this.S.activePop.remove(); this.S.activePop = null; } },

    micMenu(btn) {
      const S = this.S, d = App.devices;
      const list = (arr, sel, key) => arr.length ? arr.map(x => `<button data-dev="${key}:${x.deviceId}" class="${sel === x.deviceId ? 'checked' : ''}">${sel === x.deviceId ? icon('check') : '<span style="width:16px"></span>'} ${esc(x.label || 'Устройство')}</button>`).join('') : `<button disabled>${icon('info')} Устройства появятся после разрешения доступа</button>`;
      this.popover(btn, `
        <h5>Микрофон</h5>${list(d.mics, App.settings.micId || (d.mics[0] || {}).deviceId, 'mic')}
        <h5>Динамики</h5>${list(d.speakers, App.settings.spkId || (d.speakers[0] || {}).deviceId, 'spk')}
        <hr>
        <button data-o="noise" class="${S.noise ? 'checked' : ''}">${icon(S.noise ? 'check' : 'volume')} Подавление фонового шума</button>
        <button data-o="test">${icon('volume')} Проверить динамик и микрофон</button>
        <button data-o="leaveAudio">${icon('phone')} Отключить звук компьютера</button>
        <button data-o="settings">${icon('settings')} Настройки звука…</button>`, m => {
        m.querySelectorAll('[data-dev]').forEach(b => b.addEventListener('click', () => { const [k, id] = b.dataset.dev.split(':'); if (k === 'mic') { App.settings.micId = id; this.getMedia(); } else App.settings.spkId = id; toast('Устройство переключено', 'ok'); this.closePop(); }));
        m.querySelectorAll('[data-o]').forEach(b => b.addEventListener('click', () => {
          const o = b.dataset.o; this.closePop();
          if (o === 'noise') { S.noise = !S.noise; this.getMedia(); toast(S.noise ? 'Подавление шума включено' : 'Подавление шума выключено'); }
          if (o === 'test') this.testAudio();
          if (o === 'leaveAudio') { S.mic = false; if (S.stream) S.stream.getAudioTracks().forEach(t => t.stop()); toast('Звук компьютера отключён'); this.renderToolbar(); this.renderStage(); }
          if (o === 'settings') App.openSettingsModal('audio');
        }));
      });
    },
    testAudio() {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)(); const o = ctx.createOscillator(); const g = ctx.createGain();
        o.type = 'sine'; o.frequency.value = 660; g.gain.value = .08; o.connect(g).connect(ctx.destination); o.start();
        setTimeout(() => { o.frequency.value = 880; }, 180); setTimeout(() => { o.stop(); ctx.close(); }, 420);
        toast('Тестовый сигнал воспроизведён. Говорите — индикатор на вашей плитке подсветится', 'ok', 4000);
      } catch (e) { toast('Аудио недоступно', 'bad'); }
    },
    camMenu(btn) {
      const S = this.S, d = App.devices;
      this.popover(btn, `
        <h5>Камера</h5>
        ${d.cams.length ? d.cams.map(x => `<button data-cam="${x.deviceId}" class="${(App.settings.camId || (d.cams[0] || {}).deviceId) === x.deviceId ? 'checked' : ''}">${(App.settings.camId || (d.cams[0] || {}).deviceId) === x.deviceId ? icon('check') : '<span style="width:16px"></span>'} ${esc(x.label || 'Камера')}</button>`).join('') : `<button disabled>${icon('info')} Камеры появятся после разрешения доступа</button>`}
        <hr>
        <button data-o="bg">${icon('sparkles')} Выбрать виртуальный фон…</button>
        <button data-o="mirror" class="${S.mirror ? 'checked' : ''}">${icon(S.mirror ? 'check' : 'layout')} Зеркальное отображение</button>
        <button data-o="hd" class="${S.hd ? 'checked' : ''}">${icon(S.hd ? 'check' : 'video')} HD-видео (720p)</button>
        <button data-o="settings">${icon('settings')} Настройки видео…</button>`, m => {
        m.querySelectorAll('[data-cam]').forEach(b => b.addEventListener('click', () => { App.settings.camId = b.dataset.cam; this.getMedia(); this.closePop(); toast('Камера переключена', 'ok'); }));
        m.querySelectorAll('[data-o]').forEach(b => b.addEventListener('click', () => {
          const o = b.dataset.o; this.closePop();
          if (o === 'bg') this.bgModal();
          if (o === 'mirror') { S.mirror = !S.mirror; App.settings.mirror = S.mirror; this.attachSelf(); }
          if (o === 'hd') { S.hd = !S.hd; this.getMedia(); toast(S.hd ? 'HD включено' : 'HD выключено'); }
          if (o === 'settings') App.openSettingsModal('video');
        }));
      });
    },
    bgModal() {
      const S = this.S;
      const opts = [['none', 'Без фона', 'linear-gradient(135deg,#1e293b,#0f172a)'], ['blur', 'Размытие', 'linear-gradient(135deg,#334155,#64748b)'], ['soft', 'Мягкий свет', 'linear-gradient(135deg,#fbbf24,#f472b6)'], ['formyla', 'FORMYLA', 'radial-gradient(circle at 30% 30%,rgba(56,189,248,.5),transparent 50%),radial-gradient(circle at 70% 70%,rgba(139,92,246,.5),transparent 50%),#0f172a'], ['board', 'Аудитория', 'linear-gradient(180deg,#1e3a5f,#0b1220)'], ['geo', 'Геометрия', 'repeating-linear-gradient(45deg,#1e293b 0 10px,#0f172a 10px 20px)']];
      App.modal(`Виртуальный фон`, `
        <p class="muted small">Размытие применяется к видеопотоку локально. Фоны с изображением показываются как рамка вокруг видео (демо-режим без сегментации).</p>
        <div class="cards-grid" style="grid-template-columns:repeat(3,1fr)">
          ${opts.map(([k, l, bg]) => `<button class="tile ${S.bg === k ? 'active' : ''}" data-bg="${k}" style="padding:10px;gap:8px;${S.bg === k ? 'border-color:#8b5cf6' : ''}"><span style="display:block;width:100%;aspect-ratio:16/9;border-radius:10px;background:${bg}"></span><span class="tile-title" style="font-size:13px">${l}</span></button>`).join('')}
        </div>`, [{ label: 'Готово', cls: 'btn-gradient', act: 'close' }], m => {
        m.querySelectorAll('[data-bg]').forEach(b => b.addEventListener('click', () => { S.bg = b.dataset.bg; App.settings.bg = S.bg; this.attachSelf(); this.applyFrameBg(); m.querySelectorAll('[data-bg]').forEach(x => x.style.borderColor = x === b ? '#8b5cf6' : ''); }));
      });
    },
    applyFrameBg() {
      const S = this.S; const bgs = { formyla: 'radial-gradient(circle at 30% 30%,rgba(56,189,248,.5),transparent 50%),radial-gradient(circle at 70% 70%,rgba(139,92,246,.5),transparent 50%),#0f172a', board: 'linear-gradient(180deg,#1e3a5f,#0b1220)', geo: 'repeating-linear-gradient(45deg,#1e293b 0 10px,#0f172a 10px 20px)' };
      this.layer.querySelectorAll('[data-self-video]').forEach(h => { h.style.background = bgs[S.bg] || ''; h.style.padding = bgs[S.bg] ? '6%' : '0'; const v = h.querySelector('video'); if (v) v.style.borderRadius = bgs[S.bg] ? '12px' : '0'; });
    },
    securityMenu(btn) {
      const S = this.S;
      const row = (k, l, v) => `<button data-s="${k}" class="${v ? 'checked' : ''}">${v ? icon('check') : '<span style="width:16px"></span>'} ${l}</button>`;
      this.popover(btn, `
        ${row('locked', 'Заблокировать встречу', S.locked)}
        ${row('waitingRoom', 'Включить зал ожидания', S.waitingRoom)}
        <hr><h5>Разрешить участникам</h5>
        ${row('allowShare', 'Демонстрацию экрана', S.allowShare)}
        ${row('allowChat', 'Чат', S.allowChat)}
        ${row('allowRename', 'Переименование', S.allowRename)}
        ${row('allowUnmute', 'Включать свой микрофон', S.allowUnmute)}
        <hr>
        <button data-s="muteAll">${icon('micOff')} Выключить звук всем</button>
        <button data-s="suspend" class="danger-text">${icon('shield')} Приостановить действия участников</button>`, m => {
        m.querySelectorAll('[data-s]').forEach(b => b.addEventListener('click', () => {
          const k = b.dataset.s;
          if (k === 'muteAll') { S.participants.forEach(p => p.mic = false); toast('Звук выключен у всех участников'); }
          else if (k === 'suspend') { S.locked = true; S.allowShare = S.allowChat = S.allowRename = S.allowUnmute = false; S.sharing = S.sharing === 'me' ? 'me' : null; S.participants.forEach(p => { p.mic = false; p.cam = false; }); toast('Действия участников приостановлены: встреча заблокирована, чат и показ экрана отключены', 'bad', 5000); }
          else { S[k] = !S[k]; toast({ locked: S.locked ? 'Встреча заблокирована — новые участники не смогут войти' : 'Встреча разблокирована', waitingRoom: S.waitingRoom ? 'Зал ожидания включён' : 'Зал ожидания выключен', allowShare: 'Настройка сохранена', allowChat: 'Настройка сохранена', allowRename: 'Настройка сохранена', allowUnmute: 'Настройка сохранена' }[k]); }
          this.closePop(); this.renderRoom();
        }));
      });
    },
    shareMenu(btn) {
      this.popover(btn, `
        <button data-sh="screen">${icon('monitor')} Экран, окно или вкладка</button>
        <button data-sh="wb">${icon('board')} Доска для совместной работы</button>
        <button data-sh="cam2">${icon('video')} Вторая камера (документ-камера)</button>
        <button data-sh="audio">${icon('volume')} Только звук компьютера</button>
        <button data-sh="annot" ${S.sharing ? '' : 'disabled'}>${icon('pen')} Комментировать поверх экрана</button>
        <hr>
        <button data-sh="multi">${icon('users')} Разрешить одновременный показ нескольким</button>`, m => {
        m.querySelectorAll('[data-sh]').forEach(b => b.addEventListener('click', () => {
          const k = b.dataset.sh; this.closePop();
          if (k === 'screen') this.startShare();
          if (k === 'wb') this.toggleWhiteboard(true);
          if (k === 'cam2') toast('Подключите вторую камеру — она появится в списке камер');
          if (k === 'audio') this.startShare(true);
          if (k === 'annot') this.toggleAnnotations();
          if (k === 'multi') toast('Одновременная демонстрация разрешена');
        }));
      });
    },
    reactionsMenu(btn) {
      const S = this.S;
      this.popover(btn, `
        <div class="emoji-row">${['👍', '❤️', '😂', '😮', '🎉', '👏', '🔥', '🤔', '✅', '💯', '🙌', '😢'].map(e => `<button data-e="${e}">${e}</button>`).join('')}</div>
        <hr>
        <button data-r="hand">${icon('hand')} ${S.hand ? 'Опустить руку' : 'Поднять руку'}</button>
        <button data-r="slow">🐢 Помедленнее</button><button data-r="fast">🐇 Побыстрее</button>
        <button data-r="away">☕ Я отошёл</button>`, m => {
        m.querySelectorAll('[data-e]').forEach(b => b.addEventListener('click', () => { this.react('me', b.dataset.e); this.closePop(); }));
        m.querySelectorAll('[data-r]').forEach(b => b.addEventListener('click', () => { const r = b.dataset.r; this.closePop(); if (r === 'hand') this.action('hand'); else { this.react('me', { slow: '🐢', fast: '🐇', away: '☕' }[r]); S.chat.push({ sys: true, text: `Вы: ${b.textContent.trim()}` }); } }));
      });
    },
    react(id, emoji) {
      const tile = this.layer.querySelector(`.tile-v[data-id="${id}"]`);
      if (tile) { const el = document.createElement('span'); el.className = 'reaction-float'; el.textContent = emoji; tile.appendChild(el); setTimeout(() => el.remove(), 2200); }
      if (id === 'me') { const f = document.createElement('span'); f.className = 'reaction-fly'; f.textContent = emoji; f.style.left = (window.innerWidth / 2 - 60 + Math.random() * 120) + 'px'; f.style.bottom = '90px'; document.body.appendChild(f); setTimeout(() => f.remove(), 2400); }
    },
    moreMenu(btn) {
      const S = this.S;
      this.popover(btn, `
        <button data-m="bg">${icon('sparkles')} Виртуальный фон и эффекты</button>
        <button data-m="stats">${icon('wifi')} Статистика соединения</button>
        <button data-m="timer">${icon('timer')} Таймер для встречи</button>
        <button data-m="invite">${icon('link')} Пригласить участников</button>
        <button data-m="apps">${icon('apps')} Приложения FORMYLA (задачи дня, методы)</button>
        <button data-m="layout">${icon(S.view === 'gallery' ? 'speaker' : 'grid')} ${S.view === 'gallery' ? 'Вид докладчика' : 'Вид галереи'}</button>
        <button data-m="hideSelf">${icon('videoOff')} Скрыть своё видео</button>
        <button data-m="shortcuts">${icon('keyboard')} Горячие клавиши</button>
        <hr>
        <button data-m="settings">${icon('settings')} Настройки</button>`, m => {
        m.querySelectorAll('[data-m]').forEach(b => b.addEventListener('click', () => {
          const k = b.dataset.m; this.closePop();
          if (k === 'bg') this.bgModal();
          if (k === 'stats') this.statsModal();
          if (k === 'timer') this.timerModal();
          if (k === 'invite') this.infoModal();
          if (k === 'apps') this.appsModal();
          if (k === 'layout') { S.view = S.view === 'gallery' ? 'speaker' : 'gallery'; this.renderRoom(); }
          if (k === 'hideSelf') { const t = this.layer.querySelector('.tile-v[data-id=me]'); if (t) t.classList.toggle('hidden'); toast('Ваше видео скрыто только для вас. Нажмите ещё раз, чтобы вернуть'); }
          if (k === 'shortcuts') App.modal('Горячие клавиши', `<ul style="display:grid;gap:8px;font-size:14px">${[['Alt + A', 'Микрофон вкл/выкл'], ['Alt + V', 'Видео вкл/выкл'], ['Пробел (удерж.)', 'Временно включить микрофон'], ['Alt + S', 'Демонстрация экрана'], ['Alt + R', 'Запись'], ['Alt + H', 'Чат'], ['Alt + U', 'Участники'], ['Alt + Y', 'Поднять руку'], ['Alt + W', 'Доска'], ['Alt + C', 'Субтитры'], ['Alt + F', 'Полный экран'], ['Esc', 'Закрыть панели']].map(([k, v]) => `<li style="display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--border-soft)"><span class="muted">${v}</span><kbd style="font-family:inherit;font-weight:800;background:rgba(255,255,255,.08);padding:2px 8px;border-radius:6px">${k}</kbd></li>`).join('')}</ul>`, [{ label: 'Понятно', cls: 'btn-gradient', act: 'close' }]);
          if (k === 'settings') App.openSettingsModal('general');
        }));
      });
    },
    statsModal() {
      const S = this.S; const vt = S.stream && S.stream.getVideoTracks()[0]; const st = vt ? vt.getSettings() : {};
      App.modal('Статистика соединения', `
        <div class="stat-row" style="margin-top:0"><div class="stat"><b>${rnd(18, 42)} мс</b><span>Задержка</span></div><div class="stat"><b>${(Math.random() * .4).toFixed(2)} %</b><span>Потери пакетов</span></div><div class="stat"><b>${rnd(4, 9)} мс</b><span>Джиттер</span></div></div>
        <div class="stat-row"><div class="stat"><b>${st.width || 0}×${st.height || 0}</b><span>Разрешение отправки</span></div><div class="stat"><b>${st.frameRate ? Math.round(st.frameRate) : 0} fps</b><span>Кадры/с</span></div><div class="stat"><b>${vt ? rnd(900, 2400) : 0} кбит/с</b><span>Битрейт видео</span></div></div>
        <p class="small muted" style="margin-top:14px">Локальные показатели берутся из настроек вашего видеотрека; сетевые метрики показаны для демонстрации, пока не подключён сервер сигнализации.</p>`, [{ label: 'Закрыть', cls: 'btn-ghost', act: 'close' }]);
    },
    timerModal() {
      const S = this.S;
      App.modal('Таймер для встречи', `<label class="field">Длительность, минут<input type="number" id="tmMin" value="10" min="1" max="180"></label><p class="small muted">Таймер виден всем участникам в верхней панели.</p>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Запустить', cls: 'btn-gradient', act: 'ok' }], null, () => {
        const mins = +$('#tmMin').value || 10; let left = mins * 60;
        const el = document.createElement('span'); el.className = 'room-timer'; el.style.color = '#fbbf24'; $('.room-top .left', this.layer).appendChild(el);
        const t = setInterval(() => { left--; el.textContent = '⏱ ' + fmtTime(left); if (left <= 0) { clearInterval(t); el.remove(); toast('Время таймера истекло', 'bad'); } }, 1000);
        this.timers.push(t); S.chat.push({ sys: true, text: `Организатор запустил таймер на ${mins} мин` }); this.renderPanel();
      });
    },
    appsModal() {
      App.modal('Приложения FORMYLA', `<div class="cards-grid" style="grid-template-columns:1fr 1fr">
        ${[['📅', 'Задачи дня', 'Открыть текущую задачу дня прямо во встрече', 'https://formyla.net/daily_tasks/'], ['📚', 'Каталог методов (102)', 'Разобрать метод по теме занятия', 'https://formyla.net/olympiads/methods'], ['🏆', 'Календарь олимпиад', 'Ближайшие олимпиады и пробники', 'https://formyla.net/olympiad-prep/calendar'], ['🎓', 'Куратор подготовки', 'Индивидуальный план ученика', 'https://formyla.net/prep/coach']].map(([e, t, d, u]) => `<a class="tile" href="${u}" target="_blank" rel="noopener noreferrer"><span style="font-size:28px">${e}</span><span class="tile-title">${t}</span><span class="tile-desc">${d}</span></a>`).join('')}</div>`, [{ label: 'Закрыть', cls: 'btn-ghost', act: 'close' }]);
    },
    infoModal() {
      const S = this.S;
      App.modal('Информация о встрече', `
        <div style="display:grid;gap:10px;font-size:14px">
          <div><span class="muted">Тема</span><br><b>${esc(S.topic)}</b></div>
          <div><span class="muted">Идентификатор</span><br><b style="font-size:22px;letter-spacing:2px">${S.id}</b></div>
          <div><span class="muted">Организатор</span><br><b>${S.isHost ? esc(S.name) : 'Мария Иванова'}</b></div>
          <div><span class="muted">Код доступа</span><br><b>${S.pw || 'не требуется'}</b></div>
          <div><span class="muted">Ссылка для приглашения</span><br><code style="word-break:break-all;color:#7dd3fc">${this.inviteLink()}</code></div>
          <div><span class="muted">Шифрование</span><br><span class="tag ok">${icon('shield')} сквозное (E2EE)</span></div>
        </div>`, [{ label: 'Скопировать приглашение', cls: 'btn-gradient', act: 'ok' }, { label: 'Закрыть', cls: 'btn-ghost', act: 'close' }], null, () => this.copyInvite());
    },
    inviteLink() { return `${location.origin}${location.pathname}#/join/${this.S.id.replace(/\s/g, '')}`; },
    copyInvite() {
      const S = this.S; const text = `${App.user.name} приглашает вас на встречу FORMYLA Meet\n\nТема: ${S.topic}\nСсылка: ${this.inviteLink()}\nИдентификатор: ${S.id}${S.pw ? `\nКод доступа: ${S.pw}` : ''}`;
      navigator.clipboard ? navigator.clipboard.writeText(text).then(() => toast('Приглашение скопировано', 'ok')).catch(() => toast('Не удалось скопировать — скопируйте вручную из окна информации', 'bad')) : toast('Буфер обмена недоступен', 'bad');
    },
    leaveMenu(btn) {
      const S = this.S;
      this.popover(btn, `${S.isHost ? `<button data-l="end" class="danger-text">${icon('phone')} Завершить встречу для всех</button><button data-l="assign">${icon('crown')} Выйти и назначить организатора</button>` : ''}<button data-l="leave">${icon('logout')} Покинуть встречу</button>`, m => {
        m.querySelectorAll('[data-l]').forEach(b => b.addEventListener('click', () => {
          const k = b.dataset.l; this.closePop();
          if (k === 'assign') { const p = S.participants[0]; if (p) toast(`${p.name} назначен организатором`); }
          this.end(k === 'end');
        }));
      }, 'right');
    },

    /* ---------- демонстрация экрана ---------- */
    async startShare(audioOnly) {
      const S = this.S;
      if (!S.isHost && !S.allowShare) return toast('Организатор запретил демонстрацию экрана', 'bad');
      try {
        S.displayStream = await navigator.mediaDevices.getDisplayMedia({ video: !audioOnly || true, audio: true });
        S.sharing = 'me'; S.wbShared = false;
        S.displayStream.getVideoTracks()[0].addEventListener('ended', () => this.stopShare());
        S.chat.push({ sys: true, text: 'Вы начали демонстрацию экрана' });
        this.renderRoom(); toast('Демонстрация экрана начата', 'ok');
      } catch (e) {
        if (e.name === 'NotAllowedError') toast('Демонстрация отменена или запрещена в этом окне. Откройте приложение в отдельной вкладке', 'bad', 5000);
        else toast('Демонстрация экрана недоступна: ' + e.message, 'bad');
      }
    },
    stopShare() {
      const S = this.S; if (S.displayStream) S.displayStream.getTracks().forEach(t => t.stop()); S.displayStream = null;
      if (S.sharing === 'me') S.chat.push({ sys: true, text: 'Вы остановили демонстрацию экрана' });
      S.sharing = null; this.closeAnnotations(); this.renderRoom();
    },

    /* ---------- аннотации поверх демонстрации экрана ---------- */
    toggleAnnotations() {
      const S = this.S;
      if (!S.sharing) return toast('Сначала начните демонстрацию экрана', 'bad');
      if (S.annot) { this.closeAnnotations(); } else { S.annot = true; S.chat.push({ sys: true, text: 'Вы начали комментировать демонстрацию экрана' }); toast('Рисуйте поверх экрана — инструменты вверху. Пометки видят все участники', 'ok', 3500); }
      this.renderRoom();
    },
    closeAnnotations() {
      const S = this.S; if (S.annotWb) { S.annotWb.destroy(); S.annotWb = null; } S.annotPages = null; S.annot = false;
    },
    mountAnnotations(container) {
      const S = this.S;
      const host = document.createElement('div'); host.className = 'annot-layer';
      container.appendChild(host);
      const saved = S.annotWb ? { pages: S.annotWb.pages, page: S.annotWb.page, tool: S.annotWb.tool, color: S.annotWb.color, size: S.annotWb.size, collapsed: !!S.annotWb.root.querySelector('.wb-top.collapsed') } : null;
      if (S.annotWb) S.annotWb.destroy();
      S.annotWb = new Whiteboard(host, { overlay: true, title: 'Комментирование экрана', onClose: () => { this.closeAnnotations(); this.renderRoom(); }, underlay: () => this.shareVideo, collaborators: S.participants.slice(0, 2).map(p => ({ name: p.name.split(' ')[0], initials: p.initials, color: p.solid })) });
      if (saved) { S.annotWb.pages = saved.pages; S.annotWb.page = saved.page; S.annotWb.setColor(saved.color); S.annotWb.size = saved.size; S.annotWb.setTool(saved.tool); S.annotWb.render(); if (saved.collapsed) S.annotWb.root.querySelector('[data-act=hide]').click(); }
    },

    /* ---------- доска ---------- */
    toggleWhiteboard(force) {
      const S = this.S;
      if (S.wbShared && !force) { S.wbShared = false; if (S.wb) { S.wb.destroy(); } S.chat.push({ sys: true, text: 'Доска закрыта' }); }
      else { S.wbShared = true; S.sharing = null; if (S.displayStream) this.stopShare(); S.chat.push({ sys: true, text: 'Вы открыли общую доску' }); }
      this.renderRoom();
    },
    mountWhiteboard(container) {
      const S = this.S;
      const host = document.createElement('div'); host.style.cssText = 'position:absolute;inset:0;display:flex;flex-direction:column;background:#fbfbfe;color:#0f172a';
      container.appendChild(host);
      const saved = S.wb ? { pages: S.wb.pages, page: S.wb.page, title: S.wb.title, bg: S.wb.bg } : null;
      if (S.wb) S.wb.destroy();
      S.wb = new Whiteboard(host, { title: saved ? saved.title : `Доска · ${S.topic}`, onClose: () => this.toggleWhiteboard(), collaborators: S.participants.slice(0, 3).map(p => ({ name: p.name.split(' ')[0], initials: p.initials, color: p.solid })), onChange: () => { S.wbDirty = true; } });
      if (saved) { S.wb.pages = saved.pages; S.wb.page = saved.page; S.wb.bg = saved.bg; S.wb.setTool(S.wb.tool); S.wb.renderPages(); S.wb.render(); }
    },

    /* ---------- запись ---------- */
    startRecording() {
      const S = this.S;
      if (!window.MediaRecorder) return toast('Запись не поддерживается этим браузером', 'bad');
      const cv = document.createElement('canvas'); cv.width = 1280; cv.height = 720; const cx = cv.getContext('2d');
      S.recCanvas = cv;
      const draw = () => {
        if (!S.recording) return;
        cx.fillStyle = '#0b1220'; cx.fillRect(0, 0, 1280, 720);
        const all = [{ name: S.name, initials: App.user.initials, solid: '#8b5cf6', me: true }, ...S.participants];
        const n = all.length, cols = n <= 1 ? 1 : n <= 4 ? 2 : 3, rows = Math.ceil(n / cols), w = 1280 / cols, h = 660 / rows;
        all.forEach((p, i) => {
          const x = (i % cols) * w + 8, y = Math.floor(i / cols) * h + 8, tw = w - 16, th = h - 16;
          cx.fillStyle = '#172033'; cx.beginPath(); cx.roundRect ? cx.roundRect(x, y, tw, th, 16) : cx.rect(x, y, tw, th); cx.fill();
          if (p.me && this.selfVideo && this.selfVideo.srcObject && this.selfVideo.videoWidth) {
            cx.save(); cx.beginPath(); cx.roundRect ? cx.roundRect(x, y, tw, th, 16) : cx.rect(x, y, tw, th); cx.clip();
            const vr = this.selfVideo.videoWidth / this.selfVideo.videoHeight, tr = tw / th; let dw = tw, dh = th; if (vr > tr) dw = th * vr; else dh = tw / vr;
            if (S.mirror) { cx.translate(x + tw, 0); cx.scale(-1, 1); cx.drawImage(this.selfVideo, (tw - dw) / 2, y + (th - dh) / 2, dw, dh); } else cx.drawImage(this.selfVideo, x + (tw - dw) / 2, y + (th - dh) / 2, dw, dh);
            cx.restore();
          } else { cx.fillStyle = p.solid || '#8b5cf6'; cx.beginPath(); cx.arc(x + tw / 2, y + th / 2, Math.min(tw, th) / 5, 0, 7); cx.fill(); cx.fillStyle = '#fff'; cx.font = `800 ${Math.min(tw, th) / 7}px Satoshi, sans-serif`; cx.textAlign = 'center'; cx.textBaseline = 'middle'; cx.fillText(p.initials, x + tw / 2, y + th / 2); }
          cx.fillStyle = 'rgba(6,10,20,.75)'; cx.fillRect(x + 12, y + th - 40, cx.measureText(p.name).width * .6 + 60, 28);
          cx.fillStyle = '#fff'; cx.font = '700 16px Satoshi, sans-serif'; cx.textAlign = 'left'; cx.textBaseline = 'middle'; cx.fillText((p.me ? 'Вы · ' : '') + p.name, x + 22, y + th - 26);
        });
        cx.fillStyle = '#94a3b8'; cx.font = '700 14px Satoshi, sans-serif'; cx.textAlign = 'left'; cx.fillText(`FORMYLA Meet · ${S.topic} · ${fmtTime(S.secs)}`, 16, 700);
        cx.fillStyle = '#ef4444'; cx.beginPath(); cx.arc(1250, 700, 6, 0, 7); cx.fill();
        S.recRaf = requestAnimationFrame(draw);
      };
      const stream = cv.captureStream(15);
      if (S.stream) S.stream.getAudioTracks().forEach(t => stream.addTrack(t));
      const mime = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4'].find(m => MediaRecorder.isTypeSupported(m)) || '';
      try { S.recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined); } catch (e) { return toast('Не удалось начать запись: ' + e.message, 'bad'); }
      const rec = S.recorder; S.recChunks = []; rec.ondataavailable = e => { if (e.data.size) S.recChunks.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(S.recChunks, { type: rec.mimeType || 'video/webm' });
        const url = URL.createObjectURL(blob);
        App.recordings.unshift({ id: 'r' + Date.now(), topic: S.topic, date: new Date(), dur: fmtTime(S.recSecs || 0).replace(/^00:/, ''), size: (blob.size / 1048576).toFixed(1) + ' МБ', src: url, blob });
        toast('Запись сохранена в разделе «Записи»', 'ok', 5000);
      };
      S.recording = true; S.recPaused = false; S.recStart = S.secs; S.recSecs = 0;
      S.recorder.start(1000); draw();
      S.recTick = setInterval(() => { if (!S.recPaused) S.recSecs++; }, 1000); this.timers.push(S.recTick);
      S.chat.push({ sys: true, text: 'Запись встречи начата. Участники уведомлены' });
      this.renderRoom();
    },
    stopRecording() {
      const S = this.S; if (!S.recorder) return;
      S.recording = false; cancelAnimationFrame(S.recRaf); clearInterval(S.recTick);
      try { S.recorder.stop(); } catch (e) { /* уже остановлен */ }
      S.recorder = null; S.chat.push({ sys: true, text: 'Запись остановлена' });
      this.renderRoom();
    },

    /* ---------- субтитры ---------- */
    toggleCaptions() {
      const S = this.S; S.captions = !S.captions;
      if (S.captions) {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (SR) {
          try {
            S.rec = new SR(); S.rec.lang = 'ru-RU'; S.rec.continuous = true; S.rec.interimResults = true;
            S.rec.onresult = e => { const r = e.results[e.results.length - 1]; this.caption(S.name, r[0].transcript); };
            S.rec.onerror = () => { }; S.rec.onend = () => { if (S.captions && S.rec) try { S.rec.start(); } catch (e) { } };
            S.rec.start(); toast('Субтитры включены: ваша речь распознаётся, речь участников — демо', 'ok', 4000);
          } catch (e) { toast('Субтитры включены (демо)', 'ok'); }
        } else toast('Субтитры включены (демо-режим, распознавание речи недоступно в браузере)', 'ok', 4000);
      } else { if (S.rec) { S.rec.onend = null; S.rec.stop(); S.rec = null; } S.captionText = ''; }
      this.renderRoom();
    },
    caption(who, text) {
      const S = this.S; S.captionText = `<b>${esc(who)}:</b> ${esc(text)}`;
      const el = $('#captions', this.layer); if (el) { el.innerHTML = S.captionText; el.classList.toggle('hidden', !S.captions); }
      clearTimeout(S.capT); S.capT = setTimeout(() => { S.captionText = ''; const e = $('#captions', this.layer); if (e) e.classList.add('hidden'); }, 6000);
    },

    /* ---------- боковая панель ---------- */
    renderPanel() {
      const S = this.S, sp = $('#sidePanel', this.layer); if (!sp) return;
      sp.classList.toggle('hidden', !S.panel); if (!S.panel) return;
      const tabs = [['participants', `Участники (${S.participants.length + 1})`], ['chat', 'Чат'], ['polls', 'Опросы'], ['rooms', 'Залы']];
      let body = '', foot = '';
      if (S.panel === 'participants') {
        const pi = p => `<div class="p-item" data-pid="${p.id}"><span class="avatar avatar-sm" style="background:${p.color}">${p.initials}</span><span class="p-name">${esc(p.name)}${p.me ? ' (Вы)' : ''}<small>${p.host ? 'Организатор' : p.cohost ? 'Соорганизатор' : p.room ? 'Зал ' + p.room : 'Участник'}</small></span>${p.hand ? '<span title="Рука поднята">✋</span>' : ''}<span class="p-icons">${p.mic ? icon('mic', 'on') : icon('micOff', 'off')}${p.cam ? icon('video', 'on') : icon('videoOff', 'off')}</span>${S.isHost && !p.me ? `<button class="btn-icon p-more" data-pmenu="${p.id}">${icon('moreV')}</button>` : ''}</div>`;
        const me = { id: 'me', name: S.name, initials: App.user.initials, color: App.user.color, mic: S.mic, cam: S.cam, hand: S.hand, host: S.isHost, me: true };
        body = `
          ${S.waiting.length ? `<div class="p-group">В зале ожидания (${S.waiting.length})</div>${S.waiting.map(w => `<div class="waiting-item"><span class="avatar avatar-sm" style="background:${w.color}">${w.initials}</span><span class="p-name">${esc(w.name)}</span><button class="btn-gradient btn-sm" data-admit="${w.id}">Впустить</button><button class="btn-ghost btn-sm" data-deny="${w.id}">${icon('x')}</button></div>`).join('')}${S.waiting.length > 1 ? `<button class="btn-ghost btn-sm" data-admitall>Впустить всех</button>` : ''}` : ''}
          <div class="p-group">Во встрече (${S.participants.length + 1})</div>
          ${pi(me)}${[...S.participants].sort((a, b) => (b.hand - a.hand) || (b.host - a.host)).map(pi).join('')}`;
        foot = S.isHost ? `<button class="btn-ghost btn-sm" data-pa="invite">${icon('link')} Пригласить</button><button class="btn-ghost btn-sm" data-pa="muteAll">${icon('micOff')} Выкл. звук всем</button><button class="btn-ghost btn-sm" data-pa="lowerAll">${icon('hand')} Опустить руки</button>` : `<button class="btn-ghost btn-sm" data-pa="invite">${icon('link')} Пригласить</button>`;
      }
      if (S.panel === 'chat') {
        body = `<div id="chatList" style="display:flex;flex-direction:column;gap:12px">${S.chat.map(m => m.sys ? `<div class="chat-msg system"><div class="bubble"><div class="text">${esc(m.text)}</div></div></div>` : `<div class="chat-msg ${m.me ? 'me' : ''}"><span class="avatar" style="background:${m.color}">${m.initials}</span><div class="bubble"><div class="meta"><b>${esc(m.from)}</b>${m.to && m.to !== 'all' ? `<span class="private">→ ${esc(m.toName)} (лично)</span>` : ''}<span>${m.time}</span></div><div class="text">${m.file ? `<span class="file">${icon('file')} ${esc(m.file)}</span>` : App.linkify(esc(m.text))}</div></div></div>`).join('')}</div><div class="typing" id="typing"></div>`;
        foot = `<div class="chat-input"><div class="to">Кому: <select id="chatTo">${[['all', 'Все'], ...S.participants.map(p => [p.id, p.name])].map(([v, l]) => `<option value="${v}" ${S.chatTo === v ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select><label class="btn-icon" title="Прикрепить файл" style="margin-left:auto">${icon('file')}<input type="file" class="sr-only" id="chatFile"></label><button class="btn-icon" id="chatEmoji" title="Эмодзи">${icon('smile')}</button></div><div class="row"><textarea id="chatText" placeholder="${S.allowChat || S.isHost ? 'Введите сообщение… (Enter — отправить)' : 'Чат отключён организатором'}" ${S.allowChat || S.isHost ? '' : 'disabled'}></textarea><button class="btn-gradient" id="chatSend" style="padding:0 14px">${icon('send')}</button></div></div>`;
      }
      if (S.panel === 'polls') {
        body = S.polls.length ? S.polls.map((p, i) => `<div class="poll" data-poll="${i}"><h4>${esc(p.q)}</h4>${p.opts.map((o, j) => { const total = p.votes.reduce((a, b) => a + b, 0) || 1; const pct = Math.round(p.votes[j] / total * 100); return `<div class="opt ${p.my === j ? 'voted' : ''}" data-vote="${j}"><div class="lbl"><span>${esc(o)}</span><span>${p.votes[j]} · ${pct}%</span></div><div class="bar"><i style="width:${pct}%"></i></div></div>`; }).join('')}<div class="poll-foot"><span>${p.votes.reduce((a, b) => a + b, 0)} голосов · ${p.anon ? 'анонимно' : 'открыто'} · ${p.open ? 'идёт' : 'завершён'}</span>${S.isHost ? `<button class="btn-ghost btn-sm" data-pollend="${i}">${p.open ? 'Завершить' : 'Поделиться итогами'}</button>` : ''}</div></div>`).join('') : `<div class="empty">${icon('poll')}Опросов пока нет${S.isHost ? '. Создайте первый — участники проголосуют прямо во встрече' : ''}</div>`;
        foot = S.isHost ? `<button class="btn-gradient btn-sm" data-pa="newPoll">${icon('plus')} Создать опрос</button><button class="btn-ghost btn-sm" data-pa="quiz">${icon('sparkles')} Викторина по задаче</button>` : '';
      }
      if (S.panel === 'rooms') {
        body = S.rooms.length ? S.rooms.map((r, i) => `<div class="br-room"><h4>${esc(r.name)} <span class="tag ${r.open ? 'ok' : ''}">${r.open ? 'открыт' : 'закрыт'}</span></h4><div class="members">${S.participants.filter(p => p.room === i + 1).map(p => `<span>${esc(p.name)}</span>`).join('') || '<span class="muted">пусто</span>'}</div><div style="display:flex;gap:6px;margin-top:8px"><button class="btn-ghost btn-sm" data-join="${i}">Войти</button>${S.isHost ? `<button class="btn-ghost btn-sm" data-bcast="${i}">Сообщение</button>` : ''}</div></div>`).join('') : `<div class="empty">${icon('split')}Сессионные залы не созданы${S.isHost ? '. Разделите участников на малые группы для работы над задачами' : ''}</div>`;
        foot = S.isHost ? (S.rooms.length ? `<button class="btn-gradient btn-sm" data-pa="openRooms">${S.rooms[0].open ? 'Закрыть все залы' : 'Открыть все залы'}</button><button class="btn-ghost btn-sm" data-pa="recreate">${icon('split')} Пересоздать</button><button class="btn-ghost btn-sm" data-pa="bcastAll">${icon('bell')} Всем залам</button>` : `<button class="btn-gradient btn-sm" data-pa="createRooms">${icon('plus')} Создать залы</button>`) : '';
      }
      sp.innerHTML = `<div class="side-head"><span>${tabs.find(t => t[0] === S.panel)[1]}</span><button class="btn-icon" data-close>${icon('x')}</button></div>
        <div class="side-tabs">${tabs.map(([k, l]) => `<button class="${S.panel === k ? 'active' : ''}" data-tab="${k}">${l.replace(/\s\(.*\)/, '')}</button>`).join('')}</div>
        <div class="side-body">${body}</div>${foot ? `<div class="side-foot">${foot}</div>` : ''}`;
      sp.querySelector('[data-close]').addEventListener('click', () => { S.panel = null; this.renderRoom(); });
      sp.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { S.panel = b.dataset.tab; if (S.panel === 'chat') S.unread = 0; this.renderRoom(); }));
      sp.querySelectorAll('[data-pmenu]').forEach(b => b.addEventListener('click', () => this.participantMenu(b.dataset.pmenu, b)));
      sp.querySelectorAll('[data-admit]').forEach(b => b.addEventListener('click', () => this.admit(b.dataset.admit)));
      sp.querySelectorAll('[data-deny]').forEach(b => b.addEventListener('click', () => { S.waiting = S.waiting.filter(w => w.id !== b.dataset.deny); toast('Участнику отказано во входе'); this.renderRoom(); }));
      const aa = sp.querySelector('[data-admitall]'); aa && aa.addEventListener('click', () => [...S.waiting].forEach(w => this.admit(w.id)));
      sp.querySelectorAll('[data-pa]').forEach(b => b.addEventListener('click', () => this.panelAction(b.dataset.pa)));
      sp.querySelectorAll('[data-vote]').forEach(o => o.addEventListener('click', () => { const pi = +o.closest('.poll').dataset.poll, j = +o.dataset.vote, p = S.polls[pi]; if (!p.open) return; if (p.my != null) p.votes[p.my]--; p.my = j; p.votes[j]++; this.renderPanel(); }));
      sp.querySelectorAll('[data-pollend]').forEach(b => b.addEventListener('click', () => { const p = S.polls[+b.dataset.pollend]; if (p.open) { p.open = false; toast('Опрос завершён'); } else { S.chat.push({ sys: true, text: `Итоги опроса «${p.q}»: ` + p.opts.map((o, j) => `${o} — ${p.votes[j]}`).join(', ') }); toast('Итоги отправлены в чат', 'ok'); } this.renderPanel(); }));
      sp.querySelectorAll('[data-join]').forEach(b => b.addEventListener('click', () => { const r = S.rooms[+b.dataset.join]; if (!r.open) return toast('Зал ещё не открыт', 'bad'); toast(`Вы перешли в «${r.name}». Нажмите «Выйти», чтобы вернуться в основной зал`, 'ok', 4000); S.topic = `${r.name} · ${S.topic.split(' · ').pop()}`; this.renderRoom(); }));
      sp.querySelectorAll('[data-bcast]').forEach(b => b.addEventListener('click', () => { const t = prompt('Сообщение для зала'); if (t) toast('Сообщение отправлено в зал', 'ok'); }));
      if (S.panel === 'chat') this.bindChat(sp);
    },
    admit(id) {
      const S = this.S; const w = S.waiting.find(x => x.id === id); if (!w) return;
      S.waiting = S.waiting.filter(x => x !== w);
      S.participants.push({ id: w.id, name: w.name, initials: w.initials, color: w.color, solid: SIM.solid[rnd(0, 7)], mic: !S.muteOnEntry, cam: Math.random() > .4, hand: false, speaking: false });
      S.chat.push({ sys: true, text: `${w.name} присоединился к встрече` });
      const al = this.layer.querySelector('.room-alert'); al && al.remove();
      toast(`${w.name} впущен во встречу`, 'ok'); this.renderRoom();
    },
    panelAction(a) {
      const S = this.S;
      if (a === 'invite') this.infoModal();
      if (a === 'muteAll') { S.participants.forEach(p => p.mic = false); toast('Звук выключен у всех'); }
      if (a === 'lowerAll') { S.participants.forEach(p => p.hand = false); S.hand = false; }
      if (a === 'newPoll') return this.pollModal();
      if (a === 'quiz') { S.polls.unshift({ q: 'Задача 5: чему равен угол ∠BAC, если ∠BOC = 100°?', opts: ['40°', '50°', '80°', '100°'], votes: [1, 2, 0, 0], my: null, anon: false, open: true }); toast('Викторина запущена', 'ok'); this.simVotes(); }
      if (a === 'createRooms') return this.roomsModal();
      if (a === 'recreate') return this.roomsModal();
      if (a === 'openRooms') { const open = !S.rooms[0].open; S.rooms.forEach(r => r.open = open); S.chat.push({ sys: true, text: open ? 'Сессионные залы открыты. Участники распределены' : 'Сессионные залы закрыты, все возвращаются в основной зал' }); if (!open) S.participants.forEach(p => p.room = null); toast(open ? 'Залы открыты' : 'Залы закрыты'); }
      if (a === 'bcastAll') { const t = prompt('Сообщение всем залам'); if (t) { S.chat.push({ sys: true, text: `📢 Всем залам: ${t}` }); toast('Отправлено во все залы', 'ok'); } }
      this.renderRoom();
    },
    pollModal() {
      const S = this.S;
      App.modal('Новый опрос', `<label class="field">Вопрос<input type="text" id="pq" placeholder="Например: какой метод подходит для задачи 3?"></label>
        <div id="popts" style="display:grid;gap:8px"><input type="text" placeholder="Вариант 1"><input type="text" placeholder="Вариант 2"></div>
        <button class="btn-ghost btn-sm" id="paddopt" type="button">${icon('plus')} Добавить вариант</button>
        <label class="check"><input type="checkbox" id="panon"> Анонимное голосование</label>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Запустить', cls: 'btn-gradient', act: 'ok' }], m => {
        $('#paddopt', m).addEventListener('click', () => { const i = document.createElement('input'); i.type = 'text'; i.placeholder = 'Вариант ' + ($('#popts', m).children.length + 1); $('#popts', m).appendChild(i); });
      }, () => {
        const q = $('#pq').value.trim(); const opts = [...$('#popts').querySelectorAll('input')].map(i => i.value.trim()).filter(Boolean);
        if (!q || opts.length < 2) return toast('Нужен вопрос и минимум два варианта', 'bad');
        S.polls.unshift({ q, opts, votes: opts.map(() => 0), my: null, anon: $('#panon').checked, open: true });
        S.chat.push({ sys: true, text: `Организатор запустил опрос: «${q}»` }); toast('Опрос запущен', 'ok'); this.simVotes(); this.renderRoom();
      });
    },
    simVotes() {
      const S = this.S, p = S.polls[0];
      S.participants.forEach((_, i) => setTimeout(() => { if (p.open) { p.votes[rnd(0, p.opts.length - 1)]++; if (S.panel === 'polls') this.renderPanel(); } }, 1500 + i * 1800));
    },
    roomsModal() {
      const S = this.S;
      App.modal('Сессионные залы', `<div class="field-row"><label class="field">Количество залов<input type="number" id="brN" value="2" min="1" max="10"></label><label class="field">Распределение<select id="brMode"><option value="auto">Автоматически</option><option value="manual">Вручную</option><option value="self">Участники выбирают сами</option></select></label></div>
        <div class="field-row"><label class="field">Автозакрытие через, мин<input type="number" id="brT" value="15" min="0"></label><label class="field">Обратный отсчёт при закрытии, сек<input type="number" id="brC" value="60" min="0"></label></div>
        <label class="check"><input type="checkbox" id="brRet" checked> Разрешить возврат в основной зал в любое время</label>`, [{ label: 'Отмена', cls: 'btn-ghost', act: 'close' }, { label: 'Создать', cls: 'btn-gradient', act: 'ok' }], null, () => {
        const n = Math.max(1, Math.min(10, +$('#brN').value || 2));
        S.rooms = Array.from({ length: n }, (_, i) => ({ name: `Зал ${i + 1}`, open: false }));
        if ($('#brMode').value === 'auto') S.participants.forEach((p, i) => p.room = (i % n) + 1); else S.participants.forEach(p => p.room = null);
        toast(`Создано залов: ${n}`, 'ok'); this.renderRoom();
      });
    },
    bindChat(sp) {
      const S = this.S, ta = $('#chatText', sp), list = $('#chatList', sp);
      if (list) list.parentElement.scrollTop = list.parentElement.scrollHeight;
      $('#chatTo', sp).addEventListener('change', e => S.chatTo = e.target.value);
      const send = () => {
        const t = ta.value.trim(); if (!t) return;
        const to = S.chatTo, toP = S.participants.find(p => p.id === to);
        S.chat.push({ from: S.name, me: true, initials: App.user.initials, color: App.user.color, text: t, time: now(), to, toName: toP ? toP.name : '' });
        ta.value = ''; this.renderPanel();
        if (toP) setTimeout(() => { this.incomingChat(toP, ['Ок, понял', 'Спасибо!', 'Хорошо, сделаю', 'Да, конечно'][rnd(0, 3)], 'me', S.name); }, 2500);
      };
      $('#chatSend', sp).addEventListener('click', send);
      ta && ta.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
      $('#chatFile', sp).addEventListener('change', e => { const f = e.target.files[0]; if (f) { S.chat.push({ from: S.name, me: true, initials: App.user.initials, color: App.user.color, file: `${f.name} · ${(f.size / 1024).toFixed(0)} КБ`, time: now(), to: S.chatTo }); this.renderPanel(); } });
      $('#chatEmoji', sp).addEventListener('click', e => { this.popover(e.currentTarget, `<div class="emoji-row">${['😀', '👍', '❤️', '🎉', '🤔', '👏', '🔥', '✅', '📐', '📏', '✏️', '🧮'].map(x => `<button data-e="${x}">${x}</button>`).join('')}</div>`, m => m.querySelectorAll('[data-e]').forEach(b => b.addEventListener('click', () => { ta.value += b.dataset.e; this.closePop(); ta.focus(); }))); e.currentTarget.closest('.chat-input').style.position = 'relative'; });
      ta && ta.focus();
    },
    incomingChat(p, text, to = 'all', toName = '') {
      const S = this.S;
      S.chat.push({ from: p.name, initials: p.initials, color: p.color, text, time: now(), to, toName });
      if (S.panel !== 'chat') { S.unread++; this.renderToolbar(); } else this.renderPanel();
    },

    /* ---------- клавиатура ---------- */
    keys(e) {
      const S = this.S; if (!S || !S.joined || S.ended) return;
      if (e.target.matches('input, textarea, [contenteditable]')) return;
      if (e.altKey) {
        const map = { a: 'mic', v: 'cam', s: 'share', r: 'record', h: 'panel:chat', u: 'panel:participants', y: 'hand', w: 'whiteboard', c: 'captions', f: 'fullscreen' };
        const k = e.key.toLowerCase(); const ru = { 'ф': 'a', 'м': 'v', 'ы': 's', 'к': 'r', 'р': 'h', 'г': 'u', 'н': 'y', 'ц': 'w', 'с': 'c', 'а': 'f' };
        const a = map[k] || map[ru[k]]; if (a) { e.preventDefault(); this.action(a); }
      }
      if (e.key === 'Escape') { this.closePop(); this.layer.classList.remove('focus-mode'); if (S.panel) { S.panel = null; this.renderRoom(); } }
      if (e.code === 'Space' && !S.mic && !e.repeat) { S.ptt = true; if (S.stream) S.stream.getAudioTracks().forEach(t => t.enabled = true); toast('Микрофон включён, пока удерживаете пробел'); document.onkeyup = ev => { if (ev.code === 'Space' && S.ptt) { S.ptt = false; if (S.stream) S.stream.getAudioTracks().forEach(t => t.enabled = false); } }; }
    },

    /* ---------- имитация активности ---------- */
    startSimulation() {
      const S = this.S;
      this.timers.push(setInterval(() => {
        if (S.ended) return;
        S.participants.forEach(p => p.speaking = false);
        const talkers = S.participants.filter(p => p.mic);
        if (talkers.length && Math.random() < .8) { const p = talkers[rnd(0, talkers.length - 1)]; p.speaking = true; if (S.captions && Math.random() < .5) this.caption(p.name, SIM.captionLines[rnd(0, SIM.captionLines.length - 1)]); }
        this.layer.querySelectorAll('.tile-v').forEach(t => { const p = S.participants.find(x => x.id === t.dataset.id); if (p) t.classList.toggle('speaking', p.speaking); });
        if (S.view === 'speaker' && !S.pinned && !S.spotlight && !S.sharing && !S.wbShared) this.renderStage();
      }, 2600));
      this.timers.push(setInterval(() => {
        if (S.ended || !S.participants.length) return;
        const p = S.participants[rnd(0, S.participants.length - 1)];
        if (S.allowChat) this.incomingChat(p, SIM.chatLines[rnd(0, SIM.chatLines.length - 1)]);
      }, 24000));
      this.timers.push(setInterval(() => { if (S.ended || !S.participants.length) return; const p = S.participants[rnd(0, S.participants.length - 1)]; this.react(p.id, ['👍', '👏', '❤️', '🎉', '😂'][rnd(0, 4)]); }, 17000));
      this.timers.push(setInterval(() => { if (S.ended || !S.participants.length || Math.random() < .5) return; const p = S.participants[rnd(0, S.participants.length - 1)]; p.hand = !p.hand; if (p.hand) toast(`${p.name} поднял(а) руку`); this.renderStage(); this.renderToolbar(); if (S.panel === 'participants') this.renderPanel(); }, 31000));
      this.timers.push(setTimeout(() => this.knock(), 15000));
      this.timers.push(setInterval(() => { if (!S.ended && Math.random() < .5) this.knock(); }, 70000));
      const typ = setInterval(() => { const t = $('#typing', this.layer); if (t && S.participants.length && Math.random() < .3) { t.textContent = `${S.participants[rnd(0, S.participants.length - 1)].name.split(' ')[0]} печатает…`; setTimeout(() => { if (t) t.textContent = ''; }, 3000); } }, 9000); this.timers.push(typ);
    },
    knock() {
      const S = this.S; if (S.ended || S.locked) return;
      const used = new Set([...S.participants, ...S.waiting].map(p => p.name)); const name = SIM.waitingNames.find(n => !used.has(n)); if (!name) return;
      const w = { id: 'w' + Date.now(), name, initials: SIM.initials(name), color: SIM.palette[rnd(0, 7)] };
      if (!S.waitingRoom) { S.waiting.push(w); this.admit(w.id); return; }
      S.waiting.push(w); this.renderToolbar(); if (S.panel === 'participants') this.renderPanel();
      const st = $('#stage', this.layer); if (!st) return;
      const al = document.createElement('div'); al.className = 'room-alert';
      al.innerHTML = `<span class="avatar avatar-sm" style="background:${w.color}">${w.initials}</span><span class="p-name">${esc(name)} ждёт в зале ожидания</span>${S.isHost ? `<button class="btn-gradient btn-sm" data-admit="${w.id}">Впустить</button>` : ''}<button class="btn-ghost btn-sm" data-a="panel:participants">Показать</button><button class="btn-icon" data-x>${icon('x')}</button>`;
      st.appendChild(al);
      al.querySelector('[data-admit]') && al.querySelector('[data-admit]').addEventListener('click', () => this.admit(w.id));
      al.querySelector('[data-a]').addEventListener('click', () => { S.panel = 'participants'; this.renderRoom(); });
      al.querySelector('[data-x]').addEventListener('click', () => al.remove());
      setTimeout(() => al.remove(), 12000);
    },

    /* =============== ВЫХОД =============== */
    end(forAll) {
      const S = this.S; S.ended = true;
      if (S.recording) this.stopRecording();
      if (S.displayStream) S.displayStream.getTracks().forEach(t => t.stop());
      if (S.rec) { S.rec.onend = null; try { S.rec.stop(); } catch (e) { } }
      this.timers.forEach(t => { clearInterval(t); clearTimeout(t); }); this.timers = [];
      document.onkeydown = null; document.onkeyup = null;
      if (S.wb) S.wb.destroy();
      const mins = Math.max(1, Math.round(S.secs / 60));
      App.history.unshift({ topic: S.topic, date: new Date(), dur: fmtTime(S.secs), participants: S.participants.length + 1 });
      this.layer.innerHTML = `<div class="ended">
        <span class="avatar avatar-xl" style="background:var(--grad)">${icon('check')}</span>
        <h2>${forAll ? 'Встреча завершена для всех' : 'Вы покинули встречу'}</h2>
        <p class="muted">«${esc(S.topic)}» · ${fmtTime(S.secs)} · ${S.participants.length + 1} участник(ов)${App.recordings.length && App.recordings[0].blob ? ' · запись сохранена' : ''}</p>
        <p style="margin-top:10px;font-weight:700">Как прошла встреча?</p>
        <div class="stars">${[1, 2, 3, 4, 5].map(i => `<button data-star="${i}">⭐</button>`).join('')}</div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin-top:10px">
          <button class="btn-gradient" data-a="home">На главную</button>
          ${App.recordings[0] && App.recordings[0].blob ? `<button class="btn-ghost" data-a="rec">${icon('play')} Открыть запись</button>` : ''}
          <button class="btn-ghost" data-a="rejoin">${icon('video')} Подключиться снова</button>
        </div></div>`;
      this.layer.querySelectorAll('[data-star]').forEach(b => b.addEventListener('click', () => { this.layer.querySelectorAll('[data-star]').forEach(x => x.classList.toggle('on', +x.dataset.star <= +b.dataset.star)); toast('Спасибо за оценку!', 'ok'); }));
      this.layer.querySelectorAll('[data-a]').forEach(b => b.addEventListener('click', () => { const a = b.dataset.a; if (a === 'rejoin') { const o = { id: S.id, topic: S.topic, host: S.isHost, pw: S.pw }; this.close(); this.open(o); } else { this.close(); location.hash = a === 'rec' ? '#/recordings' : '#/home'; } }));
      if (S.stream) S.stream.getTracks().forEach(t => t.stop()); S.stream = null;
      if (S.audioCtx) S.audioCtx.close().catch(() => { });
    },
    close() {
      const S = this.S;
      if (S) { if (S.stream) S.stream.getTracks().forEach(t => t.stop()); if (S.displayStream) S.displayStream.getTracks().forEach(t => t.stop()); if (S.wb) S.wb.destroy(); if (S.audioCtx) S.audioCtx.close().catch(() => { }); }
      this.timers.forEach(t => { clearInterval(t); clearTimeout(t); }); this.timers = [];
      document.onkeydown = null; document.onkeyup = null;
      this.layer.classList.add('hidden'); this.layer.classList.remove('mini-mode'); this.layer.innerHTML = '';
      document.body.classList.remove('in-meeting'); this.S = null;
    },
  };
  window.Meeting = M;
})();
