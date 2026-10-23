/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;
  Object.assign(window.Whiteboard.prototype, {
    down(e) {
      this.pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
      this.closeMenu();
      if (this.pointers.size === 2) {
        this.drawing = null; this.marquee = null; this.dragging = null; this.resizing = null;
        if (this.erasing) { this.erasing = false; this.hideEraser(); }
        const [a, b] = Array.from(this.pointers.values());
        this.pinch = { d: Math.hypot(b.x - a.x, b.y - a.y) || 1, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2, zoom: this.zoom, panX: this.panX, panY: this.panY };
        try { this.canvas.setPointerCapture(e.pointerId); } catch (err) { }
        this.render(); return;
      }
      if (this.pointers.size > 2) return;
      this.lastMouse = { x: e.offsetX, y: e.offsetY };
      const isPan = e.button === 2 || e.button === 1 || (e.button === 0 && (e.altKey || this.spaceDown || this.tool === 'hand'));
      try { this.canvas.setPointerCapture(e.pointerId); } catch (err) { }
      if (isPan) {
        e.preventDefault();
        this.panning = { x: e.offsetX, y: e.offsetY, px: this.panX, py: this.panY }; this.wrap.classList.add('panning'); return;
      }
      if (e.button !== 0) return;
      const p = this.toWorld(e.offsetX, e.offsetY);
      const t = this.tool;
      if (t === 'laser') { this.showLaser(e.offsetX, e.offsetY); this.laserOn = true; return; }
      if (t === 'text' || t === 'note') { this.startText(e, t); return; }
      if (t === 'eraser') {
        this.eraseUndoDone = false; this.erasing = true; this.eraserPos = { x: e.offsetX, y: e.offsetY }; this.lastErasePt = p;
        this.showEraser(true); this.eraseAt(p, null); return;
      }
      if (t === 'stamp') {
        this.pushUndo();
        const sz = 64;
        this.shapes.push({ id: uid(), type: 'stamp', x1: p.x - sz / 2, y1: p.y - sz / 2, x2: p.x + sz / 2, y2: p.y + sz / 2, text: this.stamp || '👍', color: this.color, size: 4 });
        this.commit(); this.render(); return;
      }
      if (t === 'move') {
        if (this.sel.length === 1) {
          const h = this.handleAt(e.offsetX, e.offsetY);
          if (h) { this.pushUndo(); this.resizing = { handle: h, shape: this.sel[0], orig: clone(this.sel[0]), start: p, moved: false }; return; }
        }
        const s = this.hitTest(p);
        if (s && e.shiftKey) { const i = this.sel.indexOf(s); if (i >= 0) this.sel.splice(i, 1); else this.sel.push(s); this.dragging = null; this.render(); return; }
        if (s) {
          if (!this.sel.includes(s)) this.sel = [s];
          this.dragging = { start: p, origs: this.sel.map(x => clone(x)), moved: false }; this.render(); return;
        }
        this.sel = [];
        this.marquee = { x1: p.x, y1: p.y, x2: p.x, y2: p.y, shift: e.shiftKey, prev: [] };
        this.render(); return;
      }
      const base = { type: t, color: this.color, size: this.size, fill: this.fill, id: uid() };
      if (t === 'chart') this.drawing = { ...base, x1: p.x, y1: p.y, x2: p.x, y2: p.y, chartType: 'bar', data: null, title: 'Диаграмма' };
      else if (t === 'pen' || t === 'highlighter') this.drawing = { ...base, points: [p] };
      else this.drawing = { ...base, x1: p.x, y1: p.y, x2: p.x, y2: p.y };
    },
    move(e) {
      if (this.pointers.has(e.pointerId)) this.pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY });
      if (this.pinch) {
        if (this.pointers.size < 2) return;
        const [a, b] = Array.from(this.pointers.values());
        const d = Math.hypot(b.x - a.x, b.y - a.y) || 1, cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2;
        const nz = clamp(this.pinch.zoom * d / this.pinch.d, MIN_ZOOM, MAX_ZOOM);
        const wx = (this.pinch.cx - this.pinch.panX) / this.pinch.zoom, wy = (this.pinch.cy - this.pinch.panY) / this.pinch.zoom;
        this.zoom = nz; this.panX = cx - wx * nz; this.panY = cy - wy * nz;
        this.updateZoomLabel(); this.render(); return;
      }
      this.lastMouse = { x: e.offsetX, y: e.offsetY };
      if (this.panning) { this.panX = this.panning.px + (e.offsetX - this.panning.x); this.panY = this.panning.py + (e.offsetY - this.panning.y); this.render(); return; }
      const p = this.toWorld(e.offsetX, e.offsetY);
      if (this.opts.onCursor) { const t = Date.now(); if (!this._curT || t - this._curT > 90) { this._curT = t; this.opts.onCursor(p); } else { clearTimeout(this._curTm); this._curTm = setTimeout(() => { this._curT = Date.now(); this.opts.onCursor(p); }, 100); } }
      if (this.tool === 'eraser') {
        this.eraserPos = { x: e.offsetX, y: e.offsetY }; this.showEraser(this.erasing);
        if (this.erasing) { this.eraseAt(p, this.lastErasePt); this.lastErasePt = p; }
        return;
      }
      if (this.tool === 'laser') { this.showLaser(e.offsetX, e.offsetY); return; }
      if (this.resizing) { this.resizing.moved = true; this.applyResize(p, e.shiftKey); this.render(); return; }
      if (this.dragging && this.sel.length) {
        const dx = p.x - this.dragging.start.x, dy = p.y - this.dragging.start.y;
        if (!this.dragging.moved) { if (Math.hypot(dx, dy) * this.zoom < 3) return; this.pushUndo(); this.dragging.moved = true; }
        this.sel.forEach((s, i) => this.moveShape(s, this.dragging.origs[i], dx, dy));
        this.render(); return;
      }
      if (this.marquee) { this.marquee.x2 = p.x; this.marquee.y2 = p.y; this.render(); return; }
      if (!this.drawing) {
        if (this.tool === 'move' && e.buttons === 0) {
          const h = this.sel.length === 1 ? this.handleAt(e.offsetX, e.offsetY) : null;
          this.wrap.style.cursor = h ? this.handleCursor(h) : (this.hitTest(p) ? 'move' : '');
        }
        return;
      }
      const d = this.drawing;
      if (d.points) {
        if (e.shiftKey) d.points = [d.points[0], p];
        else { const l = d.points[d.points.length - 1]; if (Math.hypot(p.x - l.x, p.y - l.y) * this.zoom >= 0.7) d.points.push(p); }
      } else {
        d.x2 = p.x; d.y2 = p.y;
        if (e.shiftKey) {
          if (LINE_TYPES[d.type]) {
            const ang = Math.atan2(p.y - d.y1, p.x - d.x1), len = Math.hypot(p.x - d.x1, p.y - d.y1), snap = Math.round(ang / (Math.PI / 4)) * (Math.PI / 4);
            d.x2 = d.x1 + Math.cos(snap) * len; d.y2 = d.y1 + Math.sin(snap) * len;
          } else {
            const k = Math.max(Math.abs(p.x - d.x1), Math.abs(p.y - d.y1));
            d.x2 = d.x1 + Math.sign(p.x - d.x1 || 1) * k; d.y2 = d.y1 + Math.sign(p.y - d.y1 || 1) * k;
          }
        }
      }
      this.render();
    },
    up(e) {
      this.pointers.delete(e.pointerId);
      if (this.pinch) { if (this.pointers.size < 2) { this.pinch = null; this.scheduleSave(); } return; }
      if (this.panning) { this.panning = null; this.wrap.classList.remove('panning'); this.scheduleSave(); }
      this.laserOn = false;
      if (this.erasing) { this.erasing = false; this.lastErasePt = null; this.showEraser(false); if (this.eraseUndoDone) this.commit(); this.render(); }
      if (this.resizing) { const r = this.resizing; this.resizing = null; this.normalize(r.shape); if (r.moved) this.commit(); else this.popUndo(); this.render(); }
      if (this.dragging) { const mv = this.dragging.moved; this.dragging = null; if (mv) this.commit(); }
      if (this.marquee) {
        const m = this.marquee; this.marquee = null;
        const r = { x1: Math.min(m.x1, m.x2), y1: Math.min(m.y1, m.y2), x2: Math.max(m.x1, m.x2), y2: Math.max(m.y1, m.y2) };
        if ((r.x2 - r.x1) * this.zoom > 4 || (r.y2 - r.y1) * this.zoom > 4) {
          const inside = this.shapes.filter(s => { const b = this.bounds(s); return b.x1 >= r.x1 && b.x2 <= r.x2 && b.y1 >= r.y1 && b.y2 <= r.y2; });
          this.sel = inside;
          if (inside.length) this.setHint(`Выделено: ${inside.length}. Тяните — переместить, Delete — удалить, Ctrl+C — копировать`);
        }
        this.render();
      }
      if (this.drawing) {
        const d = this.drawing;
        const tooSmall = d.points ? d.points.length < 2 : (Math.abs(d.x2 - d.x1) < 2 && Math.abs(d.y2 - d.y1) < 2);
        if (d.points && d.points.length === 1) { d.points.push({ x: d.points[0].x + 0.5, y: d.points[0].y + 0.5 }); }
        if (!tooSmall || d.points) { this.pushUndo(); this.shapes.push(d); this.commit(); }
        if (d.type === 'chart' && !tooSmall) this.editChart(d);
        this.drawing = null; this.render();
      }
    },
    wheel(e) {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) { const f = clamp(Math.exp(-e.deltaY * 0.0022), 0.7, 1.4); this.zoomAt(f, e.offsetX, e.offsetY); }
      else if (e.shiftKey) { this.panX -= (e.deltaY || e.deltaX); this.render(); this.scheduleSave(); }
      else { this.panX -= e.deltaX; this.panY -= e.deltaY; this.render(); this.scheduleSave(); }
      if (this.tool === 'eraser') { this.eraserPos = { x: e.offsetX, y: e.offsetY }; this.showEraser(this.erasing); }
    },
    dblclick(e) {
      const p = this.toWorld(e.offsetX, e.offsetY);
      const hit = this.hitTest(p);
      if (!hit) return;
      if (hit.type === 'chart') { this.editChart(hit); return; }
      if (hit.type === 'text' || hit.type === 'note') { this.setTool('move'); this.sel = [hit]; this.startText(e, hit.type, hit); }
    },
    onKey(e) {
      if (!this.root.isConnected) return;
      if (e.target && e.target.matches && e.target.matches('input, textarea, select, [contenteditable]')) return;
      const code = e.code || '';
      const letter = code.startsWith('Key') ? code.slice(3).toLowerCase() : (e.key || '').toLowerCase();
      const mod = e.ctrlKey || e.metaKey;
      if (code === 'Space') { if (!this.spaceDown) { this.spaceDown = true; this.wrap.classList.add('space-pan'); } e.preventDefault(); return; }
      if (mod && letter === 'z') { e.preventDefault(); e.shiftKey ? this.redo() : this.undo(); return; }
      if (mod && letter === 'y') { e.preventDefault(); this.redo(); return; }
      if (mod && letter === 'a') { e.preventDefault(); this.selectAll(); return; }
      if (mod && letter === 'd') { e.preventDefault(); this.duplicateSel(); return; }
      if (mod && letter === 's') { e.preventDefault(); this.exportJson(); return; }
      if (mod || e.altKey) return;
      if (e.key === 'Escape') { this.escape(); return; }
      if (e.key === 'Delete' || e.key === 'Backspace') { if (this.sel.length) { e.preventDefault(); this.deleteSelected(); } return; }
      if (e.key && e.key.startsWith('Arrow') && this.sel.length) {
        e.preventDefault(); const st = e.shiftKey ? 10 : 1;
        this.nudge(e.key === 'ArrowLeft' ? -st : e.key === 'ArrowRight' ? st : 0, e.key === 'ArrowUp' ? -st : e.key === 'ArrowDown' ? st : 0); return;
      }
      if (code === 'BracketLeft') { this.setEraserSize(this.eraserSize - 4); if (this.tool !== 'eraser') this.setTool('eraser'); return; }
      if (code === 'BracketRight') { this.setEraserSize(this.eraserSize + 4); if (this.tool !== 'eraser') this.setTool('eraser'); return; }
      if (code === 'Equal' || code === 'NumpadAdd' || e.key === '+') { const c = this.viewCenter(); this.zoomAt(1.2, c.x, c.y); return; }
      if (code === 'Minus' || code === 'NumpadSubtract') { const c = this.viewCenter(); this.zoomAt(1 / 1.2, c.x, c.y); return; }
      if (code === 'Digit0' || code === 'Numpad0') { this.action('zoomReset'); return; }
      if (code === 'Digit1' && e.shiftKey) { this.fitAll(); return; }
      const map = { v: 'move', p: 'pen', h: 'highlighter', e: 'eraser', l: 'line', a: 'arrow', b: 'darrow', r: 'rect', o: 'ellipse', g: 'triangle', d: 'diamond', t: 'text', n: 'note', m: 'stamp', c: 'chart', k: 'laser' };
      if (map[letter]) { this.setTool(map[letter]); return; }
      if (letter === 'f') { this.action('fill'); return; }
    },
    escape() {
      if (this.finishText) { this.finishText(true); return; }
      if (this.root.querySelector('.wb-modal')) { this.root.querySelectorAll('.wb-modal, .wb-backdrop').forEach(x => x.remove()); return; }
      if (this.root.querySelector('.wb-chart-editor')) { this.root.querySelector('.wb-chart-editor').remove(); return; }
      this.closeMenu();
      if (this.drawing) { this.drawing = null; }
      if (this.marquee) this.marquee = null;
      if (this.dragging) { if (this.dragging.moved) { this.sel.forEach((s, i) => Object.assign(s, this.dragging.origs[i])); this.popUndo(); } this.dragging = null; }
      this.sel = []; this.render(); this.setHint();
    },
    strokeHalf(s) { if (s.type === 'highlighter') return (s.size || 2) * 2; if (s.points || LINE_TYPES[s.type]) return (s.size || 2) / 2; return 0; },
    distSeg(p, a, b) {
      const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
      if (!l2) return Math.hypot(p.x - a.x, p.y - a.y);
      let t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2;
      t = clamp(t, 0, 1);
      return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
    },
    outlineSegs(s) {
      const x1 = Math.min(s.x1, s.x2), x2 = Math.max(s.x1, s.x2), y1 = Math.min(s.y1, s.y2), y2 = Math.max(s.y1, s.y2);
      if (s.type === 'rect' || s.type === 'note' || s.type === 'image' || s.type === 'chart') return [[{ x: x1, y: y1 }, { x: x2, y: y1 }], [{ x: x2, y: y1 }, { x: x2, y: y2 }], [{ x: x2, y: y2 }, { x: x1, y: y2 }], [{ x: x1, y: y2 }, { x: x1, y: y1 }]];
      if (s.type === 'triangle') { const m = { x: (x1 + x2) / 2, y: y1 }, l = { x: x1, y: y2 }, r = { x: x2, y: y2 }; return [[m, r], [r, l], [l, m]]; }
      if (s.type === 'diamond') { const t = { x: (x1 + x2) / 2, y: y1 }, ri = { x: x2, y: (y1 + y2) / 2 }, bo = { x: (x1 + x2) / 2, y: y2 }, l = { x: x1, y: (y1 + y2) / 2 }; return [[t, ri], [ri, bo], [bo, l], [l, t]]; }
      return [];
    },
    arrowHeadSegs(s) {
      const { x1, y1, x2, y2 } = s, h = 10 + s.size * 2, a = Math.atan2(y2 - y1, x2 - x1);
      const head = (px, py, ang) => [
        [{ x: px, y: py }, { x: px - h * Math.cos(ang - Math.PI / 6), y: py - h * Math.sin(ang - Math.PI / 6) }],
        [{ x: px, y: py }, { x: px - h * Math.cos(ang + Math.PI / 6), y: py - h * Math.sin(ang + Math.PI / 6) }],
      ];
      const segs = [[{ x: x1, y: y1 }, { x: x2, y: y2 }]];
      if (s.type !== 'line') segs.push(...head(x2, y2, a));
      if (s.type === 'darrow') segs.push(...head(x1, y1, a + Math.PI));
      return segs;
    },
    shapeErased(s, p, r) {
      const tol = r + this.strokeHalf(s);
      if (s.points) { for (let i = 1; i < s.points.length; i++) if (this.distSeg(p, s.points[i - 1], s.points[i]) < tol) return true; return false; }
      if (LINE_TYPES[s.type]) return this.arrowHeadSegs(s).some(([a, b]) => this.distSeg(p, a, b) < tol);
      const b = this.bounds(s);
      const inBox = (pad = tol) => p.x >= b.x1 - pad && p.x <= b.x2 + pad && p.y >= b.y1 - pad && p.y <= b.y2 + pad;
      if (s.type === 'rect' || s.type === 'triangle' || s.type === 'diamond') {
        if (s.fill) return inBox();
        return this.outlineSegs(s).some(([a, c]) => this.distSeg(p, a, c) < tol + (s.size || 0) / 2);
      }
      if (s.type === 'ellipse') {
        const cx = (b.x1 + b.x2) / 2, cy = (b.y1 + b.y2) / 2, rx = (b.x2 - b.x1) / 2, ry = (b.y2 - b.y1) / 2;
        if (!rx || !ry) return inBox(0);
        if (s.fill) { const dxn = (p.x - cx) / (rx + tol), dyn = (p.y - cy) / (ry + tol); if (dxn * dxn + dyn * dyn <= 1) return true; }
        const N = 48;
        for (let i = 0; i < N; i++) {
          const a1 = i / N * Math.PI * 2, a2 = (i + 1) / N * Math.PI * 2;
          if (this.distSeg(p, { x: cx + rx * Math.cos(a1), y: cy + ry * Math.sin(a1) }, { x: cx + rx * Math.cos(a2), y: cy + ry * Math.sin(a2) }) < tol + (s.size || 0) / 2) return true;
        }
        return false;
      }
      return inBox();
    },
    splitStroke(s, q, r) {
      const tol = r + this.strokeHalf(s), pts = s.points, n = pts.length;
      const keep = pts.map(pt => Math.hypot(pt.x - q.x, pt.y - q.y) > tol);
      let touched = keep.some(k => !k);
      const pieces = []; let cur = [];
      const flush = () => { if (cur.length >= 2) pieces.push(cur); else if (cur.length === 1 && n <= 2 && !touched) pieces.push(cur); cur = []; };
      for (let i = 0; i < n; i++) {
        if (!keep[i]) { flush(); continue; }
        cur.push(pts[i]);
        if (i < n - 1 && keep[i + 1] && this.distSeg(q, pts[i], pts[i + 1]) < tol) { touched = true; flush(); }
      }
      flush();
      if (!touched) return null;
      return pieces.map(pc => ({ ...s, id: uid(), points: pc }));
    },
    eraseAt(p, prev) {
      const r = this.eraserSize / this.zoom;
      const samples = [];
      if (prev) {
        const d = Math.hypot(p.x - prev.x, p.y - prev.y), step = Math.max(r * 0.5, 0.5), n = Math.min(60, Math.ceil(d / step));
        for (let i = 1; i <= n; i++) samples.push({ x: prev.x + (p.x - prev.x) * i / n, y: prev.y + (p.y - prev.y) * i / n });
      } else samples.push(p);
      let changed = false;
      const ensure = () => { if (!this.eraseUndoDone) { this.pushUndo(); this.eraseUndoDone = true; } };
      for (const q of samples) {
        const shapes = this.shapes;
        for (let i = shapes.length - 1; i >= 0; i--) {
          const s = shapes[i];
          if (this.eraserMode === 'stroke' && s.points) {
            const res = this.splitStroke(s, q, r);
            if (res) { ensure(); shapes.splice(i, 1, ...res); changed = true; }
          } else if (this.shapeErased(s, q, r)) { ensure(); shapes.splice(i, 1); changed = true; }
        }
      }
      if (changed) { this.sel = this.sel.filter(s => this.shapes.includes(s)); this.render(); }
    },
  });
})();
