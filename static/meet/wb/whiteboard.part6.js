/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;
  Object.assign(window.Whiteboard.prototype, {
    startText(e, kind, existing) {
      if (this.finishText) this.finishText();
      const z = this.zoom;
      const p = existing ? { x: Math.min(existing.x1, existing.x2), y: Math.min(existing.y1, existing.y2) } : this.toWorld(e.offsetX, e.offsetY);
      const scr = this.toScreen(p.x, p.y);
      const box = document.createElement('div');
      box.className = 'wb-textbox'; box.contentEditable = 'true'; box.spellcheck = false;
      const size = existing ? existing.size : this.size;
      const fs = kind === 'note' ? 15 : 14 + size * 2;
      box.style.left = scr.x + 'px'; box.style.top = scr.y + 'px';
      box.style.fontSize = (fs * z) + 'px';
      if (kind === 'note') {
        const w = existing ? Math.abs(existing.x2 - existing.x1) : 180, h = existing ? Math.abs(existing.y2 - existing.y1) : 140;
        box.style.width = w * z + 'px'; box.style.minHeight = h * z + 'px'; box.style.padding = (10 * z) + 'px';
        box.style.background = existing ? (existing.noteColor || '#fef08a') : this.noteColor; box.style.borderStyle = 'solid'; box.style.borderRadius = '4px';
        box.style.boxShadow = '0 6px 16px rgba(15,23,42,.18)';
      } else {
        box.style.color = existing ? existing.color : this.color; box.style.padding = `${2 * z}px ${4 * z}px`;
        box.style.minWidth = (120 * z) + 'px';
      }
      box.dataset.placeholder = kind === 'note' ? 'Текст стикера…' : 'Введите текст…';
      if (existing) { box.innerText = existing.text || ''; this.editing = existing; this.render(); }
      this.wrap.appendChild(box);
      setTimeout(() => {
        box.focus();
        if (existing) { try { const r = document.createRange(); r.selectNodeContents(box); r.collapse(false); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); } catch (err) { } }
      }, 0);
      let done = false;
      const finish = (cancel) => {
        if (done) return; done = true; this.finishText = null;
        const text = cancel && !existing ? '' : box.innerText.replace(/\u00a0/g, ' ').replace(/\s+$/, '');
        box.remove(); this.editing = null;
        if (existing) {
          if (cancel) { this.render(); return; }
          if (!text.trim()) { this.pushUndo(); const i = this.shapes.indexOf(existing); if (i >= 0) this.shapes.splice(i, 1); this.sel = []; }
          else if (text !== existing.text) { this.pushUndo(); existing.text = text; if (existing.type === 'text') this.fitText(existing); }
          this.commit(); this.render(); return;
        }
        if (!text.trim()) { this.render(); return; }
        this.pushUndo();
        let sh;
        if (kind === 'note') sh = { id: uid(), type: 'note', x1: p.x, y1: p.y, x2: p.x + 180, y2: p.y + 140, text, color: '#0f172a', size: this.size, noteColor: this.noteColor };
        else { sh = { id: uid(), type: 'text', x1: p.x, y1: p.y, x2: p.x + 10, y2: p.y + 10, text, color: this.color, size: this.size }; this.fitText(sh); }
        this.shapes.push(sh); this.commit(); this.render();
      };
      this.finishText = finish;
      box.addEventListener('blur', () => finish(false));
      box.addEventListener('keydown', ev => {
        ev.stopPropagation();
        if (ev.key === 'Escape') { ev.preventDefault(); finish(true); return; }
        if (ev.key === 'Enter' && !ev.shiftKey && kind === 'text') { ev.preventDefault(); finish(false); }
      });
      box.addEventListener('pointerdown', ev => ev.stopPropagation());
      box.addEventListener('paste', ev => { ev.preventDefault(); ev.stopPropagation(); const t = (ev.clipboardData || window.clipboardData).getData('text/plain'); document.execCommand('insertText', false, t); });
    },
    showLaser(x, y) {
      if (!this.laser) { this.laser = document.createElement('div'); this.laser.className = 'wb-laser-dot'; this.wrap.appendChild(this.laser); }
      this.laser.style.left = x + 'px'; this.laser.style.top = y + 'px';
    },
    hideLaser() { if (this.laser) { this.laser.remove(); this.laser = null; } },
    render() {
      const ctx = this.ctx, dpr = window.devicePixelRatio || 1;
      const W = this.canvas.width / dpr, H = this.canvas.height / dpr;
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.translate(this.panX, this.panY); ctx.scale(this.zoom, this.zoom);
      const vw = this.toWorld(0, 0), vw2 = this.toWorld(W, H);
      for (const s of this.shapes) {
        if (s === this.editing) continue;
        const b = this.bounds(s);
        if (b.x2 < vw.x - 50 || b.x1 > vw2.x + 50 || b.y2 < vw.y - 50 || b.y1 > vw2.y + 50) continue;
        this.drawShape(ctx, s);
      }
      if (this.drawing) this.drawShape(ctx, this.drawing);
      for (const sh of this.sel) {
        const b = this.bounds(sh), pad = 6 / this.zoom;
        ctx.save(); ctx.strokeStyle = '#6d28d9'; ctx.lineWidth = 1.5 / this.zoom; ctx.setLineDash([6 / this.zoom, 4 / this.zoom]);
        ctx.strokeRect(b.x1 - pad, b.y1 - pad, b.x2 - b.x1 + pad * 2, b.y2 - b.y1 + pad * 2); ctx.restore();
      }
      if (this.marquee) {
        const m = this.marquee;
        ctx.save(); ctx.fillStyle = 'rgba(109,40,217,.08)'; ctx.strokeStyle = '#6d28d9'; ctx.lineWidth = 1 / this.zoom; ctx.setLineDash([4 / this.zoom, 3 / this.zoom]);
        ctx.fillRect(Math.min(m.x1, m.x2), Math.min(m.y1, m.y2), Math.abs(m.x2 - m.x1), Math.abs(m.y2 - m.y1));
        ctx.strokeRect(Math.min(m.x1, m.x2), Math.min(m.y1, m.y2), Math.abs(m.x2 - m.x1), Math.abs(m.y2 - m.y1)); ctx.restore();
      }
      ctx.restore();
      if (this.sel.length === 1 && this.tool === 'move' && !this.dragging) {
        ctx.save(); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        for (const h of this.handlesFor(this.sel[0])) {
          const sc = this.toScreen(h.x, h.y);
          ctx.fillStyle = '#fff'; ctx.strokeStyle = '#6d28d9'; ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.arc(sc.x, sc.y, 5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }
        ctx.restore();
      }
    },
    fillShape(ctx, s) {
      if (!s.fill) return;
      if (s.bg) { ctx.fillStyle = s.bg; ctx.fill(); }
      else { ctx.globalAlpha = .25; ctx.fill(); ctx.globalAlpha = 1; }
    },
    drawShape(ctx, s) {
      ctx.save();
      ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.strokeStyle = s.color; ctx.fillStyle = s.color; ctx.lineWidth = s.size;
      const { x1, y1, x2, y2 } = s;
      switch (s.type) {
        case 'pen': case 'highlighter': {
          if (s.type === 'highlighter') { ctx.globalAlpha = .35; ctx.lineWidth = s.size * 4; ctx.lineCap = 'butt'; }
          const pts = s.points; if (!pts || !pts.length) break;
          ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
          if (pts.length === 1) ctx.lineTo(pts[0].x + 0.1, pts[0].y);
          for (let i = 1; i < pts.length - 1; i++) { const m = { x: (pts[i].x + pts[i + 1].x) / 2, y: (pts[i].y + pts[i + 1].y) / 2 }; ctx.quadraticCurveTo(pts[i].x, pts[i].y, m.x, m.y); }
          if (pts.length > 1) ctx.lineTo(pts[pts.length - 1].x, pts[pts.length - 1].y);
          ctx.stroke(); break;
        }
        case 'line': ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); break;
        case 'arrow': case 'darrow': {
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
          const a = Math.atan2(y2 - y1, x2 - x1), h = 10 + s.size * 2;
          const heads = [[x2, y2, a]]; if (s.type === 'darrow') heads.push([x1, y1, a + Math.PI]);
          heads.forEach(([px, py, aa]) => {
            ctx.beginPath(); ctx.moveTo(px, py);
            ctx.lineTo(px - h * Math.cos(aa - Math.PI / 6), py - h * Math.sin(aa - Math.PI / 6));
            ctx.lineTo(px - h * Math.cos(aa + Math.PI / 6), py - h * Math.sin(aa + Math.PI / 6));
            ctx.closePath(); ctx.fill();
          }); break;
        }
        case 'rect': {
          const x = Math.min(x1, x2), y = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
          ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, w, h, Math.min(4, w / 2, h / 2)); else ctx.rect(x, y, w, h);
          this.fillShape(ctx, s); ctx.stroke(); break;
        }
        case 'ellipse': ctx.beginPath(); ctx.ellipse((x1 + x2) / 2, (y1 + y2) / 2, Math.abs(x2 - x1) / 2, Math.abs(y2 - y1) / 2, 0, 0, Math.PI * 2); this.fillShape(ctx, s); ctx.stroke(); break;
        case 'triangle': ctx.beginPath(); ctx.moveTo((x1 + x2) / 2, Math.min(y1, y2)); ctx.lineTo(Math.max(x1, x2), Math.max(y1, y2)); ctx.lineTo(Math.min(x1, x2), Math.max(y1, y2)); ctx.closePath(); this.fillShape(ctx, s); ctx.stroke(); break;
        case 'diamond': ctx.beginPath(); ctx.moveTo((x1 + x2) / 2, y1); ctx.lineTo(x2, (y1 + y2) / 2); ctx.lineTo((x1 + x2) / 2, y2); ctx.lineTo(x1, (y1 + y2) / 2); ctx.closePath(); this.fillShape(ctx, s); ctx.stroke(); break;
        case 'image': {
          const img = s.src ? this.imgFor(s.src) : null;
          const x = Math.min(x1, x2), y = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
          if (img && img.complete && img.naturalWidth) { ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high'; ctx.drawImage(img, x, y, w, h); }
          else {
            ctx.fillStyle = '#e2e8f0'; ctx.fillRect(x, y, w, h); ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 1.5; ctx.strokeRect(x, y, w, h);
            ctx.fillStyle = '#64748b'; ctx.font = `600 14px ${FONT}`; ctx.textBaseline = 'middle'; ctx.textAlign = 'center'; ctx.fillText('Загрузка изображения…', x + w / 2, y + h / 2);
          }
          break;
        }
        case 'stamp': {
          const x = Math.min(x1, x2), y = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
          const fs = Math.max(8, Math.min(w, h) * 0.82);
          ctx.font = `${fs}px ${EMOJI_FONT}`; ctx.textBaseline = 'middle'; ctx.textAlign = 'center';
          ctx.fillText(s.text || '👍', x + w / 2, y + h / 2 + fs * 0.05); break;
        }
        case 'text': {
          const m = this.measureText(s);
          ctx.font = `600 ${m.fs}px ${FONT}`; ctx.textBaseline = 'top'; ctx.textAlign = 'left';
          String(s.text || '').split('\n').forEach((l, i) => ctx.fillText(l, x1 + 4, y1 + 2 + i * m.fs * 1.3)); break;
        }
        case 'note': {
          const x = Math.min(x1, x2), y = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
          ctx.shadowColor = 'rgba(15,23,42,.18)'; ctx.shadowBlur = 12; ctx.shadowOffsetY = 4;
          ctx.fillStyle = s.noteColor || '#fef08a'; ctx.fillRect(x, y, w, h); ctx.shadowColor = 'transparent';
          ctx.fillStyle = '#0f172a'; ctx.font = `600 15px ${FONT}`; ctx.textBaseline = 'top'; ctx.textAlign = 'left';
          ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
          this.wrapText(ctx, s.text || '', x + 10, y + 10, w - 20, 20); break;
        }
        case 'chart': this.drawChart(ctx, s); break;
      }
      ctx.restore();
    },
    wrapText(ctx, text, x, y, maxW, lh) {
      let yy = y;
      String(text).split('\n').forEach(par => {
        const words = par.split(/\s+/); let line = '';
        for (const w of words) {
          const t = line ? line + ' ' + w : w;
          if (ctx.measureText(t).width > maxW && line) { ctx.fillText(line, x, yy); line = w; yy += lh; } else line = t;
        }
        ctx.fillText(line, x, yy); yy += lh;
      });
    },
    drawChart(ctx, s) {
      const { x1, y1, x2, y2 } = s;
      const x = Math.min(x1, x2), y = Math.min(y1, y2), w = Math.abs(x2 - x1), h = Math.abs(y2 - y1);
      const data = (s.data && s.data.length) ? s.data : [{ label: 'Янв', value: 30 }, { label: 'Фев', value: 55 }, { label: 'Мар', value: 42 }, { label: 'Апр', value: 68 }];
      const sum = data.reduce((a, d) => a + (+d.value || 0), 0) || 1;
      ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#cbd5e1'; ctx.lineWidth = 1.5;
      ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x, y, w, h, 10); else ctx.rect(x, y, w, h); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#0f172a'; ctx.font = `800 16px ${FONT}`; ctx.textBaseline = 'top'; ctx.textAlign = 'left';
      ctx.fillText(s.title || 'Диаграмма', x + 14, y + 10);
      if (s.chartType === 'pie') {
        const cx0 = x + Math.min(h * .5, w * .38), cy0 = y + h / 2 + 8, r = Math.max(4, Math.min(h * .32, w * .26));
        let ang = -Math.PI / 2;
        data.forEach((d, i) => {
          const a2 = ang + (+d.value || 0) / sum * Math.PI * 2;
          ctx.beginPath(); ctx.moveTo(cx0, cy0); ctx.arc(cx0, cy0, r, ang, a2); ctx.closePath();
          ctx.fillStyle = PIE_COLORS[i % PIE_COLORS.length]; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke();
          ang = a2;
        });
        const lx = Math.min(cx0 + r + 12, x + w - 104); let ly = y + h / 2 - data.length * 11;
        ctx.font = `700 14px ${FONT}`;
        data.forEach((d, i) => {
          ctx.fillStyle = PIE_COLORS[i % PIE_COLORS.length]; ctx.fillRect(lx, ly + 3, 9, 9);
          ctx.fillStyle = '#0f172a'; ctx.fillText(`${d.label} — ${Math.round((+d.value || 0) / sum * 100)}%`, lx + 14, ly + 1);
          ly += 22;
        });
      } else {
        const px = 34, pb = 30, pt = 40, cw = Math.max(10, w - px - 14), chh = Math.max(10, h - pt - pb);
        const max = Math.max(...data.map(d => +d.value || 0), 1);
        ctx.strokeStyle = '#e2e8f0'; ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) { const gy = y + pt + chh - chh * i / 4; ctx.beginPath(); ctx.moveTo(x + px, gy); ctx.lineTo(x + px + cw, gy); ctx.stroke(); }
        const bw = cw / data.length, barColor = s.color === '#ffffff' ? '#6d28d9' : s.color;
        data.forEach((d, i) => {
          const bh = chh * ((+d.value || 0) / max), bx = x + px + i * bw + bw * .18, by = y + pt + chh - bh, bwi = bw * .64;
          const gr = ctx.createLinearGradient(0, by, 0, y + pt + chh); gr.addColorStop(0, barColor); gr.addColorStop(1, barColor + '99');
          ctx.fillStyle = gr; ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(bx, by, bwi, Math.max(bh, 2), 4); else ctx.rect(bx, by, bwi, Math.max(bh, 2)); ctx.fill();
          ctx.fillStyle = '#475569'; ctx.font = `600 12px ${FONT}`; ctx.textBaseline = 'top'; ctx.textAlign = 'center';
          ctx.fillText(String(d.label), bx + bwi / 2, y + pt + chh + 8); ctx.fillText(String(d.value), bx + bwi / 2, by - 16);
          ctx.textAlign = 'left';
        });
      }
    },
  });
})();
