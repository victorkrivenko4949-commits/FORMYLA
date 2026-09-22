/* whiteboard.js — интерактивная доска (canvas, векторные фигуры, страницы, зум, экспорт) */
(function () {
  const COLORS = ['#0f172a', '#ef4444', '#f59e0b', '#22c55e', '#38bdf8', '#8b5cf6', '#ec4899', '#ffffff'];
  const SIZES = [2, 4, 8, 14];
  const NOTE_COLORS = ['#fef08a', '#bbf7d0', '#bae6fd', '#e9d5ff', '#fecdd3'];

  class Whiteboard {
    constructor(root, opts = {}) {
      this.root = root;
      this.opts = opts;
      this.title = opts.title || 'Доска без названия';
      this.pages = [{ shapes: [], undo: [], redo: [] }];
      this.page = 0;
      this.tool = 'pen';
      this.color = COLORS[0];
      this.size = SIZES[1];
      this.fill = false;
      this.bg = opts.overlay ? 'clear' : 'dots';
      this.overlay = !!opts.overlay;   // режим аннотаций поверх демонстрации экрана
      this.zoom = 1; this.panX = 0; this.panY = 0;
      this.drawing = null;
      this.menuOpen = false;
      this.collab = opts.collaborators || [];
      this.build();
      this.bind();
      this.resize();
      this.render();
      if (this.collab.length) this.startCollabCursors();
    }

    get shapes() { return this.pages[this.page].shapes; }

    build() {
      const r = this.root;
      r.classList.add('wb'); if (this.overlay) r.classList.add('wb-annot');
      r.innerHTML = `
        <div class="wb-top">
          <div class="wb-title">${this.overlay ? `${icon('pen')} <span class="wb-annot-label">${this.title}</span>` : `${icon('board')} <input type="text" value="${this.title}" aria-label="Название доски">`}</div>
          <div class="wb-tools">
            <button class="wb-tool" data-tool="move" title="Перемещение / выделение (V)">${icon('cursor')}</button>
            <button class="wb-tool active" data-tool="pen" title="Перо (P)">${icon('pen')}</button>
            <button class="wb-tool" data-tool="highlighter" title="Маркер (H)">${icon('highlighter')}</button>
            <button class="wb-tool" data-tool="line" title="Линия (L)">${icon('line')}</button>
            <button class="wb-tool" data-tool="arrow" title="Стрелка (A)">${icon('arrow')}</button>
            <button class="wb-tool" data-tool="rect" title="Прямоугольник (R)">${icon('square')}</button>
            <button class="wb-tool" data-tool="ellipse" title="Эллипс (O)">${icon('circle')}</button>
            <button class="wb-tool" data-tool="triangle" title="Треугольник">${icon('triangle')}</button>
            <button class="wb-tool" data-tool="text" title="Текст (T)">${icon('type')}</button>
            <button class="wb-tool" data-tool="note" title="Стикер (N)">${icon('note')}</button>
            <button class="wb-tool" data-tool="eraser" title="Ластик (E)">${icon('eraser')}</button>
            <button class="wb-tool" data-tool="laser" title="Лазерная указка">${icon('laser')}</button>
            <span class="wb-sep"></span>
            <div class="wb-colors">
              ${COLORS.map((c, i) => `<button class="wb-color${i === 0 ? ' active' : ''}" data-color="${c}" style="background:${c}" title="${c}" aria-label="Цвет ${c}"></button>`).join('')}
              <label class="wb-color" style="background:conic-gradient(red,yellow,lime,cyan,blue,magenta,red)" title="Свой цвет"><input type="color" class="wb-custom" value="#0f172a"></label>
            </div>
            <span class="wb-sep"></span>
            <div class="wb-sizes">
              ${SIZES.map((s, i) => `<button class="wb-size${i === 1 ? ' active' : ''}" data-size="${s}" title="Толщина ${s}"><i style="width:${4 + i * 4}px;height:${4 + i * 4}px"></i></button>`).join('')}
            </div>
            <button class="wb-tool" data-act="fill" title="Заливка фигур">${icon('square').replace('fill="none"', 'fill="currentColor" fill-opacity=".25"')}</button>
            <span class="wb-sep"></span>
            <button class="wb-tool" data-act="undo" title="Отменить (Ctrl+Z)">${icon('undo')}</button>
            <button class="wb-tool" data-act="redo" title="Повторить (Ctrl+Y)">${icon('redo')}</button>
            <button class="wb-tool" data-act="clear" title="Очистить страницу">${icon('trash')}</button>
            <span class="wb-sep"></span>
            <button class="wb-tool" data-act="menu" title="Ещё">${icon('more')}</button>
            ${this.overlay ? `<button class="wb-tool" data-act="hide" title="Скрыть панель (рисунок останется)">${icon('chevUp')}</button>` : ''}
            ${this.opts.onClose ? `<button class="wb-tool" data-act="close" title="${this.overlay ? 'Завершить комментирование' : 'Закрыть доску'}">${icon('x')}</button>` : ''}
          </div>
        </div>
        <div class="wb-canvas-wrap ${this.bg}">
          <canvas></canvas>
          <div class="wb-cursors"></div>
        </div>
        <div class="wb-bottom">
          <div class="wb-pages"></div>
          <div class="wb-collab"></div>
          <div class="wb-zoom">
            <button data-act="zoomOut" title="Уменьшить">${icon('zoomOut')}</button>
            <span class="wb-zoom-val">100%</span>
            <button data-act="zoomIn" title="Увеличить">${icon('zoomIn')}</button>
            <button data-act="zoomReset" title="Сбросить масштаб">${icon('maximize')}</button>
          </div>
        </div>`;
      this.canvas = r.querySelector('canvas');
      this.ctx = this.canvas.getContext('2d');
      if (this.overlay) { const t = r.querySelector('.wb-title'); ['hide', 'close'].forEach(a => { const b = r.querySelector(`[data-act=${a}]`); if (b) t.appendChild(b); }); }
      this.wrap = r.querySelector('.wb-canvas-wrap');
      this.cursorsEl = r.querySelector('.wb-cursors');
      this.renderPages();
      this.renderCollab();
    }

    bind() {
      const r = this.root;
      const ti = r.querySelector('.wb-title input'); if (ti) ti.addEventListener('input', e => { this.title = e.target.value; });
      r.querySelectorAll('[data-tool]').forEach(b => b.addEventListener('click', () => this.setTool(b.dataset.tool)));
      r.querySelectorAll('.wb-color[data-color]').forEach(b => b.addEventListener('click', () => this.setColor(b.dataset.color)));
      r.querySelector('.wb-custom').addEventListener('input', e => this.setColor(e.target.value, true));
      r.querySelectorAll('[data-size]').forEach(b => b.addEventListener('click', () => {
        this.size = +b.dataset.size;
        r.querySelectorAll('[data-size]').forEach(x => x.classList.toggle('active', x === b));
      }));
      r.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', (e) => this.action(b.dataset.act, e)));

      const c = this.canvas;
      c.addEventListener('pointerdown', e => this.down(e));
      c.addEventListener('pointermove', e => this.move(e));
      c.addEventListener('pointerup', e => this.up(e));
      c.addEventListener('pointerleave', e => this.up(e));
      c.addEventListener('wheel', e => {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) {
          const f = e.deltaY < 0 ? 1.1 : 0.9;
          this.zoomAt(f, e.offsetX, e.offsetY);
        } else { this.panX -= e.deltaX; this.panY -= e.deltaY; this.render(); }
      }, { passive: false });
      c.addEventListener('dblclick', e => {
        if (this.tool !== 'text' && this.tool !== 'note') { this.startText(e, 'text'); }
      });

      this.keyHandler = e => {
        if (e.target.matches('input, textarea, [contenteditable]')) return;
        if (!this.root.isConnected) return;
        const k = e.key.toLowerCase();
        if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); e.shiftKey ? this.redo() : this.undo(); }
        else if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); this.redo(); }
        else if (!e.ctrlKey && !e.metaKey && !e.altKey) {
          const map = { v: 'move', p: 'pen', h: 'highlighter', l: 'line', a: 'arrow', r: 'rect', o: 'ellipse', t: 'text', n: 'note', e: 'eraser' };
          if (map[k]) this.setTool(map[k]);
          if (k === 'delete' || k === 'backspace') this.deleteSelected();
        }
      };
      document.addEventListener('keydown', this.keyHandler);
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(this.wrap);
    }

    destroy() {
      document.removeEventListener('keydown', this.keyHandler);
      this.ro && this.ro.disconnect();
      clearInterval(this.collabTimer);
    }

    setTool(t) {
      this.tool = t;
      this.root.querySelectorAll('[data-tool]').forEach(x => x.classList.toggle('active', x.dataset.tool === t));
      this.wrap.className = `wb-canvas-wrap ${this.bg} tool-${t}`;
      if (t !== 'move') { this.selected = null; this.render(); }
      this.hideLaser();
    }
    setColor(c, custom) {
      this.color = c;
      this.root.querySelectorAll('.wb-color[data-color]').forEach(x => x.classList.toggle('active', !custom && x.dataset.color === c));
      if (this.selected) { this.selected.color = c; this.render(); }
    }

    action(act, e) {
      switch (act) {
        case 'undo': return this.undo();
        case 'redo': return this.redo();
        case 'clear': return this.clearPage();
        case 'fill': this.fill = !this.fill; e.currentTarget.classList.toggle('active', this.fill); return;
        case 'zoomIn': return this.zoomAt(1.2, this.canvas.width / 2 / devicePixelRatio, this.canvas.height / 2 / devicePixelRatio);
        case 'zoomOut': return this.zoomAt(1 / 1.2, this.canvas.width / 2 / devicePixelRatio, this.canvas.height / 2 / devicePixelRatio);
        case 'zoomReset': this.zoom = 1; this.panX = 0; this.panY = 0; this.updateZoomLabel(); return this.render();
        case 'menu': return this.toggleMenu();
        case 'close': return this.opts.onClose && this.opts.onClose();
        case 'hide': { const top = this.root.querySelector('.wb-top'); const hidden = top.classList.toggle('collapsed'); e.currentTarget.innerHTML = icon(hidden ? 'chevDown' : 'chevUp'); e.currentTarget.title = hidden ? 'Показать панель' : 'Скрыть панель (рисунок останется)'; return; }
      }
    }

    toggleMenu() {
      const old = this.root.querySelector('.wb-menu');
      if (old) { old.remove(); return; }
      const m = document.createElement('div');
      m.className = 'wb-menu';
      m.innerHTML = (this.overlay ? '' : `
        <h5>Фон</h5>
        <button data-bg="plain">${icon('square')} Без сетки ${this.bg === 'plain' ? icon('check') : ''}</button>
        <button data-bg="grid">${icon('grid')} Клетка ${this.bg === 'grid' ? icon('check') : ''}</button>
        <button data-bg="dots">${icon('more')} Точки ${this.bg === 'dots' ? icon('check') : ''}</button>
        <hr>
        <h5>Страницы</h5>
        <button data-m="addPage">${icon('plus')} Добавить страницу</button>
        <button data-m="dupPage">${icon('copy')} Дублировать страницу</button>
        <button data-m="delPage" ${this.pages.length < 2 ? 'disabled' : ''}>${icon('trash')} Удалить страницу</button>
        <hr>`) + `
        <h5>Файл</h5>
        <button data-m="exportPng">${icon('image')} ${this.overlay ? 'Снимок экрана с пометками (PNG)' : 'Экспорт в PNG'}</button>
        <button data-m="exportJson">${icon('download')} Сохранить (.json)</button>
        <label>${icon('upload')} Открыть (.json)<input type="file" accept="application/json" class="sr-only"></label>
        <hr>
        <button data-m="shortcuts">${icon('keyboard')} Горячие клавиши</button>`;
      this.root.querySelector('.wb-top').appendChild(m);
      m.querySelectorAll('[data-bg]').forEach(b => b.addEventListener('click', () => { this.bg = b.dataset.bg; this.setTool(this.tool); m.remove(); }));
      m.querySelector('input[type=file]').addEventListener('change', ev => this.importJson(ev.target.files[0]));
      m.querySelectorAll('[data-m]').forEach(b => b.addEventListener('click', () => { this.menuAction(b.dataset.m); m.remove(); }));
      const off = ev => { if (!m.contains(ev.target) && !ev.target.closest('[data-act=menu]')) { m.remove(); document.removeEventListener('pointerdown', off); } };
      setTimeout(() => document.addEventListener('pointerdown', off), 0);
    }
    menuAction(a) {
      if (a === 'addPage') { this.pages.push({ shapes: [], undo: [], redo: [] }); this.page = this.pages.length - 1; }
      if (a === 'dupPage') { this.pages.splice(this.page + 1, 0, { shapes: JSON.parse(JSON.stringify(this.shapes)), undo: [], redo: [] }); this.page++; }
      if (a === 'delPage' && this.pages.length > 1) { this.pages.splice(this.page, 1); this.page = Math.max(0, this.page - 1); }
      if (a === 'exportPng') this.exportPng();
      if (a === 'exportJson') this.exportJson();
      if (a === 'shortcuts') window.toast && toast('V — выделение, P — перо, H — маркер, L — линия, A — стрелка, R — прямоугольник, O — эллипс, T — текст, N — стикер, E — ластик, Ctrl+Z / Ctrl+Y — отмена/повтор, Ctrl+колесо — масштаб, двойной клик — текст', 'ok', 9000);
      this.renderPages(); this.render();
    }
    renderPages() {
      const el = this.root.querySelector('.wb-pages');
      el.innerHTML = this.pages.map((_, i) => `<button class="${i === this.page ? 'active' : ''}" data-p="${i}">Стр. ${i + 1}</button>`).join('') + `<button data-p="add" title="Новая страница">${icon('plus')}</button>`;
      el.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
        if (b.dataset.p === 'add') this.menuAction('addPage'); else { this.page = +b.dataset.p; this.selected = null; this.renderPages(); this.render(); }
      }));
    }
    renderCollab() {
      const el = this.root.querySelector('.wb-collab');
      if (!this.collab.length) { el.innerHTML = `<span class="small" style="color:#64748b">Личная доска · изменения сохраняются в сессии</span>`; return; }
      el.innerHTML = this.collab.map(c => `<span class="avatar" style="background:${c.color}" title="${c.name}">${c.initials}</span>`).join('') + `<span style="margin-left:8px;font-weight:700">${this.collab.length + 1} на доске</span>`;
    }

    /* ---------- координаты ---------- */
    toWorld(x, y) { return { x: (x - this.panX) / this.zoom, y: (y - this.panY) / this.zoom }; }
    zoomAt(f, cx, cy) {
      const nz = Math.min(4, Math.max(0.25, this.zoom * f));
      const w = this.toWorld(cx, cy);
      this.zoom = nz;
      this.panX = cx - w.x * nz; this.panY = cy - w.y * nz;
      this.updateZoomLabel(); this.render();
    }
    updateZoomLabel() { this.root.querySelector('.wb-zoom-val').textContent = Math.round(this.zoom * 100) + '%'; }

    resize() {
      const rect = this.wrap.getBoundingClientRect();
      if (!rect.width) return;
      const dpr = window.devicePixelRatio || 1;
      this.canvas.width = rect.width * dpr; this.canvas.height = rect.height * dpr;
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.render();
    }

    /* ---------- ввод ---------- */
    down(e) {
      if (e.button === 1 || (e.button === 0 && e.altKey) || (this.tool === 'move' && !this.hitTest(this.toWorld(e.offsetX, e.offsetY)))) {
        this.panning = { x: e.offsetX, y: e.offsetY, px: this.panX, py: this.panY }; this.selected = null; this.render(); return;
      }
      this.canvas.setPointerCapture(e.pointerId);
      const p = this.toWorld(e.offsetX, e.offsetY);
      const t = this.tool;
      if (t === 'laser') { this.showLaser(e.offsetX, e.offsetY); this.laserOn = true; return; }
      if (t === 'text' || t === 'note') { this.startText(e, t); return; }
      if (t === 'eraser') { this.eraseAt(p); this.erasing = true; return; }
      if (t === 'move') {
        const s = this.hitTest(p);
        this.selected = s; this.dragging = s ? { start: p, orig: JSON.parse(JSON.stringify(s)) } : null; this.render(); return;
      }
      const base = { type: t, color: this.color, size: this.size, fill: this.fill, id: Date.now() + Math.random() };
      if (t === 'pen' || t === 'highlighter') this.drawing = { ...base, points: [p] };
      else this.drawing = { ...base, x1: p.x, y1: p.y, x2: p.x, y2: p.y };
    }
    move(e) {
      if (this.panning) { this.panX = this.panning.px + (e.offsetX - this.panning.x); this.panY = this.panning.py + (e.offsetY - this.panning.y); this.render(); return; }
      const p = this.toWorld(e.offsetX, e.offsetY);
      if (this.tool === 'laser') { if (this.laserOn || true) this.showLaser(e.offsetX, e.offsetY); return; }
      if (this.erasing) { this.eraseAt(p); return; }
      if (this.dragging && this.selected) {
        const dx = p.x - this.dragging.start.x, dy = p.y - this.dragging.start.y, o = this.dragging.orig, s = this.selected;
        if (o.points) s.points = o.points.map(q => ({ x: q.x + dx, y: q.y + dy }));
        else { s.x1 = o.x1 + dx; s.y1 = o.y1 + dy; s.x2 = o.x2 + dx; s.y2 = o.y2 + dy; }
        this.render(); return;
      }
      if (!this.drawing) return;
      if (this.drawing.points) this.drawing.points.push(p);
      else {
        this.drawing.x2 = p.x; this.drawing.y2 = p.y;
        if (e.shiftKey && (this.drawing.type === 'rect' || this.drawing.type === 'ellipse')) {
          const d = Math.max(Math.abs(p.x - this.drawing.x1), Math.abs(p.y - this.drawing.y1));
          this.drawing.x2 = this.drawing.x1 + Math.sign(p.x - this.drawing.x1) * d; this.drawing.y2 = this.drawing.y1 + Math.sign(p.y - this.drawing.y1) * d;
        }
      }
      this.render();
    }
    up() {
      this.panning = null; this.laserOn = false;
      if (this.erasing) { this.erasing = false; this.commit(); }
      if (this.dragging) { this.dragging = null; this.commit(); }
      if (this.drawing) {
        const d = this.drawing;
        const tooSmall = d.points ? d.points.length < 2 : (Math.abs(d.x2 - d.x1) < 2 && Math.abs(d.y2 - d.y1) < 2);
        if (!tooSmall) { this.pushUndo(); this.shapes.push(d); this.opts.onChange && this.opts.onChange(); }
        this.drawing = null; this.render();
      }
    }
    commit() { this.opts.onChange && this.opts.onChange(); }

    startText(e, kind) {
      const p = this.toWorld(e.offsetX, e.offsetY);
      const box = document.createElement('div');
      box.className = 'wb-textbox'; box.contentEditable = 'true';
      box.style.left = e.offsetX + 'px'; box.style.top = e.offsetY + 'px';
      if (kind === 'note') { box.style.background = NOTE_COLORS[this.shapes.filter(s => s.type === 'note').length % NOTE_COLORS.length]; box.style.minWidth = '160px'; box.style.minHeight = '120px'; box.style.borderStyle = 'solid'; }
      box.dataset.placeholder = kind === 'note' ? 'Стикер…' : 'Введите текст…';
      this.wrap.appendChild(box);
      setTimeout(() => box.focus(), 0);
      const finish = () => {
        const text = box.innerText.trim();
        box.remove();
        if (!text) return;
        this.pushUndo();
        const noteColor = kind === 'note' ? box.style.background : null;
        this.shapes.push({ id: Date.now(), type: kind, x1: p.x, y1: p.y, x2: p.x + (kind === 'note' ? 180 : 10), y2: p.y + (kind === 'note' ? 140 : 10), text, color: kind === 'note' ? '#0f172a' : this.color, size: this.size, noteColor });
        this.commit(); this.render();
      };
      box.addEventListener('blur', finish);
      box.addEventListener('keydown', ev => { if (ev.key === 'Escape') { box.innerText = ''; box.blur(); } if (ev.key === 'Enter' && !ev.shiftKey && kind === 'text') { ev.preventDefault(); box.blur(); } });
    }

    showLaser(x, y) {
      if (!this.laser) { this.laser = document.createElement('div'); this.laser.className = 'wb-laser-dot'; this.wrap.appendChild(this.laser); }
      this.laser.style.left = x + 'px'; this.laser.style.top = y + 'px';
    }
    hideLaser() { if (this.laser) { this.laser.remove(); this.laser = null; } }

    /* ---------- фигуры ---------- */
    bounds(s) {
      if (s.points) {
        const xs = s.points.map(p => p.x), ys = s.points.map(p => p.y);
        return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
      }
      if (s.type === 'text') { const w = this.measureText(s); return { x1: s.x1, y1: s.y1, x2: s.x1 + w.w, y2: s.y1 + w.h }; }
      return { x1: Math.min(s.x1, s.x2), y1: Math.min(s.y1, s.y2), x2: Math.max(s.x1, s.x2), y2: Math.max(s.y1, s.y2) };
    }
    measureText(s) {
      const ctx = this.ctx; const fs = 14 + s.size * 2;
      ctx.font = `600 ${fs}px Satoshi, sans-serif`;
      const lines = s.text.split('\n');
      const w = Math.max(...lines.map(l => ctx.measureText(l).width));
      return { w: w + 8, h: lines.length * fs * 1.3 + 4, fs };
    }
    hitTest(p) {
      for (let i = this.shapes.length - 1; i >= 0; i--) {
        const s = this.shapes[i], b = this.bounds(s), pad = 8 / this.zoom;
        if (p.x >= b.x1 - pad && p.x <= b.x2 + pad && p.y >= b.y1 - pad && p.y <= b.y2 + pad) {
          if (s.points) { if (s.points.some(q => Math.hypot(q.x - p.x, q.y - p.y) < 10 / this.zoom + s.size)) return s; }
          else return s;
        }
      }
      return null;
    }
    eraseAt(p) {
      const s = this.hitTest(p);
      if (s) { if (!this.eraseUndoPushed) { this.pushUndo(); this.eraseUndoPushed = true; setTimeout(() => this.eraseUndoPushed = false, 600); } this.shapes.splice(this.shapes.indexOf(s), 1); this.render(); }
    }
    deleteSelected() { if (this.selected) { this.pushUndo(); this.shapes.splice(this.shapes.indexOf(this.selected), 1); this.selected = null; this.commit(); this.render(); } }
    pushUndo() { const pg = this.pages[this.page]; pg.undo.push(JSON.stringify(pg.shapes)); if (pg.undo.length > 60) pg.undo.shift(); pg.redo = []; }
    undo() { const pg = this.pages[this.page]; if (!pg.undo.length) return; pg.redo.push(JSON.stringify(pg.shapes)); pg.shapes = JSON.parse(pg.undo.pop()); this.selected = null; this.commit(); this.render(); }
    redo() { const pg = this.pages[this.page]; if (!pg.redo.length) return; pg.undo.push(JSON.stringify(pg.shapes)); pg.shapes = JSON.parse(pg.redo.pop()); this.commit(); this.render(); }
    clearPage() { if (!this.shapes.length) return; this.pushUndo(); this.pages[this.page].shapes = []; this.selected = null; this.commit(); this.render(); }

    /* ---------- отрисовка ---------- */
    render() {
      const ctx = this.ctx, dpr = window.devicePixelRatio || 1;
      const W = this.canvas.width / dpr, H = this.canvas.height / dpr;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.translate(this.panX, this.panY); ctx.scale(this.zoom, this.zoom);
      for (const s of this.shapes) this.drawShape(ctx, s);
      if (this.drawing) this.drawShape(ctx, this.drawing);
      if (this.selected) {
        const b = this.bounds(this.selected);
        ctx.save(); ctx.strokeStyle = '#6d28d9'; ctx.lineWidth = 1.5 / this.zoom; ctx.setLineDash([6 / this.zoom, 4 / this.zoom]);
        ctx.strokeRect(b.x1 - 6, b.y1 - 6, b.x2 - b.x1 + 12, b.y2 - b.y1 + 12); ctx.restore();
      }
      ctx.restore();
    }
    drawShape(ctx, s) {
      ctx.save();
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.strokeStyle = s.color; ctx.fillStyle = s.color; ctx.lineWidth = s.size;
      const { x1, y1, x2, y2 } = s;
      switch (s.type) {
        case 'pen': case 'highlighter': {
          if (s.type === 'highlighter') { ctx.globalAlpha = .35; ctx.lineWidth = s.size * 4; ctx.lineCap = 'butt'; }
          ctx.beginPath();
          const pts = s.points; ctx.moveTo(pts[0].x, pts[0].y);
          for (let i = 1; i < pts.length - 1; i++) { const m = { x: (pts[i].x + pts[i + 1].x) / 2, y: (pts[i].y + pts[i + 1].y) / 2 }; ctx.quadraticCurveTo(pts[i].x, pts[i].y, m.x, m.y); }
          if (pts.length > 1) ctx.lineTo(pts[pts.length - 1].x, pts[pts.length - 1].y);
          ctx.stroke(); break;
        }
        case 'line': ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); break;
        case 'arrow': {
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
          const a = Math.atan2(y2 - y1, x2 - x1), h = 10 + s.size * 2;
          ctx.beginPath(); ctx.moveTo(x2, y2);
          ctx.lineTo(x2 - h * Math.cos(a - Math.PI / 6), y2 - h * Math.sin(a - Math.PI / 6));
          ctx.lineTo(x2 - h * Math.cos(a + Math.PI / 6), y2 - h * Math.sin(a + Math.PI / 6));
          ctx.closePath(); ctx.fill(); break;
        }
        case 'rect': ctx.beginPath(); ctx.roundRect ? ctx.roundRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1), 4) : ctx.rect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1)); if (s.fill) { ctx.globalAlpha = .25; ctx.fill(); ctx.globalAlpha = 1; } ctx.stroke(); break;
        case 'ellipse': ctx.beginPath(); ctx.ellipse((x1 + x2) / 2, (y1 + y2) / 2, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 2, 0, 0, Math.PI * 2); if (s.fill) { ctx.globalAlpha = .25; ctx.fill(); ctx.globalAlpha = 1; } ctx.stroke(); break;
        case 'triangle': ctx.beginPath(); ctx.moveTo((x1 + x2) / 2, y1); ctx.lineTo(x2, y2); ctx.lineTo(x1, y2); ctx.closePath(); if (s.fill) { ctx.globalAlpha = .25; ctx.fill(); ctx.globalAlpha = 1; } ctx.stroke(); break;
        case 'text': {
          const m = this.measureText(s);
          ctx.font = `600 ${m.fs}px Satoshi, sans-serif`; ctx.textBaseline = 'top';
          s.text.split('\n').forEach((l, i) => ctx.fillText(l, x1 + 4, y1 + 2 + i * m.fs * 1.3)); break;
        }
        case 'note': {
          const w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
          ctx.shadowColor = 'rgba(15,23,42,.18)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 4;
          ctx.fillStyle = s.noteColor || '#fef08a'; ctx.fillRect(x1, y1, w, h); ctx.shadowColor = 'transparent';
          ctx.fillStyle = '#0f172a'; ctx.font = '600 15px Satoshi, sans-serif'; ctx.textBaseline = 'top';
          this.wrapText(ctx, s.text, x1 + 10, y1 + 10, w - 20, 20); break;
        }
      }
      ctx.restore();
    }
    wrapText(ctx, text, x, y, maxW, lh) {
      const words = text.split(/\s+/); let line = '', yy = y;
      for (const w of words) {
        const t = line ? line + ' ' + w : w;
        if (ctx.measureText(t).width > maxW && line) { ctx.fillText(line, x, yy); line = w; yy += lh; } else line = t;
      }
      ctx.fillText(line, x, yy);
    }

    /* ---------- экспорт ---------- */
    exportPng() {
      const off = document.createElement('canvas');
      const W = this.canvas.width, H = this.canvas.height;
      off.width = W; off.height = H;
      const c = off.getContext('2d');
      c.fillStyle = this.overlay ? '#0b1220' : '#ffffff'; c.fillRect(0, 0, W, H);
      // в режиме аннотаций подкладываем кадр демонстрации экрана (если есть)
      const under = this.opts.underlay && this.opts.underlay();
      if (under && under.videoWidth) { try { const vr = under.videoWidth / under.videoHeight, tr = W / H; let dw = W, dh = H; if (vr > tr) dh = W / vr; else dw = H * vr; c.drawImage(under, (W - dw) / 2, (H - dh) / 2, dw, dh); } catch (e) { /* кадр недоступен */ } }
      c.drawImage(this.canvas, 0, 0);
      const url = off.toDataURL('image/png');
      const w = window.open();
      if (w) { w.document.write(`<title>${this.title}</title><body style="margin:0;background:#111;display:grid;place-items:center;min-height:100vh"><img src="${url}" style="max-width:100%"></body>`); }
      else { const a = document.createElement('a'); a.href = url; a.download = `${this.title}.png`; a.click(); }
      window.toast && toast('PNG-снимок доски открыт в новой вкладке', 'ok');
    }
    exportJson() {
      const data = JSON.stringify({ title: this.title, bg: this.bg, pages: this.pages.map(p => ({ shapes: p.shapes })) });
      const blob = new Blob([data], { type: 'application/json' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${this.title}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }
    importJson(file) {
      if (!file) return;
      const r = new FileReader();
      r.onload = () => {
        try {
          const d = JSON.parse(r.result);
          this.pages = d.pages.map(p => ({ shapes: p.shapes, undo: [], redo: [] })); this.page = 0;
          this.title = d.title || this.title; const ti = this.root.querySelector('.wb-title input'); if (ti) ti.value = this.title;
          this.bg = d.bg || this.bg; this.setTool(this.tool); this.renderPages(); this.render();
          window.toast && toast('Доска загружена', 'ok');
        } catch (e) { window.toast && toast('Не удалось прочитать файл доски', 'bad'); }
      };
      r.readAsText(file);
    }
    snapshot() { return this.canvas.toDataURL('image/png'); }

    /* ---------- имитация курсоров участников ---------- */
    startCollabCursors() {
      this.cursorsEl.innerHTML = this.collab.map((c, i) => `<div class="wb-cursor" data-i="${i}" style="left:${100 + i * 120}px;top:${120 + i * 60}px">${icon('cursor').replace('fill="none"', `fill="${c.color}"`).replace('stroke="currentColor"', `stroke="#fff"`)}<span style="background:${c.color}">${c.name}</span></div>`).join('');
      this.collabTimer = setInterval(() => {
        const rect = this.wrap.getBoundingClientRect();
        this.cursorsEl.querySelectorAll('.wb-cursor').forEach(el => {
          if (Math.random() < .5) return;
          el.style.left = 40 + Math.random() * Math.max(100, rect.width - 160) + 'px';
          el.style.top = 40 + Math.random() * Math.max(100, rect.height - 120) + 'px';
        });
      }, 1800);
    }
  }
  window.Whiteboard = Whiteboard;
})();
