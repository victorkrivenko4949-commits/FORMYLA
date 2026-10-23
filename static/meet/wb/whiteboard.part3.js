/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;
  Object.assign(window.Whiteboard.prototype, {
    closeMenu() { const old = this.root.querySelector('.wb-menu'); if (old) old.remove(); },
    toggleMenu() {
      const old = this.root.querySelector('.wb-menu');
      if (old) { old.remove(); return; }
      const m = document.createElement('div');
      m.className = 'wb-menu';
      const chk = on => on ? `<span class="wb-check">${ic('check')}</span>` : '';
      m.innerHTML = (this.overlay ? '' : `
        <h5>Шаблоны</h5>
        ${Object.entries(TEMPLATES).map(([k, t]) => `<button data-tpl="${k}">${ic(t.icon)} ${esc(t.name)}</button>`).join('')}
        <hr>
        <h5>Фон</h5>
        ${BGS.map(([k, n, i]) => `<button data-bg="${k}">${ic(i)} ${n} ${chk(this.bg === k)}</button>`).join('')}
        <hr>
        <h5>Страницы</h5>
        <button data-m="addPage">${ic('plus')} Добавить страницу</button>
        <button data-m="dupPage">${ic('copy')} Дублировать страницу</button>
        <button data-m="delPage" ${this.pages.length < 2 ? 'disabled' : ''}>${ic('trash')} Удалить страницу</button>
        <hr>`) + `
        <h5>Файл</h5>
        <button data-m="exportPng">${ic('image')} ${this.overlay ? 'Снимок экрана с пометками (PNG)' : 'Скачать картинку всей доски (PNG)'}</button>
        <button data-m="exportJson">${ic('download')} Сохранить доску в файл (.json) · Ctrl+S</button>
        <label>${ic('upload')} Открыть доску из файла (.json)<input type="file" accept="application/json,.json" class="sr-only"></label>
        ${this.overlay ? '' : `<button data-m="newBoard">${ic('file')} Новая пустая доска</button>`}
        <hr>
        <button data-m="shortcuts">${ic('keyboard')} Горячие клавиши и подсказки</button>`;
      this.root.querySelector('.wb-top').appendChild(m);
      m.querySelectorAll('[data-tpl]').forEach(b => b.addEventListener('click', () => { this.applyTemplate(b.dataset.tpl); m.remove(); }));
      m.querySelectorAll('[data-bg]').forEach(b => b.addEventListener('click', () => { this.bg = b.dataset.bg; this.setTool(this.tool); m.remove(); this.commit(); }));
      m.querySelector('input[type=file]').addEventListener('change', ev => { this.importJson(ev.target.files[0]); m.remove(); });
      m.querySelectorAll('[data-m]').forEach(b => b.addEventListener('click', () => { this.menuAction(b.dataset.m); m.remove(); }));
      const off = ev => { if (!m.isConnected) { document.removeEventListener('pointerdown', off); return; } if (!m.contains(ev.target) && !ev.target.closest('[data-act=menu]')) { m.remove(); document.removeEventListener('pointerdown', off); } };
      setTimeout(() => document.addEventListener('pointerdown', off), 0);
    },
    menuAction(a) {
      if (a === 'addPage') { this.pages.push({ shapes: [], undo: [], redo: [] }); this.page = this.pages.length - 1; this.sel = []; }
      if (a === 'dupPage') { this.pages.splice(this.page + 1, 0, { shapes: clone(this.shapes), undo: [], redo: [] }); this.page++; this.sel = []; }
      if (a === 'delPage' && this.pages.length > 1) { this.pages.splice(this.page, 1); this.page = Math.max(0, Math.min(this.page, this.pages.length - 1)); this.sel = []; }
      if (a === 'exportPng') this.exportPng();
      if (a === 'exportJson') this.exportJson();
      if (a === 'newBoard') {
        if (!confirm('Создать новую пустую доску? Текущая будет удалена (сначала можно сохранить её в .json).')) return;
        this.pages = [{ shapes: [], undo: [], redo: [] }]; this.page = 0; this.sel = []; this.zoom = 1; this.panX = 0; this.panY = 0; this.updateZoomLabel();
        this.say('Новая доска создана', 'ok');
      }
      if (a === 'shortcuts') this.showShortcuts();
      this.renderPages(); this.render();
      if (a === 'addPage' || a === 'dupPage' || a === 'delPage' || a === 'newBoard') this.commit();
    },
    showShortcuts() {
      this.root.querySelectorAll('.wb-modal, .wb-backdrop').forEach(x => x.remove());
      const bd = document.createElement('div'); bd.className = 'wb-backdrop';
      const m = document.createElement('div'); m.className = 'wb-modal';
      const rows = [
        ['V · пробел', 'Выделение · рука (двигать холст)'], ['P / H / E', 'Перо / маркер / ластик'], ['[ и ]', 'Размер ластика'],
        ['L / A / B', 'Линия / стрелка / двойная стрелка'], ['R / O / G / D', 'Прямоугольник / эллипс / треугольник / ромб'],
        ['T / N / M / C / K', 'Текст / стикер / штамп / диаграмма / указка'], ['F', 'Заливка фигур'], ['Shift при рисовании', 'Прямая линия, угол 45°, квадрат/круг'],
        ['Ctrl+Z / Ctrl+Y', 'Отменить / повторить'], ['Ctrl+A', 'Выделить всё'], ['Ctrl+C / X / V', 'Копировать / вырезать / вставить (фигуры, текст, картинки)'],
        ['Ctrl+D', 'Дублировать выделенное'], ['Delete', 'Удалить выделенное'], ['Стрелки (+Shift)', 'Сдвинуть выделенное на 1 (10) px'],
        ['Двойной клик', 'Править текст / стикер / данные диаграммы'], ['Esc', 'Снять выделение, отменить действие'],
        ['Ctrl+колесо · + / −', 'Масштаб'], ['Колесо · правая кнопка · Alt+мышь', 'Двигать холст'], ['Shift+1 · 0', 'Показать всё · масштаб 100%'], ['Ctrl+S', 'Сохранить в .json'],
      ];
      m.innerHTML = `<h5>${ic('keyboard')} Горячие клавиши (работают в любой раскладке)</h5><ul>${rows.map(([k, v]) => `<li><span>${esc(v)}</span><kbd>${esc(k)}</kbd></li>`).join('')}</ul><div class="wb-modal-actions"><button class="primary">Понятно</button></div>`;
      this.root.appendChild(bd); this.root.appendChild(m);
      const close = () => { bd.remove(); m.remove(); };
      bd.addEventListener('pointerdown', close); m.querySelector('button').addEventListener('click', close);
    },
    renderPages() {
      const el = this.root.querySelector('.wb-pages');
      if (this.page > this.pages.length - 1) this.page = this.pages.length - 1;
      el.innerHTML = this.pages.map((_, i) => `<button class="${i === this.page ? 'active' : ''}" data-p="${i}" title="Страница ${i + 1}">${i + 1}</button>`).join('') + `<button data-p="add" title="Новая страница">${ic('plus')}</button>`;
      el.querySelectorAll('button').forEach(b => b.addEventListener('click', () => {
        if (b.dataset.p === 'add') this.menuAction('addPage'); else { this.page = +b.dataset.p; this.sel = []; this.renderPages(); this.render(); this.scheduleSave(); }
      }));
    },
    renderCollab() {
      const el = this.root.querySelector('.wb-collab');
      if (!this.collab.length) {
        el.innerHTML = `<span class="small">${this.opts.onChange ? 'Общая доска · пока вы одни' : (this.opts.storageKey ? 'Автосохранение в браузере' : 'Личная доска')}</span>`; return;
      }
      el.innerHTML = this.collab.map(c => `<span class="avatar" style="background:${c.color}" title="${esc(c.name)}">${esc(c.initials)}</span>`).join('') + `<span style="margin-left:8px;font-weight:700">${this.collab.length + 1} на доске</span>`;
    },
    toWorld(x, y) { return { x: (x - this.panX) / this.zoom, y: (y - this.panY) / this.zoom }; },
    toScreen(x, y) { return { x: x * this.zoom + this.panX, y: y * this.zoom + this.panY }; },
    viewCenter() { const dpr = window.devicePixelRatio || 1; return { x: this.canvas.width / dpr / 2, y: this.canvas.height / dpr / 2 }; },
    zoomAt(f, cx, cy) {
      const nz = clamp(this.zoom * f, MIN_ZOOM, MAX_ZOOM);
      const w = this.toWorld(cx, cy);
      this.zoom = nz;
      this.panX = cx - w.x * nz; this.panY = cy - w.y * nz;
      this.updateZoomLabel(); this.render(); this.scheduleSave();
    },
    updateZoomLabel() { const el = this.root.querySelector('.wb-zoom-val'); if (el) el.textContent = Math.round(this.zoom * 100) + '%'; },
    resize() {
      const rect = this.wrap.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const dpr = window.devicePixelRatio || 1;
      this.canvas.width = Math.round(rect.width * dpr); this.canvas.height = Math.round(rect.height * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (this.opts.fitSpace) {
        const [W, H] = this.opts.fitSpace; this.zoom = Math.min(rect.width / W, rect.height / H);
        this.panX = (rect.width - W * this.zoom) / 2; this.panY = (rect.height - H * this.zoom) / 2; this.updateZoomLabel();
      }
      this.render();
    },
    contentBounds(shapes) {
      let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
      (shapes || this.shapes).forEach(s => { const b = this.bounds(s); x1 = Math.min(x1, b.x1); y1 = Math.min(y1, b.y1); x2 = Math.max(x2, b.x2); y2 = Math.max(y2, b.y2); });
      return isFinite(x1) && x2 > x1 && y2 > y1 ? { x1, y1, x2, y2 } : null;
    },
    fitToShapes(shapes) {
      const b = this.contentBounds(shapes); const rect = this.wrap.getBoundingClientRect(); if (!b || !rect.width) return;
      const pad = 40;
      this.zoom = clamp(Math.min((rect.width - pad * 2) / (b.x2 - b.x1), (rect.height - pad * 2) / (b.y2 - b.y1)), MIN_ZOOM, 1.5);
      this.panX = (rect.width - (b.x2 - b.x1) * this.zoom) / 2 - b.x1 * this.zoom;
      this.panY = (rect.height - (b.y2 - b.y1) * this.zoom) / 2 - b.y1 * this.zoom;
      this.updateZoomLabel(); this.scheduleSave();
    },
    fitAll() { if (!this.shapes.length) { this.say('На странице пока пусто', 'info', 1500); return; } this.fitToShapes(this.shapes); this.render(); },
  });
})();
