/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;
  Object.assign(window.Whiteboard.prototype, {
    build() {
      const r = this.root;
      r.classList.add('wb', 'wb-v2'); if (this.overlay) r.classList.add('wb-annot');
      const toolBtn = ([t, i, title]) => `<button class="wb-tool${t === this.tool ? ' active' : ''}" data-tool="${t}" title="${esc(title)}">${ic(i)}</button>`;
      r.innerHTML = `
        <div class="wb-top">
          <div class="wb-title">${this.overlay ? `${ic('pen')} <span class="wb-annot-label">${esc(this.title)}</span>` : `${ic('board')} <input type="text" value="${esc(this.title)}" aria-label="Название доски" title="Название доски">`}
            ${this.overlay ? `<button class="wb-tool" data-act="hide" title="Скрыть панель (рисунок останется)">${ic('chevUp')}</button>` : ''}
            ${this.overlay && this.opts.onClose ? `<button class="wb-tool" data-act="close" title="Завершить комментирование">${ic('x')}</button>` : ''}
          </div>
          <div class="wb-tools">
            ${TOOL_GROUPS.map(g => `<div class="wb-group">${g.map(toolBtn).join('')}</div>`).join('')}
            <span class="wb-sep"></span>
            <div class="wb-colors" title="Цвет">
              ${COLORS.map((c, i) => `<button class="wb-color${i === 0 ? ' active' : ''}" data-color="${c}" style="background:${c}" title="Цвет ${c}" aria-label="Цвет ${c}"></button>`).join('')}
              <label class="wb-color" style="background:conic-gradient(red,yellow,lime,cyan,blue,magenta,red)" title="Свой цвет"><input type="color" class="wb-custom" value="#0f172a"></label>
            </div>
            <span class="wb-sep"></span>
            <div class="wb-sizes" title="Толщина линии / размер текста">
              ${SIZES.map((s, i) => `<button class="wb-size${i === 1 ? ' active' : ''}" data-size="${s}" title="Толщина ${s}"><i style="width:${4 + i * 4}px;height:${4 + i * 4}px"></i></button>`).join('')}
            </div>
            <button class="wb-tool" data-act="fill" title="Заливка фигур (F)">${ic('fill')}</button>
            <span class="wb-sep"></span>
            <button class="wb-tool" data-act="undo" title="Отменить (Ctrl+Z)">${ic('undo')}</button>
            <button class="wb-tool" data-act="redo" title="Повторить (Ctrl+Y)">${ic('redo')}</button>
            <button class="wb-tool" data-act="clear" title="Очистить страницу (можно отменить)">${ic('trash')}</button>
            <span class="wb-sep"></span>
            <button class="wb-tool" data-act="menu" title="Меню: шаблоны, фон, страницы, файл">${ic('more')}</button>
            ${!this.overlay && this.opts.onClose ? `<button class="wb-tool" data-act="close" title="Закрыть доску">${ic('x')}</button>` : ''}
          </div>
        </div>
        <div class="wb-sub">
          <span class="wb-sub-eraser">
            <label>Размер <input type="range" min="4" max="80" step="1" value="${this.eraserSize}" class="wb-eraser-range"> <b class="wb-eraser-val">${this.eraserSize * 2}px</b></label>
            <i class="wb-eraser-preview" style="width:${Math.min(36, this.eraserSize)}px;height:${Math.min(36, this.eraserSize)}px"></i>
            <span class="wb-seg"><button data-emode="stroke" class="active" title="Стирается только задетая часть линии">Штрих</button><button data-emode="object" title="Удаляется вся фигура, которой коснулись">Объект</button></span>
            <span class="wb-sub-note">[ и ] — размер · Ctrl+Z — вернуть</span>
          </span>
          <span class="wb-sub-note-color"><label>Цвет стикера</label><span class="wb-palette wb-note-palette show">${NOTE_COLORS.map((c, i) => `<button data-note-color="${c}" class="${i === 0 ? 'active' : ''}" style="background:${c}" title="Цвет стикера"></button>`).join('')}</span></span>
          <span class="wb-sub-stamp"><label>Эмодзи</label><span class="wb-palette wb-stamp-palette show">${STAMPS.map((e, i) => `<button data-stamp="${e}" class="${i === 0 ? 'active' : ''}">${e}</button>`).join('')}</span></span>
        </div>
        <div class="wb-canvas-wrap ${this.bg} tool-${this.tool}">
          <canvas></canvas>
          <div class="wb-eraser-cursor"></div>
          <div class="wb-cursors"></div>
          <div class="wb-dropzone">Отпустите, чтобы добавить изображение или открыть .json</div>
        </div>
        <div class="wb-bottom">
          <div class="wb-pages"></div>
          <div class="wb-status"></div>
          <div class="wb-collab"></div>
          <div class="wb-zoom">
            <button data-act="zoomOut" title="Уменьшить (−)">${ic('zoomOut')}</button>
            <span class="wb-zoom-val" title="Сбросить масштаб (0)">100%</span>
            <button data-act="zoomIn" title="Увеличить (+)">${ic('zoomIn')}</button>
            <button data-act="fit" title="Показать всё (Shift+1)">${ic('fit')}</button>
            <button data-act="zoomReset" title="Сбросить масштаб (0)">${ic('maximize')}</button>
          </div>
        </div>
        <div class="wb-toast"></div>`;
      this.canvas = r.querySelector('canvas');
      this.ctx = this.canvas.getContext('2d');
      this.wrap = r.querySelector('.wb-canvas-wrap');
      this.cursorsEl = r.querySelector('.wb-cursors');
      this.eraserEl = r.querySelector('.wb-eraser-cursor');
      this.subEl = r.querySelector('.wb-sub');
      this.toastEl = r.querySelector('.wb-toast');
      this.renderPages();
      this.renderCollab();
      this.updateZoomLabel();
    },
    bind() {
      const r = this.root;
      const ti = r.querySelector('.wb-title input'); if (ti) ti.addEventListener('input', e => { this.title = e.target.value; this.commit(); });
      r.querySelectorAll('[data-tool]').forEach(b => b.addEventListener('click', () => this.setTool(b.dataset.tool)));
      r.querySelectorAll('.wb-color[data-color]').forEach(b => b.addEventListener('click', () => this.setColor(b.dataset.color)));
      r.querySelector('.wb-custom').addEventListener('input', e => this.setColor(e.target.value, true));
      r.querySelectorAll('[data-size]').forEach(b => b.addEventListener('click', () => {
        this.size = +b.dataset.size;
        r.querySelectorAll('[data-size]').forEach(x => x.classList.toggle('active', x === b));
        if (this.sel.length) { this.pushUndo(); this.sel.forEach(s => { s.size = this.size; if (s.type === 'text') this.fitText(s); }); this.commit(); this.render(); }
      }));
      r.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', e => this.action(b.dataset.act, e)));
      r.querySelector('.wb-zoom-val').addEventListener('click', () => this.action('zoomReset'));
      r.querySelectorAll('[data-note-color]').forEach(b => b.addEventListener('click', () => {
        this.noteColor = b.dataset.noteColor;
        r.querySelectorAll('[data-note-color]').forEach(x => x.classList.toggle('active', x === b));
        const notes = this.sel.filter(s => s.type === 'note');
        if (notes.length) { this.pushUndo(); notes.forEach(s => { s.noteColor = this.noteColor; }); this.commit(); this.render(); }
      }));
      r.querySelectorAll('[data-stamp]').forEach(b => b.addEventListener('click', () => {
        this.stamp = b.dataset.stamp;
        r.querySelectorAll('[data-stamp]').forEach(x => x.classList.toggle('active', x === b));
      }));
      r.querySelector('.wb-eraser-range').addEventListener('input', e => this.setEraserSize(+e.target.value, true));
      r.querySelectorAll('[data-emode]').forEach(b => b.addEventListener('click', () => {
        this.eraserMode = b.dataset.emode;
        r.querySelectorAll('[data-emode]').forEach(x => x.classList.toggle('active', x === b));
        this.setHint();
      }));
      const c = this.canvas;
      c.addEventListener('pointerdown', e => this.down(e));
      c.addEventListener('pointermove', e => this.move(e));
      c.addEventListener('pointerup', e => this.up(e));
      c.addEventListener('pointercancel', e => this.up(e));
      c.addEventListener('lostpointercapture', e => { if (this.pointers.has(e.pointerId)) this.up(e); });
      c.addEventListener('pointerenter', e => { this.lastMouse = { x: e.offsetX, y: e.offsetY }; if (this.tool === 'eraser') { this.eraserPos = this.lastMouse; this.showEraser(this.erasing); } });
      c.addEventListener('pointerleave', () => { if (!this.erasing) this.hideEraser(); if (!this.laserOn) this.hideLaser(); });
      c.addEventListener('contextmenu', e => e.preventDefault());
      c.addEventListener('wheel', e => this.wheel(e), { passive: false });
      c.addEventListener('dblclick', e => this.dblclick(e));
      this.keyHandler = e => this.onKey(e);
      this.keyUpHandler = e => { if (e.code === 'Space') { this.spaceDown = false; this.wrap.classList.remove('space-pan'); } };
      document.addEventListener('keydown', this.keyHandler);
      document.addEventListener('keyup', this.keyUpHandler);
      const inField = e => e.target && e.target.matches && e.target.matches('input, textarea, select, [contenteditable]');
      this.pasteHandler = e => {
        if (!this.root.isConnected || inField(e)) return;
        const items = e.clipboardData && e.clipboardData.items; if (!items) return;
        const item = Array.from(items).find(it => it.kind === 'file' && it.type && it.type.startsWith('image/'));
        if (!item) {
          const text = e.clipboardData.getData('text/plain') || '';
          if (text.startsWith('FORMYLA-WB:')) { e.preventDefault(); this.pasteShapes(text, true); }
          else if (text.trim()) {
            e.preventDefault(); this.pushUndo();
            const m = this.lastMouse || this.viewCenter();
            const c0 = this.toWorld(m.x, m.y);
            const sh = { id: uid(), type: 'text', x1: c0.x, y1: c0.y, x2: c0.x + 10, y2: c0.y + 10, text: text.trim().slice(0, 4000), color: this.color, size: this.size };
            this.fitText(sh); this.shapes.push(sh); this.setTool('move'); this.sel = [sh]; this.commit(); this.render();
          }
          return;
        }
        const file = item.getAsFile(); if (!file) return;
        e.preventDefault(); this.readImageFile(file);
      };
      this.copyHandler = e => { if (!this.root.isConnected || inField(e)) return; this.copySel(e); };
      this.cutHandler = e => { if (!this.root.isConnected || inField(e)) return; this.cutSel(e); };
      document.addEventListener('paste', this.pasteHandler);
      document.addEventListener('copy', this.copyHandler);
      document.addEventListener('cut', this.cutHandler);
      ['dragenter', 'dragover'].forEach(ev => this.wrap.addEventListener(ev, e => { e.preventDefault(); this.root.classList.add('dragover'); }));
      this.wrap.addEventListener('dragleave', e => { if (e.target === this.wrap) this.root.classList.remove('dragover'); });
      this.wrap.addEventListener('drop', e => {
        e.preventDefault(); this.root.classList.remove('dragover');
        const rect = this.wrap.getBoundingClientRect(); this.lastMouse = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        Array.from(e.dataTransfer.files || []).forEach(f => {
          if (f.type.startsWith('image/')) this.readImageFile(f);
          else if (/\.json$/i.test(f.name)) this.importJson(f);
        });
      });
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(this.wrap);
    },
    destroy() {
      document.removeEventListener('keydown', this.keyHandler);
      document.removeEventListener('keyup', this.keyUpHandler);
      document.removeEventListener('paste', this.pasteHandler);
      document.removeEventListener('copy', this.copyHandler);
      document.removeEventListener('cut', this.cutHandler);
      this.ro && this.ro.disconnect();
      clearTimeout(this._saveT); clearTimeout(this._toastT);
      if (this.opts.storageKey) this.saveLocal();
    },
    say(msg, kind = 'ok', ms = 2600) {
      if (typeof window.toast === 'function') { try { window.toast(msg, kind, ms); return; } catch (e) { } }
      const el = this.toastEl; if (!el) return;
      el.textContent = msg; el.className = 'wb-toast show' + (kind === 'bad' ? ' bad' : '');
      clearTimeout(this._toastT); this._toastT = setTimeout(() => el.classList.remove('show'), ms);
    },
    setHint(extra) {
      const el = this.root.querySelector('.wb-status'); if (!el) return;
      let h = HINTS[this.tool] || '';
      if (this.tool === 'eraser' && this.eraserMode === 'object') h = 'Коснитесь фигуры — она удалится целиком. «Штрих» — стирать только часть линии. [ и ] — размер';
      el.innerHTML = `<b>${esc(TOOL_NAMES[this.tool] || this.tool)}</b> · ${esc(extra || h)}`;
    },
    setTool(t) {
      if (this.editing || this.finishText) this.finishText && this.finishText();
      this.tool = t;
      this.root.querySelectorAll('[data-tool]').forEach(x => x.classList.toggle('active', x.dataset.tool === t));
      this.wrap.className = `wb-canvas-wrap ${this.bg} tool-${t}` + (this.spaceDown ? ' space-pan' : '');
      this.wrap.style.cursor = '';
      const sub = this.subEl;
      sub.querySelector('.wb-sub-eraser').style.display = t === 'eraser' ? '' : 'none';
      sub.querySelector('.wb-sub-note-color').style.display = t === 'note' ? '' : 'none';
      sub.querySelector('.wb-sub-stamp').style.display = t === 'stamp' ? '' : 'none';
      sub.classList.toggle('show', t === 'eraser' || t === 'note' || t === 'stamp');
      if (t !== 'move') { this.sel = []; this.marquee = null; }
      if (t === 'eraser') { if (this.lastMouse) { this.eraserPos = this.lastMouse; this.showEraser(false); } } else this.hideEraser();
      this.hideLaser();
      this.setHint();
      this.render();
    },
    setColor(c, custom) {
      this.color = c;
      this.root.querySelectorAll('.wb-color[data-color]').forEach(x => x.classList.toggle('active', !custom && x.dataset.color === c));
      if (this.sel.length) { this.pushUndo(); this.sel.forEach(x => { if (x.type !== 'image') x.color = c; }); this.commit(); this.render(); }
    },
    setEraserSize(v, fromRange) {
      this.eraserSize = clamp(Math.round(v), 4, 80);
      const rg = this.root.querySelector('.wb-eraser-range'); if (rg && !fromRange) rg.value = this.eraserSize;
      const val = this.root.querySelector('.wb-eraser-val'); if (val) val.textContent = this.eraserSize * 2 + 'px';
      const pv = this.root.querySelector('.wb-eraser-preview'); if (pv) { const d = Math.min(36, this.eraserSize); pv.style.width = pv.style.height = d + 'px'; }
      this.showEraser(this.erasing);
    },
    showEraser(down) {
      const el = this.eraserEl;
      if (this.tool !== 'eraser' || !this.eraserPos) { el.classList.remove('show'); return; }
      const d = this.eraserSize * 2;
      el.style.width = el.style.height = d + 'px';
      el.style.left = this.eraserPos.x + 'px'; el.style.top = this.eraserPos.y + 'px';
      el.classList.add('show'); el.classList.toggle('down', !!down);
    },
    hideEraser() { this.eraserPos = null; this.eraserEl.classList.remove('show'); },
    action(act, e) {
      switch (act) {
        case 'undo': return this.undo();
        case 'redo': return this.redo();
        case 'clear': return this.clearPage();
        case 'fill': {
          this.fill = !this.fill; this.root.querySelector('[data-act=fill]').classList.toggle('active', this.fill);
          const fillable = this.sel.filter(s => /^(rect|ellipse|triangle|diamond)$/.test(s.type));
          if (fillable.length) { this.pushUndo(); fillable.forEach(s => { s.fill = this.fill; }); this.commit(); this.render(); }
          return;
        }
        case 'zoomIn': { const c = this.viewCenter(); return this.zoomAt(1.2, c.x, c.y); }
        case 'zoomOut': { const c = this.viewCenter(); return this.zoomAt(1 / 1.2, c.x, c.y); }
        case 'zoomReset': this.zoom = 1; this.panX = 0; this.panY = 0; this.updateZoomLabel(); this.scheduleSave(); return this.render();
        case 'fit': return this.fitAll();
        case 'menu': return this.toggleMenu();
        case 'close': return this.opts.onClose && this.opts.onClose();
        case 'hide': {
          const top = this.root.querySelector('.wb-top'); const hidden = top.classList.toggle('collapsed');
          const b = e && e.currentTarget; if (b) { b.innerHTML = ic(hidden ? 'chevDown' : 'chevUp'); b.title = hidden ? 'Показать панель' : 'Скрыть панель (рисунок останется)'; }
          return;
        }
      }
    },
  });
})();
