/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;
  Object.assign(window.Whiteboard.prototype, {
    bounds(s) {
      if (s.points) {
        let x1 = Infinity, y1 = Infinity, x2 = -Infinity, y2 = -Infinity;
        for (const p of s.points) { if (p.x < x1) x1 = p.x; if (p.x > x2) x2 = p.x; if (p.y < y1) y1 = p.y; if (p.y > y2) y2 = p.y; }
        const h = this.strokeHalf(s);
        return { x1: x1 - h, y1: y1 - h, x2: x2 + h, y2: y2 + h };
      }
      if (s.type === 'text') { const m = this.measureText(s); return { x1: s.x1, y1: s.y1, x2: s.x1 + m.w, y2: s.y1 + m.h }; }
      return { x1: Math.min(s.x1, s.x2), y1: Math.min(s.y1, s.y2), x2: Math.max(s.x1, s.x2), y2: Math.max(s.y1, s.y2) };
    },
    measureText(s) {
      const ctx = this.ctx; const fs = 14 + (s.size || 0) * 2;
      ctx.save(); ctx.font = `600 ${fs}px ${FONT}`;
      const lines = String(s.text || '').split('\n');
      const w = Math.max(...lines.map(l => ctx.measureText(l).width), 4);
      ctx.restore();
      return { w: w + 8, h: lines.length * fs * 1.3 + 4, fs };
    },
    fitText(s) { const m = this.measureText(s); s.x2 = s.x1 + m.w; s.y2 = s.y1 + m.h; },
    hitTest(p) {
      const pad = 6 / this.zoom;
      for (let i = this.shapes.length - 1; i >= 0; i--) {
        const s = this.shapes[i];
        if (s === this.editing) continue;
        if (s.points || LINE_TYPES[s.type]) { if (this.shapeErased(s, p, pad)) return s; continue; }
        const b = this.bounds(s);
        if (p.x >= b.x1 - pad && p.x <= b.x2 + pad && p.y >= b.y1 - pad && p.y <= b.y2 + pad) return s;
      }
      return null;
    },
    handlesFor(s) {
      if (LINE_TYPES[s.type]) return [{ k: 'a', x: s.x1, y: s.y1 }, { k: 'b', x: s.x2, y: s.y2 }];
      const b = this.bounds(s), mx = (b.x1 + b.x2) / 2, my = (b.y1 + b.y2) / 2;
      const hs = [{ k: 'nw', x: b.x1, y: b.y1 }, { k: 'ne', x: b.x2, y: b.y1 }, { k: 'sw', x: b.x1, y: b.y2 }, { k: 'se', x: b.x2, y: b.y2 }];
      if (s.type !== 'text' && s.type !== 'stamp') hs.push({ k: 'n', x: mx, y: b.y1 }, { k: 's', x: mx, y: b.y2 }, { k: 'w', x: b.x1, y: my }, { k: 'e', x: b.x2, y: my });
      return hs;
    },
    handleAt(sx, sy) {
      const s = this.sel[0]; if (!s) return null;
      for (const h of this.handlesFor(s)) { const sc = this.toScreen(h.x, h.y); if (Math.abs(sc.x - sx) <= 8 && Math.abs(sc.y - sy) <= 8) return h.k; }
      return null;
    },
    handleCursor(k) { return { nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize', a: 'crosshair', b: 'crosshair' }[k] || 'move'; },
    applyResize(p, shift) {
      const { handle: h, orig: o, shape: s } = this.resizing;
      if (LINE_TYPES[s.type]) { if (h === 'a') { s.x1 = p.x; s.y1 = p.y; } else { s.x2 = p.x; s.y2 = p.y; } return; }
      const ob = this.bounds(o); let x1 = ob.x1, y1 = ob.y1, x2 = ob.x2, y2 = ob.y2;
      if (h.includes('w')) x1 = p.x; if (h.includes('e')) x2 = p.x; if (h.includes('n')) y1 = p.y; if (h.includes('s')) y2 = p.y;
      const ow = ob.x2 - ob.x1 || 1, oh = ob.y2 - ob.y1 || 1;
      const keepAspect = shift || s.type === 'image' || s.type === 'stamp' || s.type === 'text';
      if (keepAspect && h.length === 2) {
        const k = Math.max(Math.abs(x2 - x1) / ow, Math.abs(y2 - y1) / oh);
        const nw = ow * k, nh = oh * k;
        if (h.includes('w')) x1 = x2 - nw * Math.sign(x2 - x1 || 1); else x2 = x1 + nw * Math.sign(x2 - x1 || 1);
        if (h.includes('n')) y1 = y2 - nh * Math.sign(y2 - y1 || 1); else y2 = y1 + nh * Math.sign(y2 - y1 || 1);
      }
      const nw = x2 - x1, nh = y2 - y1;
      if (o.points) { s.points = o.points.map(q => ({ x: x1 + (q.x - ob.x1) / ow * nw, y: y1 + (q.y - ob.y1) / oh * nh })); return; }
      if (s.type === 'text') {
        const lines = String(o.text || '').split('\n').length;
        const fs = clamp(Math.abs(nh) / (lines * 1.3), 8, 400);
        s.size = Math.max(0.5, (fs - 14) / 2);
        s.x1 = Math.min(x1, x2); s.y1 = Math.min(y1, y2); this.fitText(s); return;
      }
      s.x1 = x1; s.y1 = y1; s.x2 = x2; s.y2 = y2;
    },
    normalize(s) {
      if (!s || LINE_TYPES[s.type] || s.points || s.type === 'text') return;
      const x1 = Math.min(s.x1, s.x2), x2 = Math.max(s.x1, s.x2), y1 = Math.min(s.y1, s.y2), y2 = Math.max(s.y1, s.y2);
      s.x1 = x1; s.x2 = Math.max(x2, x1 + 4); s.y1 = y1; s.y2 = Math.max(y2, y1 + 4);
    },
    moveShape(s, o, dx, dy) {
      if (o.points) s.points = o.points.map(q => ({ x: q.x + dx, y: q.y + dy }));
      else { s.x1 = o.x1 + dx; s.y1 = o.y1 + dy; s.x2 = o.x2 + dx; s.y2 = o.y2 + dy; }
    },
    deleteSelected() {
      if (!this.sel.length) return;
      this.pushUndo();
      const set = new Set(this.sel);
      this.pages[this.page].shapes = this.shapes.filter(s => !set.has(s));
      this.sel = []; this.commit(); this.render(); this.setHint();
    },
    selectAll() { this.setTool('move'); this.sel = this.shapes.slice(); this.render(); if (this.sel.length) this.setHint(`Выделено: ${this.sel.length}`); },
    nudge(dx, dy) {
      if (!this.sel.length) return;
      if (!this._nudgeT) this.pushUndo();
      clearTimeout(this._nudgeT); this._nudgeT = setTimeout(() => { this._nudgeT = null; }, 700);
      const k = 1 / this.zoom;
      this.sel.forEach(s => this.moveShape(s, clone(s), dx * k, dy * k));
      this.commit(); this.render();
    },
    serializeSel() { return 'FORMYLA-WB:' + JSON.stringify(this.sel.map(s => clone(s))); },
    copySel(e) {
      if (!this.sel.length) return false;
      const data = this.serializeSel(); this.clip = data;
      if (e && e.clipboardData) { e.clipboardData.setData('text/plain', data); e.preventDefault(); }
      this.say(`Скопировано фигур: ${this.sel.length}`, 'ok', 1500);
      return true;
    },
    cutSel(e) { if (this.copySel(e)) this.deleteSelected(); },
    pasteShapes(data, offset) {
      let arr; try { arr = JSON.parse(data.slice('FORMYLA-WB:'.length)); } catch (err) { return false; }
      if (!Array.isArray(arr) || !arr.length) return false;
      this.pasteN = (this.pasteN || 0) + 1;
      const d = offset ? 24 * this.pasteN / this.zoom : 0;
      this.pushUndo();
      const made = arr.map(o => { const n = clone(o); n.id = uid(); this.moveShape(n, o, d, d); return n; });
      made.forEach(n => this.shapes.push(n));
      this.setTool('move'); this.sel = made;
      this.commit(); this.render();
      return true;
    },
    duplicateSel() { if (!this.sel.length) return; this.pasteN = 0; this.pasteShapes(this.serializeSel(), true); },
    imgFor(src) {
      let img = this.imgCache.get(src);
      if (!img) { img = new Image(); img.onload = () => this.render(); img.src = src; this.imgCache.set(src, img); }
      return img;
    },
    readImageFile(file) {
      const rd = new FileReader();
      rd.onload = () => { if (typeof rd.result === 'string') this.addImage(rd.result); };
      rd.onerror = () => this.say('Не удалось прочитать изображение', 'bad');
      rd.readAsDataURL(file);
    },
    addImage(src) {
      const img = new Image();
      img.onload = () => {
        let dw = img.naturalWidth, dh = img.naturalHeight, url = src;
        const MAX = 1600;
        if (Math.max(dw, dh) > MAX) {
          const k = MAX / Math.max(dw, dh); dw = Math.round(dw * k); dh = Math.round(dh * k);
          try { const off = document.createElement('canvas'); off.width = dw; off.height = dh; off.getContext('2d').drawImage(img, 0, 0, dw, dh); url = off.toDataURL(src.startsWith('data:image/png') ? 'image/png' : 'image/jpeg', 0.85); } catch (e) { }
        }
        this.imgFor(url);
        const vc = this.viewCenter();
        const maxW = vc.x * 2 / this.zoom * 0.7, maxH = vc.y * 2 / this.zoom * 0.7;
        const sc = Math.min(1, maxW / dw, maxH / dh); dw *= sc; dh *= sc;
        const c = this.lastMouse ? this.toWorld(this.lastMouse.x, this.lastMouse.y) : this.toWorld(vc.x, vc.y);
        this.pushUndo();
        const s = { id: uid(), type: 'image', src: url, x1: c.x - dw / 2, y1: c.y - dh / 2, x2: c.x + dw / 2, y2: c.y + dh / 2, color: this.color, size: 0, fill: false };
        this.shapes.push(s); this.setTool('move'); this.sel = [s];
        this.commit(); this.render();
        this.say('Изображение добавлено — тяните за уголки, чтобы изменить размер', 'ok', 3500);
      };
      img.onerror = () => this.say('Файл не является поддерживаемым изображением', 'bad');
      img.src = src;
    },
    pushUndo() { const pg = this.pages[this.page]; pg.undo.push(JSON.stringify(pg.shapes)); if (pg.undo.length > 80) pg.undo.shift(); pg.redo = []; },
    popUndo() { const pg = this.pages[this.page]; pg.undo.pop(); },
    undo() { const pg = this.pages[this.page]; if (!pg.undo.length) { this.say('Отменять нечего', 'info', 1200); return; } pg.redo.push(JSON.stringify(pg.shapes)); pg.shapes = JSON.parse(pg.undo.pop()); this.sel = []; this.commit(); this.render(); },
    redo() { const pg = this.pages[this.page]; if (!pg.redo.length) return; pg.undo.push(JSON.stringify(pg.shapes)); pg.shapes = JSON.parse(pg.redo.pop()); this.sel = []; this.commit(); this.render(); },
    clearPage() { if (!this.shapes.length) return; this.pushUndo(); this.pages[this.page].shapes = []; this.sel = []; this.commit(); this.render(); this.say('Страница очищена. Ctrl+Z — вернуть', 'ok', 2500); },
    commit() { this.opts.onChange && this.opts.onChange(); this.scheduleSave(); },
    scheduleSave() { if (!this.opts.storageKey) return; clearTimeout(this._saveT); this._saveT = setTimeout(() => this.saveLocal(), 400); },
    saveLocal() {
      if (!this.opts.storageKey) return;
      try {
        localStorage.setItem(this.opts.storageKey, JSON.stringify({ v: 2, title: this.title, bg: this.bg, page: this.page, zoom: this.zoom, panX: this.panX, panY: this.panY, pages: this.pages.map(p => ({ shapes: p.shapes })) }));
      } catch (e) { this.say('Не хватает места для автосохранения в браузере — сохраните доску в .json (Ctrl+S)', 'bad', 5000); }
    },
    restoreLocal() {
      try {
        const raw = localStorage.getItem(this.opts.storageKey); if (!raw) return;
        const d = JSON.parse(raw);
        if (d && Array.isArray(d.pages) && d.pages.length) {
          this.pages = d.pages.map(p => ({ shapes: Array.isArray(p.shapes) ? p.shapes : [], undo: [], redo: [] }));
          this.page = clamp(d.page || 0, 0, this.pages.length - 1);
          this.title = d.title || this.title; this.bg = d.bg || this.bg;
          this.zoom = clamp(d.zoom || 1, MIN_ZOOM, MAX_ZOOM); this.panX = d.panX || 0; this.panY = d.panY || 0;
        }
      } catch (e) { }
    },
  });
})();
