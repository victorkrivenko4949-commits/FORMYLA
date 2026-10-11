/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;
  Object.assign(window.Whiteboard.prototype, {
    editChart(shape) {
      const old = this.root.querySelector('.wb-chart-editor'); if (old) old.remove();
      const box = document.createElement('div'); box.className = 'wb-chart-editor';
      const cur = (shape.data && shape.data.length) ? shape.data.map(d => `${d.label}, ${d.value}`).join('\n') : 'Январь, 120\nФевраль, 95\nМарт, 140\nАпрель, 175';
      box.innerHTML = `
        <h5>${ic('chart')} Данные диаграммы</h5>
        <p class="small" style="color:#64748b;margin:0">Одна строка — один столбик или сектор: <b>Название, число</b></p>
        <textarea class="wb-chart-data" rows="6">${esc(cur)}</textarea>
        <div class="wb-chart-row">
          <input type="text" class="wb-chart-title" value="${esc(shape.title || 'Диаграмма')}" placeholder="Заголовок">
          <select class="wb-chart-type">
            <option value="bar"${shape.chartType !== 'pie' ? ' selected' : ''}>Столбчатая</option>
            <option value="pie"${shape.chartType === 'pie' ? ' selected' : ''}>Круговая</option>
          </select>
        </div>
        <div class="wb-chart-actions"><button class="wb-chart-cancel">Отмена</button><button class="wb-chart-save">Сохранить</button></div>`;
      this.root.appendChild(box);
      const close = () => box.remove();
      box.querySelector('.wb-chart-cancel').onclick = close;
      box.querySelector('.wb-chart-save').onclick = () => {
        const rows = box.querySelector('.wb-chart-data').value.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
          const parts = l.split(/[,;\t]/); const v = parseFloat(String(parts[1] || '').replace(',', '.'));
          return { label: (parts[0] || '').trim() || '—', value: isNaN(v) ? 0 : v };
        });
        this.pushUndo();
        shape.data = rows.length ? rows : [{ label: '—', value: 1 }];
        shape.title = box.querySelector('.wb-chart-title').value.trim() || 'Диаграмма';
        shape.chartType = box.querySelector('.wb-chart-type').value;
        close(); this.commit(); this.render();
        this.say('Диаграмма обновлена — двойной клик по ней, чтобы изменить данные', 'ok');
      };
      box.addEventListener('keydown', e => { if (e.key === 'Escape') close(); e.stopPropagation(); });
      box.addEventListener('pointerdown', e => e.stopPropagation());
      setTimeout(() => box.querySelector('textarea').focus(), 0);
    },
    tplShapes(key) {
      const box = (x, y, w, h, stroke = '#94a3b8', bg = '#f8fafc', size = 2) => ({ id: uid(), type: 'rect', x1: x, y1: y, x2: x + w, y2: y + h, color: stroke, size, fill: true, bg });
      const label = (x, y, text, sz = 4, color = '#0f172a') => { const s = { id: uid(), type: 'text', x1: x, y1: y, x2: x + 10, y2: y + 10, text, color, size: sz }; this.fitText(s); return s; };
      const band = (x, y, w, text, c, sz = 2.8) => { const bh = text.includes('\n') ? 58 : 36; return [box(x, y, w, bh, c, c, 1.5), label(x + 12, y + 7, text, sz, '#ffffff')]; };
      const note = (x, y, text, bg = '#fef08a', w = 175, h = 92) => ({ id: uid(), type: 'note', x1: x, y1: y, x2: x + w, y2: y + h, text, color: '#0f172a', size: 2, noteColor: bg });
      const shapes = [];
      if (key === 'lesson') {
        shapes.push(label(40, 20, 'Разбор задачи', 6));
        shapes.push(box(40, 76, 1120, 150, '#64748b', '#f8fafc')); shapes.push(...band(40, 76, 1120, 'Условие', '#475569'));
        shapes.push(box(40, 246, 340, 430, '#2563eb', '#ffffff')); shapes.push(...band(40, 246, 340, 'Дано · Найти', '#2563eb'));
        shapes.push(box(400, 246, 760, 430, '#7c3aed', '#ffffff')); shapes.push(...band(400, 246, 760, 'Решение', '#7c3aed'));
        shapes.push(box(40, 696, 1120, 90, '#16a34a', '#ecfdf5')); shapes.push(...band(40, 696, 1120, 'Ответ', '#16a34a'));
        shapes.push(note(830, 300, 'Проверь единицы измерения и размерность ответа', '#fef08a', 300, 70));
      } else if (key === 'kanban') {
        shapes.push(label(40, 24, 'Канбан-доска проекта', 6));
        [['Бэклог', '#64748b'], ['Запланировано', '#7c3aed'], ['В работе', '#2563eb'], ['На проверке', '#d97706'], ['Готово', '#16a34a']].forEach((c, i) => {
          const x = 40 + i * 232; shapes.push(box(x, 80, 216, 560)); shapes.push(...band(x, 80, 216, c[0], c[1]));
        });
        shapes.push(note(52, 132, 'Обсудить бюджет Q4', '#fef08a')); shapes.push(note(284, 132, 'Прототип витрины', '#bae6fd'));
        shapes.push(note(284, 240, 'Найти 2 клиентов на интервью', '#bae6fd')); shapes.push(note(516, 132, 'A/B-тест тарифов', '#bbf7d0')); shapes.push(note(980, 132, 'Отчёт для инвесторов', '#e9d5ff'));
      } else if (key === 'swot') {
        shapes.push(label(40, 24, 'SWOT-анализ', 6));
        [['S · Сильные стороны', '#16a34a', 40, 90], ['W · Слабые стороны', '#dc2626', 640, 90], ['O · Возможности', '#2563eb', 40, 390], ['T · Угрозы', '#d97706', 640, 390]].forEach(q => {
          shapes.push(box(q[2], q[3], 580, 280, q[1], '#ffffff', 2)); shapes.push(...band(q[2], q[3], 580, q[0], q[1]));
        });
        shapes.push(note(64, 150, 'Опыт команды в нише', '#bbf7d0', 150, 76)); shapes.push(note(224, 250, 'Растущий спрос на онлайн-обучение', '#bbf7d0', 180, 90));
      } else if (key === 'bmc') {
        shapes.push(label(40, 18, 'Business Model Canvas', 5.5));
        const X = 40, Y = 64, W = 1120, cw = W / 5, rowH = 205, gap = 6;
        [['Ключевые\nпартнёры', 0, Y, cw - gap, rowH * 2 + gap, '#334155'], ['Ключевые\nактивности', cw, Y, cw - gap, rowH, '#0e7490'], ['Ценностное\nпредложение', cw * 2, Y, cw - gap, rowH * 2 + gap, '#7c3aed'],
         ['Отношения\nс клиентами', cw * 3, Y, cw - gap, rowH, '#b45309'], ['Клиентские\nсегменты', cw * 4, Y, cw - gap, rowH * 2 + gap, '#15803d'], ['Ключевые ресурсы', cw, Y + rowH + gap, cw - gap, rowH, '#0e7490'],
         ['Каналы сбыта', cw * 3, Y + rowH + gap, cw - gap, rowH, '#b45309'], ['Структура издержек', 0, Y + (rowH + gap) * 2, W / 2 - gap, 104, '#be123c'], ['Потоки доходов', W / 2, Y + (rowH + gap) * 2, W / 2 - gap, 104, '#0369a1']]
          .forEach(c => { shapes.push(box(X + c[1], c[2], c[3], c[4], c[5], '#ffffff', 1.5)); shapes.push(...band(X + c[1], c[2], c[3], c[0], c[5], 2.2)); });
      } else if (key === 'roadmap') {
        shapes.push(label(40, 24, 'Дорожная карта · год', 6));
        shapes.push({ id: uid(), type: 'arrow', x1: 40, y1: 62, x2: 1160, y2: 62, color: '#64748b', size: 2, fill: false });
        ['Q1 · цели и планирование', 'Q2 · разработка', 'Q3 · запуск и маркетинг', 'Q4 · масштабирование'].forEach((q, i) => {
          const x = 40 + i * 292; shapes.push(box(x, 96, 280, 470, '#94a3b8', i % 2 ? '#f8fafc' : '#eef2ff', 1.5)); shapes.push(...band(x, 96, 280, q, '#475569'));
        });
        shapes.push(note(56, 156, 'Инициатива 1 · владелец · срок', '#bae6fd', 245, 78)); shapes.push(note(348, 246, 'Инициатива 2 · владелец · срок', '#bbf7d0', 245, 78)); shapes.push(note(932, 336, 'Инициатива 3 · владелец · срок', '#fecdd3', 245, 78));
      } else if (key === 'retro') {
        shapes.push(label(40, 24, 'Ретроспектива команды', 6));
        [['Что удалось 👍', '#16a34a'], ['Что мешало ⚠️', '#dc2626'], ['Что улучшить 💡', '#2563eb']].forEach((c, i) => {
          const x = 40 + i * 390; shapes.push(box(x, 90, 374, 480, c[1], '#ffffff', 2)); shapes.push(...band(x, 90, 374, c[0], c[1]));
        });
        shapes.push(note(56, 150, 'Быстро выпустили релиз', '#bbf7d0')); shapes.push(note(446, 150, 'Много переделок из-за требований', '#fecdd3')); shapes.push(note(836, 150, 'Демо каждую пятницу', '#bae6fd'));
      } else if (key === 'eisenhower') {
        shapes.push(label(40, 24, 'Матрица Эйзенхауэра', 6));
        [['Срочно и важно — делать сразу', '#dc2626', 40, 90], ['Важно, не срочно — планировать', '#2563eb', 640, 90], ['Срочно, не важно — делегировать', '#d97706', 40, 390], ['Не срочно и не важно — убрать', '#64748b', 640, 390]].forEach(q => {
          shapes.push(box(q[2], q[3], 580, 280, q[1], '#ffffff', 2)); shapes.push(...band(q[2], q[3], 580, q[0], q[1]));
        });
        shapes.push(note(64, 150, 'Звонок клиенту по контракту', '#fef08a', 190, 84)); shapes.push(note(664, 150, 'Стратегия на следующий год', '#bae6fd', 190, 84));
      }
      return shapes;
    },
    applyTemplate(key) {
      const shapes = this.tplShapes(key);
      if (!shapes.length) return;
      this.pages.push({ shapes, undo: [], redo: [] });
      this.page = this.pages.length - 1; this.sel = [];
      this.fitToShapes(shapes);
      this.renderPages(); this.render(); this.commit();
      this.say(`Шаблон «${TEMPLATES[key].name}» добавлен на новую страницу`, 'ok', 4000);
    },
    download(url, name) { const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { a.remove(); if (url.startsWith('blob:')) URL.revokeObjectURL(url); }, 1500); },
    safeName() { return (this.title || 'Доска').replace(/[\\/:*?"<>|]+/g, '-').trim() || 'Доска'; },
    exportPng() {
      const off = document.createElement('canvas');
      const b = this.overlay ? null : this.contentBounds();
      if (!b) {
        const W = this.canvas.width, H = this.canvas.height; off.width = W; off.height = H;
        const c = off.getContext('2d');
        c.fillStyle = this.overlay ? '#0b1220' : '#ffffff'; c.fillRect(0, 0, W, H);
        const under = this.opts.underlay && this.opts.underlay();
        if (under && under.videoWidth) { try { const vr = under.videoWidth / under.videoHeight, tr = W / H; let dw = W, dh = H; if (vr > tr) dh = W / vr; else dw = H * vr; c.drawImage(under, (W - dw) / 2, (H - dh) / 2, dw, dh); } catch (e) { } }
        c.drawImage(this.canvas, 0, 0);
      } else {
        const pad = 40, cw = b.x2 - b.x1 + pad * 2, ch = b.y2 - b.y1 + pad * 2;
        const scale = clamp(Math.min(2, 8000 / cw, 8000 / ch), 0.2, 2);
        off.width = Math.ceil(cw * scale); off.height = Math.ceil(ch * scale);
        const c = off.getContext('2d');
        c.fillStyle = '#ffffff'; c.fillRect(0, 0, off.width, off.height);
        c.setTransform(scale, 0, 0, scale, (pad - b.x1) * scale, (pad - b.y1) * scale);
        for (const s of this.shapes) this.drawShape(c, s);
      }
      try { this.download(off.toDataURL('image/png'), `${this.safeName()}.png`); this.say('Картинка доски сохранена (PNG)', 'ok'); }
      catch (e) { this.say('Не удалось сохранить PNG', 'bad'); }
    },
    exportJson() {
      const data = JSON.stringify({ title: this.title, bg: this.bg, pages: this.pages.map(p => ({ shapes: p.shapes })) });
      const blob = new Blob([data], { type: 'application/json' });
      this.download(URL.createObjectURL(blob), `${this.safeName()}.json`);
      this.say('Доска сохранена в файл .json — его можно открыть через меню', 'ok');
    },
    importJson(file) {
      if (!file) return;
      const r = new FileReader();
      r.onload = () => {
        try {
          const d = JSON.parse(r.result);
          if (!d || !Array.isArray(d.pages)) throw new Error('bad');
          this.pages = d.pages.map(p => ({ shapes: Array.isArray(p.shapes) ? p.shapes : [], undo: [], redo: [] })); if (!this.pages.length) this.pages = [{ shapes: [], undo: [], redo: [] }];
          this.page = 0; this.sel = [];
          this.title = d.title || this.title; const ti = this.root.querySelector('.wb-title input'); if (ti) ti.value = this.title;
          this.bg = d.bg || this.bg; this.setTool(this.tool); this.renderPages();
          if (this.shapes.length) this.fitToShapes(this.shapes);
          this.render(); this.commit();
          this.say('Доска загружена', 'ok');
        } catch (e) { this.say('Не удалось прочитать файл доски', 'bad'); }
      };
      r.readAsText(file);
    },
    snapshot() { return this.canvas.toDataURL('image/png'); },
    startCollabCursors() { this.cursorsEl.innerHTML = ''; },
    setCursor(id, name, color, wx, wy) {
      if (!this.cursorsEl) return;
      let el = this.cursorsEl.querySelector(`.wb-cursor[data-id="${id}"]`);
      if (!el) { el = document.createElement('div'); el.className = 'wb-cursor'; el.dataset.id = id; el.innerHTML = `${ic('cursor').replace('fill="none"', `fill="${color}"`).replace('stroke="currentColor"', 'stroke="#fff"')}<span style="background:${color}">${esc(name)}</span>`; this.cursorsEl.appendChild(el); }
      const sc = this.toScreen(wx, wy);
      el.style.left = sc.x + 'px'; el.style.top = sc.y + 'px'; el.style.opacity = '1';
      clearTimeout(el._hide); el._hide = setTimeout(() => { el.style.opacity = '0'; }, 4000);
    },
    removeCursor(id) { const el = this.cursorsEl && this.cursorsEl.querySelector(`.wb-cursor[data-id="${id}"]`); el && el.remove(); },
  });
})();
