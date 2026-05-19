// FORMYLA Whiteboard - Thalamus-style infinite canvas.
// Tools: select/pen/eraser/rect/ellipse/line/arrow/text/sticky.
// Pan: middle-mouse or space+drag. Zoom: ctrl+wheel.
// Undo/Redo, auto-save to localStorage, export PNG, import image.

(function () {
  "use strict";

  const STORAGE_KEY = "formyla_wb_state_v1";
  const MAX_HISTORY = 50;

  const canvasEl = document.getElementById("wbCanvas");
  const wrap = document.getElementById("wbCanvasWrap");
  const hud = document.getElementById("wbHUD");
  const status = document.getElementById("wbStatus");
  const textEditor = document.getElementById("wbTextEditor");
  if (!canvasEl || !wrap) return;
  const ctx = canvasEl.getContext("2d");

  let state = { objects: [], nextId: 1 };
  let view = { x: 0, y: 0, scale: 1 };
  let tool = "select";
  let color = "#e6e8ff";
  let thickness = 3;
  let selectedId = null;
  let drag = null;
  let history = [];
  let historyIndex = -1;
  let spaceDown = false;
  let editingId = null;
  let saveTimer = 0;

  function uid() { return state.nextId++; }
  function snap() { return JSON.parse(JSON.stringify(state)); }

  // ── Collaborative diff broadcast ───────────────────────────────────
  // When the user mutates state.objects (add/edit/remove/clear), we
  // detect the delta against the previous snapshot and forward it via
  // window.__wbBroadcast (set by static/js/wb_meet.js once the LiveKit
  // data-channel is up).  Pure local sessions (no meet) never see a
  // broadcaster and run zero-overhead.
  //
  // `_suppressBroadcastDepth` lets us apply REMOTE ops via the very
  // same path without echoing them back to the room.
  let _lastSnapshotJSON = null;     // snapshot taken right after the previous pushHistory
  let _suppressBroadcastDepth = 0;  // >0 means "we are applying a remote op, don't broadcast"

  function _objectsById(arr) {
    const m = new Map();
    for (const o of arr) m.set(o.id, o);
    return m;
  }

  function _diffAndBroadcast(prevSnap, nextSnap) {
    if (_suppressBroadcastDepth > 0) return;
    const fn = window.__wbBroadcast;
    if (typeof fn !== "function") return;
    try {
      const prevObjs = (prevSnap && prevSnap.objects) || [];
      const nextObjs = (nextSnap && nextSnap.objects) || [];
      // Detect a wholesale wipe so we can send a compact "clear".
      if (prevObjs.length > 0 && nextObjs.length === 0) {
        fn({ op: "clear", nextId: nextSnap.nextId });
        return;
      }
      const prevMap = _objectsById(prevObjs);
      const nextMap = _objectsById(nextObjs);
      const adds = [];
      const updates = [];
      const removes = [];
      for (const o of nextObjs) {
        const prev = prevMap.get(o.id);
        if (!prev) { adds.push(o); continue; }
        // Cheap shallow compare via JSON; the WB object schema is tiny.
        if (JSON.stringify(prev) !== JSON.stringify(o)) updates.push(o);
      }
      for (const o of prevObjs) {
        if (!nextMap.has(o.id)) removes.push(o.id);
      }
      // If the delta is suspiciously large (paste / undo across many
      // objects), fall back to a full snapshot to keep the data-channel
      // packet count low and ensure remote pairs converge.
      const totalChanges = adds.length + updates.length + removes.length;
      if (totalChanges > 30) {
        fn({ op: "snapshot", state: { objects: nextObjs, nextId: nextSnap.nextId } });
        return;
      }
      if (totalChanges === 0) return;
      fn({
        op: "ops",
        adds: adds,
        updates: updates,
        removes: removes,
        nextId: nextSnap.nextId,
      });
    } catch (e) {
      console.warn("[WB] diff/broadcast failed:", e);
    }
  }

  function pushHistory() {
    history = history.slice(0, historyIndex + 1);
    const fresh = snap();
    history.push(fresh);
    if (history.length > MAX_HISTORY) history.shift();
    historyIndex = history.length - 1;
    scheduleSave();
    // Broadcast the diff between the previous committed snapshot and
    // the new one.  On the very first call _lastSnapshotJSON is null —
    // we still emit a snapshot so peers that join late get our state.
    try {
      const prev = _lastSnapshotJSON ? JSON.parse(_lastSnapshotJSON) : { objects: [], nextId: 1 };
      _diffAndBroadcast(prev, fresh);
    } catch (e) { /* never let collab break the UI */ }
    _lastSnapshotJSON = JSON.stringify(fresh);
  }
  function apply(s) {
    state = JSON.parse(JSON.stringify(s));
    selectedId = null;
    redraw();
  }
  function undo() {
    if (historyIndex > 0) { historyIndex--; apply(history[historyIndex]); scheduleSave(); }
  }
  function redo() {
    if (historyIndex < history.length - 1) { historyIndex++; apply(history[historyIndex]); scheduleSave(); }
  }

  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 400);
  }
  function saveNow() {
    try {
      const out = JSON.stringify({ objects: state.objects, nextId: state.nextId });
      localStorage.setItem(STORAGE_KEY, out);
      if (status) status.textContent = "Сохранено";
    } catch (e) { console.warn("WB save failed", e); }
  }
  function loadSaved() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const obj = JSON.parse(raw);
      if (obj && Array.isArray(obj.objects)) {
        state.objects = obj.objects;
        state.nextId = obj.nextId || (state.objects.length + 1);
      }
    } catch (e) { console.warn("WB load failed", e); }
  }

  function screenToWorld(sx, sy) {
    return { x: (sx - view.x) / view.scale, y: (sy - view.y) / view.scale };
  }
  function worldToScreen(wx, wy) {
    return { x: wx * view.scale + view.x, y: wy * view.scale + view.y };
  }
  function eventPos(e) {
    const r = canvasEl.getBoundingClientRect();
    const cx = e.clientX !== undefined ? e.clientX : (e.touches && e.touches[0] && e.touches[0].clientX);
    const cy = e.clientY !== undefined ? e.clientY : (e.touches && e.touches[0] && e.touches[0].clientY);
    return { sx: cx - r.left, sy: cy - r.top };
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const r = wrap.getBoundingClientRect();
    canvasEl.width = Math.round(r.width * dpr);
    canvasEl.height = Math.round(r.height * dpr);
    canvasEl.style.width = r.width + "px";
    canvasEl.style.height = r.height + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    redraw();
  }
  window.addEventListener("resize", resize);

  function clearScreen() {
    const r = wrap.getBoundingClientRect();
    ctx.save();
    ctx.fillStyle = "#0f1117";
    ctx.fillRect(0, 0, r.width, r.height);
    ctx.restore();
  }
  function drawGrid() {
    const r = wrap.getBoundingClientRect();
    const step = 40 * view.scale;
    if (step < 8) return;
    ctx.save();
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    const offX = ((view.x % step) + step) % step;
    const offY = ((view.y % step) + step) % step;
    ctx.beginPath();
    for (let x = offX; x < r.width; x += step) { ctx.moveTo(x, 0); ctx.lineTo(x, r.height); }
    for (let y = offY; y < r.height; y += step) { ctx.moveTo(0, y); ctx.lineTo(r.width, y); }
    ctx.stroke();
    const o = worldToScreen(0, 0);
    ctx.strokeStyle = "rgba(139,92,246,0.22)";
    ctx.beginPath();
    ctx.moveTo(o.x, 0); ctx.lineTo(o.x, r.height);
    ctx.moveTo(0, o.y); ctx.lineTo(r.width, o.y);
    ctx.stroke();
    ctx.restore();
  }
  function applyWorld() {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr * view.scale, 0, 0, dpr * view.scale, dpr * view.x, dpr * view.y);
  }
  function resetTr() {
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function redraw() {
    resetTr();
    clearScreen();
    drawGrid();
    applyWorld();
    for (const o of state.objects) {
      drawObj(o, ctx);
      if (o.id === selectedId) drawSel(o);
    }
    if (drag && drag.preview) drawObj(drag.preview, ctx);
    resetTr();
    if (hud) hud.textContent = "zoom " + Math.round(view.scale * 100) + "% | объектов: " + state.objects.length;
  }

  function roundRect(c, x, y, w, h, r) {
    if (w < 2 * r) r = w / 2; if (h < 2 * r) r = h / 2;
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }
  function wrapText(c, t, maxW) {
    const out = [];
    for (const para of String(t || "").split("\n")) {
      const words = para.split(" ");
      let line = "";
      for (const w of words) {
        const tryLine = line ? line + " " + w : w;
        if (c.measureText(tryLine).width > maxW && line) { out.push(line); line = w; }
        else line = tryLine;
      }
      if (line) out.push(line);
      if (!para) out.push("");
    }
    return out;
  }
  function drawObj(o, c) {
    c.save();
    c.lineCap = "round";
    c.lineJoin = "round";
    c.strokeStyle = o.color || "#e6e8ff";
    c.fillStyle = o.color || "#e6e8ff";
    c.lineWidth = o.thickness || 2;
    if (o.kind === "pen" || o.kind === "eraser") {
      if (o.kind === "eraser") { c.globalCompositeOperation = "destination-out"; c.strokeStyle = "#000"; }
      if (o.points && o.points.length >= 2) {
        c.beginPath();
        c.moveTo(o.points[0].x, o.points[0].y);
        for (let i = 1; i < o.points.length; i++) c.lineTo(o.points[i].x, o.points[i].y);
        c.stroke();
      } else if (o.points && o.points.length === 1) {
        c.beginPath();
        c.arc(o.points[0].x, o.points[0].y, (o.thickness || 2) / 2, 0, Math.PI * 2);
        c.fill();
      }
    } else if (o.kind === "rect") {
      c.strokeRect(o.x, o.y, o.w, o.h);
    } else if (o.kind === "ellipse") {
      c.beginPath();
      c.ellipse(o.x + o.w / 2, o.y + o.h / 2, Math.abs(o.w / 2), Math.abs(o.h / 2), 0, 0, Math.PI * 2);
      c.stroke();
    } else if (o.kind === "line") {
      c.beginPath(); c.moveTo(o.x1, o.y1); c.lineTo(o.x2, o.y2); c.stroke();
    } else if (o.kind === "arrow") {
      const dx = o.x2 - o.x1, dy = o.y2 - o.y1;
      const ang = Math.atan2(dy, dx);
      const head = Math.max(10, (o.thickness || 2) * 3);
      c.beginPath(); c.moveTo(o.x1, o.y1); c.lineTo(o.x2, o.y2); c.stroke();
      c.beginPath();
      c.moveTo(o.x2, o.y2);
      c.lineTo(o.x2 - head * Math.cos(ang - Math.PI / 7), o.y2 - head * Math.sin(ang - Math.PI / 7));
      c.lineTo(o.x2 - head * Math.cos(ang + Math.PI / 7), o.y2 - head * Math.sin(ang + Math.PI / 7));
      c.closePath(); c.fill();
    } else if (o.kind === "text") {
      const fs = o.fontSize || 18;
      c.font = fs + 'px ui-sans-serif, system-ui, "Segoe UI", sans-serif';
      c.textBaseline = "top";
      const lines = (o.text || "").split("\n");
      for (let i = 0; i < lines.length; i++) c.fillText(lines[i], o.x, o.y + i * fs * 1.3);
    } else if (o.kind === "sticky") {
      const pad = 12;
      const fs = o.fontSize || 16;
      c.fillStyle = o.bg || "#fde68a";
      c.shadowColor = "rgba(0,0,0,0.35)";
      c.shadowBlur = 14;
      c.shadowOffsetY = 4;
      roundRect(c, o.x, o.y, o.w, o.h, 8);
      c.fill();
      c.shadowBlur = 0; c.shadowOffsetY = 0;
      c.fillStyle = "#1f2937";
      c.font = fs + 'px ui-sans-serif, system-ui, "Segoe UI", sans-serif';
      c.textBaseline = "top";
      const lines = wrapText(c, o.text || "", o.w - pad * 2);
      for (let i = 0; i < lines.length; i++) c.fillText(lines[i], o.x + pad, o.y + pad + i * fs * 1.35);
    } else if (o.kind === "image") {
      if (!o._img) {
        o._img = new Image();
        o._img.onload = () => redraw();
        o._img.src = o.src;
      }
      if (o._img.complete) c.drawImage(o._img, o.x, o.y, o.w, o.h);
    }
    c.restore();
  }
  function drawSel(o) {
    const b = bbox(o);
    if (!b) return;
    ctx.save();
    ctx.strokeStyle = "#8b5cf6";
    ctx.lineWidth = 1.5 / view.scale;
    ctx.setLineDash([6 / view.scale, 4 / view.scale]);
    const pad = 4 / view.scale;
    ctx.strokeRect(b.x - pad, b.y - pad, b.w + 2 * pad, b.h + 2 * pad);
    ctx.restore();
  }
  function bbox(o) {
    if (o.kind === "pen" || o.kind === "eraser") {
      if (!o.points || !o.points.length) return null;
      let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
      for (const p of o.points) {
        if (p.x < a) a = p.x; if (p.y < b) b = p.y;
        if (p.x > c) c = p.x; if (p.y > d) d = p.y;
      }
      return { x: a, y: b, w: c - a, h: d - b };
    }
    if (o.kind === "rect" || o.kind === "ellipse" || o.kind === "sticky" || o.kind === "image" || o.kind === "text") {
      let w = o.w, h = o.h;
      if (o.kind === "text") {
        ctx.save();
        const fs = o.fontSize || 18;
        ctx.font = fs + 'px ui-sans-serif, system-ui, "Segoe UI", sans-serif';
        const lines = (o.text || "").split("\n");
        w = 0;
        for (const ln of lines) w = Math.max(w, ctx.measureText(ln).width);
        h = lines.length * fs * 1.3;
        ctx.restore();
      }
      let x = o.x, y = o.y;
      if (w < 0) { x = o.x + w; w = -w; }
      if (h < 0) { y = o.y + h; h = -h; }
      return { x: x, y: y, w: w, h: h };
    }
    if (o.kind === "line" || o.kind === "arrow") {
      return { x: Math.min(o.x1, o.x2), y: Math.min(o.y1, o.y2), w: Math.abs(o.x2 - o.x1), h: Math.abs(o.y2 - o.y1) };
    }
    return null;
  }
  function hitTest(wx, wy) {
    for (let i = state.objects.length - 1; i >= 0; i--) {
      const o = state.objects[i];
      const b = bbox(o);
      if (!b) continue;
      const t = 6 / view.scale;
      if (wx >= b.x - t && wx <= b.x + b.w + t && wy >= b.y - t && wy <= b.y + b.h + t) return o;
    }
    return null;
  }

  // Точечный hit-test для ластика: считаем что объект "задет",
  // если ЛЮБАЯ его точка/сегмент находится в радиусе r от (wx,wy).
  function _distSq(ax, ay, bx, by) {
    const dx = ax - bx, dy = ay - by;
    return dx*dx + dy*dy;
  }
  function _segPointDistSq(px, py, ax, ay, bx, by) {
    const dx = bx - ax, dy = by - ay;
    const len2 = dx*dx + dy*dy;
    if (len2 < 1e-9) return _distSq(px, py, ax, ay);
    let t = ((px - ax) * dx + (py - ay) * dy) / len2;
    t = Math.max(0, Math.min(1, t));
    return _distSq(px, py, ax + t*dx, ay + t*dy);
  }
  function eraserHits(wx, wy, radius) {
    // Возвращает индексы объектов, которые задеты ластиком в точке (wx,wy).
    const r2 = radius * radius;
    const hits = [];
    for (let i = state.objects.length - 1; i >= 0; i--) {
      const o = state.objects[i];
      if (o.kind === "eraser") continue; // старые eraser-обводки игнорируем
      // pen-обводки — проверяем сегменты
      if (o.kind === "pen") {
        if (!o.points || !o.points.length) continue;
        let hit = false;
        if (o.points.length === 1) {
          hit = _distSq(wx, wy, o.points[0].x, o.points[0].y) <= r2;
        } else {
          for (let k = 1; k < o.points.length; k++) {
            if (_segPointDistSq(wx, wy, o.points[k-1].x, o.points[k-1].y, o.points[k].x, o.points[k].y) <= r2) {
              hit = true; break;
            }
          }
        }
        if (hit) hits.push(i);
        continue;
      }
      // Прямоугольники / эллипсы / стикеры / картинки / текст — bbox
      const b = bbox(o);
      if (!b) continue;
      if (wx >= b.x - radius && wx <= b.x + b.w + radius &&
          wy >= b.y - radius && wy <= b.y + b.h + radius) {
        hits.push(i);
        continue;
      }
      // Линии / стрелки — точное расстояние до отрезка
      if (o.kind === "line" || o.kind === "arrow") {
        if (_segPointDistSq(wx, wy, o.x1, o.y1, o.x2, o.y2) <= r2) hits.push(i);
      }
    }
    return hits;
  }
  function eraseAt(wx, wy, radius) {
    const idxs = eraserHits(wx, wy, radius);
    if (!idxs.length) return false;
    // Удаляем по убыванию индекса
    idxs.sort((a, b) => b - a);
    for (const i of idxs) state.objects.splice(i, 1);
    return true;
  }
  function moveObj(o, dx, dy) {
    if (o.kind === "pen" || o.kind === "eraser") {
      for (const p of o.points) { p.x += dx; p.y += dy; }
    } else if (o.kind === "rect" || o.kind === "ellipse" || o.kind === "sticky" || o.kind === "image" || o.kind === "text") {
      o.x += dx; o.y += dy;
    } else if (o.kind === "line" || o.kind === "arrow") {
      o.x1 += dx; o.y1 += dy; o.x2 += dx; o.y2 += dy;
    }
  }

  // Build SVG data-URI cursors so each tool has a distinct, "Thalamus-like" pointer.
  function svgCursor(svg, hotX, hotY) {
    const enc = encodeURIComponent(svg)
      .replace(/'/g, "%27")
      .replace(/"/g, "%22");
    return "url(\"data:image/svg+xml;utf8," + enc + "\") " + hotX + " " + hotY + ", crosshair";
  }
  function cursorForTool(t, c) {
    const stroke = (c || color || "#e6e8ff");
    if (t === "select") return "default";
    if (t === "pen") {
      // Карандаш: рисуем тело вертикально внутри SVG, кончик грифеля в точке (16, 27).
      // Поворачиваем на +135° вокруг (16, 16) — карандаш «смотрит» острием в верхний-левый
      // угол курсора (как обычный writing-cursor). После поворота (16, 27) -> (16-11*cos45, 16-11*sin45) ≈ (8.2, 8.2).
      // Hotspot ставим точно в визуальный кончик грифеля.
      const TIP_X = 8, TIP_Y = 8;
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">' +
          '<g transform="rotate(135 16 16)">' +
            '<rect x="13" y="3"  width="6" height="16" fill="#f4d35e" stroke="#1f2937" stroke-width="1.2"/>' +
            '<rect x="13" y="3"  width="6" height="3"  fill="#e07a5f" stroke="#1f2937" stroke-width="1.2"/>' +
            '<polygon points="13,19 19,19 16,27" fill="#f5deb3" stroke="#1f2937" stroke-width="1.2"/>' +
            '<polygon points="14.5,24 17.5,24 16,27" fill="#1f2937"/>' +
            '<rect x="13" y="6.5" width="6" height="1.2" fill="#1f2937" opacity="0.7"/>' +
          '</g>' +
          // Цветной маркер прямо под остриём — подтверждает hotspot
          '<circle cx="' + TIP_X + '" cy="' + TIP_Y + '" r="1.3" fill="' + stroke + '" stroke="#0b1020" stroke-width="0.7"/>' +
        '</svg>';
      return svgCursor(svg, TIP_X, TIP_Y);
    }
    if (t === "eraser") {
      // Eraser block, hotspot at tip (4, 28).
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">' +
          '<g transform="rotate(-30 16 16)">' +
            '<rect x="6"  y="14" width="20" height="10" rx="1.5" fill="#ff7a90" stroke="#1f2937" stroke-width="1.3"/>' +
            '<rect x="6"  y="14" width="20" height="4"  rx="1.5" fill="#ffd5dd" stroke="#1f2937" stroke-width="1.3"/>' +
            '<line x1="12" y1="14" x2="12" y2="24" stroke="#1f2937" stroke-width="0.8" opacity="0.5"/>' +
            '<line x1="20" y1="14" x2="20" y2="24" stroke="#1f2937" stroke-width="0.8" opacity="0.5"/>' +
          '</g>' +
        '</svg>';
      return svgCursor(svg, 4, 28);
    }
    if (t === "objErase") {
      // Корзина — ластик «удалить объект целиком», hotspot в центре корзины (16, 18).
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">' +
          '<rect x="10" y="6" width="12" height="3" rx="1" fill="#ff7a90" stroke="#1f2937" stroke-width="1.2"/>' +
          '<rect x="14" y="3" width="4"  height="3" rx="0.6" fill="#ff7a90" stroke="#1f2937" stroke-width="1.2"/>' +
          '<path d="M9 9 L23 9 L21.5 27 Q21.4 28.4 20 28.4 L12 28.4 Q10.6 28.4 10.5 27 Z" fill="#ffe4ea" stroke="#1f2937" stroke-width="1.3"/>' +
          '<line x1="13" y1="13" x2="13.5" y2="25" stroke="#1f2937" stroke-width="1"/>' +
          '<line x1="16" y1="13" x2="16"   y2="25" stroke="#1f2937" stroke-width="1"/>' +
          '<line x1="19" y1="13" x2="18.5" y2="25" stroke="#1f2937" stroke-width="1"/>' +
        '</svg>';
      return svgCursor(svg, 16, 18);
    }
    if (t === "rect") {
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">' +
          '<rect x="6" y="6" width="16" height="12" fill="none" stroke="' + stroke + '" stroke-width="2"/>' +
          '<circle cx="14" cy="14" r="1.2" fill="' + stroke + '"/>' +
        '</svg>';
      return svgCursor(svg, 14, 14);
    }
    if (t === "ellipse") {
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">' +
          '<ellipse cx="14" cy="14" rx="9" ry="6" fill="none" stroke="' + stroke + '" stroke-width="2"/>' +
          '<circle cx="14" cy="14" r="1.2" fill="' + stroke + '"/>' +
        '</svg>';
      return svgCursor(svg, 14, 14);
    }
    if (t === "line") {
      // По запросу пользователя — для «прямой линии» используем системный
      // курсор-стрелку (как у мышки в Windows/macOS). Так визуально понятно,
      // что инструмент «точно ставит» точки начала и конца отрезка.
      return "default";
    }
    if (t === "arrow") {
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">' +
          '<line x1="4" y1="22" x2="22" y2="6" stroke="' + stroke + '" stroke-width="2.2" stroke-linecap="round"/>' +
          '<polygon points="22,6 16,7 21,12" fill="' + stroke + '"/>' +
          '<circle cx="14" cy="14" r="1.2" fill="' + stroke + '"/>' +
        '</svg>';
      return svgCursor(svg, 14, 14);
    }
    if (t === "text") {
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="28" viewBox="0 0 20 28">' +
          '<text x="3" y="20" font-family="Georgia, serif" font-size="22" font-weight="700" fill="' + stroke + '" stroke="#0b1020" stroke-width="0.6">T</text>' +
        '</svg>';
      return svgCursor(svg, 6, 22);
    }
    if (t === "sticky") {
      const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28">' +
          '<rect x="4" y="5" width="20" height="18" fill="#fde68a" stroke="#1f2937" stroke-width="1.3"/>' +
          '<polygon points="20,23 24,23 24,19" fill="#f3c969" stroke="#1f2937" stroke-width="1.3"/>' +
          '<line x1="7"  y1="10" x2="20" y2="10" stroke="#1f2937" stroke-width="1"/>' +
          '<line x1="7"  y1="14" x2="20" y2="14" stroke="#1f2937" stroke-width="1"/>' +
          '<line x1="7"  y1="18" x2="16" y2="18" stroke="#1f2937" stroke-width="1"/>' +
        '</svg>';
      return svgCursor(svg, 4, 5);
    }
    return "crosshair";
  }

  function applyCursor() {
    canvasEl.style.cursor = spaceDown ? "grab" : cursorForTool(tool, color);
  }

  function setTool(t) {
    tool = t;
    document.querySelectorAll("#wbToolbar .wb-tool").forEach(b => b.classList.toggle("active", b.dataset.tool === t));
    applyCursor();
    if (t !== "select") selectedId = null;
    redraw();
  }
  function setColor(c) {
    color = c;
    document.querySelectorAll(".wb-color").forEach(b => b.classList.toggle("active", b.dataset.color === c));
    applyCursor();
    if (selectedId) {
      const o = state.objects.find(x => x.id === selectedId);
      if (o && o.kind !== "eraser" && o.kind !== "sticky" && o.kind !== "image") {
        o.color = c; pushHistory(); redraw();
      }
    }
  }

  function onDown(e) {
    if (e.target !== canvasEl) return;
    e.preventDefault();
    if (canvasEl.setPointerCapture) try { canvasEl.setPointerCapture(e.pointerId); } catch (_) {}
    const p = eventPos(e);
    const w = screenToWorld(p.sx, p.sy);
    if (e.button === 1 || spaceDown || e.button === 2) {
      drag = { kind: "pan", startX: p.sx, startY: p.sy, vx: view.x, vy: view.y };
      canvasEl.style.cursor = "grabbing";
      return;
    }
    if (tool === "select") {
      const h = hitTest(w.x, w.y);
      if (h) { selectedId = h.id; drag = { kind: "move", id: h.id, startX: w.x, startY: w.y }; }
      else selectedId = null;
      redraw(); return;
    }
    if (tool === "objErase") {
      // Стереть один объект целиком по клику
      const h = hitTest(w.x, w.y);
      if (h) {
        const idx = state.objects.findIndex(x => x.id === h.id);
        if (idx >= 0) {
          state.objects.splice(idx, 1);
          pushHistory();
          redraw();
        }
      }
      drag = { kind: "objErase" }; // дальше можно перетаскивать — будем стирать ещё
      return;
    }
    if (tool === "eraser") {
      // Векторный ластик: удаляем объекты, чьи штрихи попадают под радиус кисти.
      // Радиус берём из текущей толщины (минимум 12 px в world-координатах).
      const r = Math.max(12 / view.scale, (thickness || 2) * 4 / view.scale);
      eraseAt(w.x, w.y, r);
      redraw();
      drag = { kind: "erase", radius: r, lastX: w.x, lastY: w.y };
      return;
    }
    if (tool === "pen") {
      drag = { kind: "stroke", preview: { id: uid(), kind: "pen", color: color, thickness: thickness, points: [{ x: w.x, y: w.y }] } };
      return;
    }
    if (tool === "rect" || tool === "ellipse") {
      drag = { kind: "shape", preview: { id: uid(), kind: tool, color: color, thickness: thickness, x: w.x, y: w.y, w: 0, h: 0 } };
      return;
    }
    if (tool === "line" || tool === "arrow") {
      drag = { kind: "segment", preview: { id: uid(), kind: tool, color: color, thickness: thickness, x1: w.x, y1: w.y, x2: w.x, y2: w.y } };
      return;
    }
    if (tool === "text") { openEditor(w.x, w.y, null, "text"); return; }
    if (tool === "sticky") {
      const obj = { id: uid(), kind: "sticky", x: w.x, y: w.y, w: 200, h: 140, bg: "#fde68a", color: "#1f2937", text: "", fontSize: 16 };
      state.objects.push(obj);
      pushHistory();
      selectedId = obj.id;
      openEditor(obj.x, obj.y, obj.id, "sticky");
      redraw();
      return;
    }
  }
  function onMove(e) {
    if (!drag) return;
    const p = eventPos(e);
    if (drag.kind === "pan") {
      view.x = drag.vx + (p.sx - drag.startX);
      view.y = drag.vy + (p.sy - drag.startY);
      redraw(); return;
    }
    const w = screenToWorld(p.sx, p.sy);
    if (drag.kind === "stroke") { drag.preview.points.push({ x: w.x, y: w.y }); redraw(); }
    else if (drag.kind === "shape") { drag.preview.w = w.x - drag.preview.x; drag.preview.h = w.y - drag.preview.y; redraw(); }
    else if (drag.kind === "segment") { drag.preview.x2 = w.x; drag.preview.y2 = w.y; redraw(); }
    else if (drag.kind === "erase") {
      // Векторный ластик при перетаскивании: проходим по короткой линии
      // от прошлой точки до текущей, стираем по точкам с шагом ~radius/2
      const r = drag.radius;
      const dx = w.x - drag.lastX, dy = w.y - drag.lastY;
      const dist = Math.hypot(dx, dy);
      const step = Math.max(r / 2, 1);
      const n = Math.max(1, Math.ceil(dist / step));
      let changed = false;
      for (let s = 1; s <= n; s++) {
        const t = s / n;
        if (eraseAt(drag.lastX + dx * t, drag.lastY + dy * t, r)) changed = true;
      }
      drag.lastX = w.x; drag.lastY = w.y;
      if (changed) redraw();
    }
    else if (drag.kind === "objErase") {
      // Удалить ещё один объект при перетаскивании
      const h = hitTest(w.x, w.y);
      if (h) {
        const idx = state.objects.findIndex(x => x.id === h.id);
        if (idx >= 0) { state.objects.splice(idx, 1); redraw(); }
      }
    }
    else if (drag.kind === "move") {
      const dx = w.x - drag.startX, dy = w.y - drag.startY;
      drag.startX = w.x; drag.startY = w.y;
      const o = state.objects.find(x => x.id === drag.id);
      if (o) moveObj(o, dx, dy);
      redraw();
    }
  }
  function onUp() {
    if (!drag) return;
    if (drag.kind === "pan") { drag = null; applyCursor(); return; }
    if (drag.kind === "stroke" && drag.preview && drag.preview.points.length >= 1) { state.objects.push(drag.preview); pushHistory(); }
    else if (drag.kind === "shape" && drag.preview) {
      if (Math.abs(drag.preview.w) > 2 && Math.abs(drag.preview.h) > 2) {
        if (drag.preview.w < 0) { drag.preview.x += drag.preview.w; drag.preview.w = -drag.preview.w; }
        if (drag.preview.h < 0) { drag.preview.y += drag.preview.h; drag.preview.h = -drag.preview.h; }
        state.objects.push(drag.preview); pushHistory();
      }
    } else if (drag.kind === "segment" && drag.preview) {
      if (Math.hypot(drag.preview.x2 - drag.preview.x1, drag.preview.y2 - drag.preview.y1) > 3) {
        state.objects.push(drag.preview); pushHistory();
      }
    } else if (drag.kind === "erase" || drag.kind === "objErase") {
      // Любое стирание попадает в историю одной операцией
      pushHistory();
    } else if (drag.kind === "move") {
      pushHistory();
    }
    drag = null;
    redraw();
  }
  canvasEl.addEventListener("pointerdown", onDown);
  canvasEl.addEventListener("pointermove", onMove);
  canvasEl.addEventListener("pointerup", onUp);
  canvasEl.addEventListener("pointercancel", onUp);
  canvasEl.addEventListener("contextmenu", e => e.preventDefault());

  canvasEl.addEventListener("wheel", function (e) {
    e.preventDefault();
    const p = eventPos(e);
    if (e.ctrlKey || e.metaKey) {
      zoomAt(p.sx, p.sy, e.deltaY > 0 ? 0.9 : 1.1);
    } else {
      view.x -= e.deltaX;
      view.y -= e.deltaY;
      redraw();
    }
  }, { passive: false });

  function zoomAt(sx, sy, f) {
    const w = screenToWorld(sx, sy);
    view.scale = Math.min(8, Math.max(0.1, view.scale * f));
    const s2 = worldToScreen(w.x, w.y);
    view.x += sx - s2.x;
    view.y += sy - s2.y;
    redraw();
  }

  function openEditor(wx, wy, objId, kind) {
    const s = worldToScreen(wx, wy);
    textEditor.style.display = "block";
    textEditor.style.left = s.x + "px";
    textEditor.style.top = s.y + "px";
    if (kind === "sticky") {
      const obj = state.objects.find(o => o.id === objId);
      textEditor.style.width = (obj.w * view.scale) + "px";
      textEditor.style.height = (obj.h * view.scale) + "px";
      textEditor.style.color = obj.color || "#1f2937";
      textEditor.style.background = obj.bg || "#fde68a";
      textEditor.style.fontSize = ((obj.fontSize || 16) * view.scale) + "px";
      textEditor.value = obj.text || "";
      editingId = objId;
    } else {
      textEditor.style.width = "320px";
      textEditor.style.height = "60px";
      textEditor.style.color = color;
      textEditor.style.background = "transparent";
      textEditor.style.fontSize = (18 * view.scale) + "px";
      textEditor.value = "";
      editingId = { newAt: { x: wx, y: wy } };
    }
    setTimeout(function () { textEditor.focus(); }, 30);
  }
  function closeEditor(commit) {
    if (!textEditor || textEditor.style.display === "none") return;
    const v = textEditor.value;
    textEditor.style.display = "none";
    if (commit && editingId) {
      if (typeof editingId === "object" && editingId.newAt) {
        if ((v || "").trim()) {
          state.objects.push({ id: uid(), kind: "text", x: editingId.newAt.x, y: editingId.newAt.y, text: v, color: color, fontSize: 18 });
          pushHistory();
        }
      } else {
        const o = state.objects.find(x => x.id === editingId);
        if (o) { o.text = v; pushHistory(); }
      }
    }
    editingId = null;
    redraw();
  }
  textEditor.addEventListener("blur", function () { closeEditor(true); });
  textEditor.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { e.preventDefault(); closeEditor(false); }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); closeEditor(true); }
  });
  canvasEl.addEventListener("dblclick", function (e) {
    const p = eventPos(e);
    const w = screenToWorld(p.sx, p.sy);
    const h = hitTest(w.x, w.y);
    if (h && (h.kind === "text" || h.kind === "sticky")) {
      selectedId = h.id;
      openEditor(h.x, h.y, h.id, h.kind);
    }
  });

  window.addEventListener("keydown", function (e) {
    // Пользователь печатает текст / редактирует поле — не перехватываем шорткаты.
    var tg = e.target;
    if (tg && (tg.tagName === "TEXTAREA" || tg.tagName === "INPUT" || tg.tagName === "SELECT" || tg.isContentEditable)) return;

    if (e.code === "Space") { spaceDown = true; applyCursor(); e.preventDefault(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undo(); return; }
    if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))) {
      e.preventDefault(); redo(); return;
    }
    if (e.key === "Delete" || e.key === "Backspace") {
      if (selectedId !== null) {
        e.preventDefault();
        state.objects = state.objects.filter(o => o.id !== selectedId);
        selectedId = null;
        pushHistory(); redraw();
      }
    }
    // Однобуквенные хоткеи переключения инструмента — только без Ctrl/Cmd,
    // чтобы Ctrl+V / Ctrl+X не превращались в setTool('select') / setTool('objErase').
    if (!e.ctrlKey && !e.metaKey && !e.altKey) {
      const map = { v: "select", p: "pen", e: "eraser", x: "objErase", r: "rect", o: "ellipse", l: "line", a: "arrow", t: "text", s: "sticky" };
      const tool2 = map[e.key.toLowerCase()];
      if (tool2) { setTool(tool2); }
    }
  });
  window.addEventListener("keyup", function (e) {
    if (e.code === "Space") { spaceDown = false; applyCursor(); }
  });

  // ===== WB_SHORTCUTS_V1 =====
  var wbClipboard = null;

  function _wbClone(o) {
    try { return JSON.parse(JSON.stringify(o)); } catch (_) { return null; }
  }

  function _wbOffset(o, dx, dy) {
    if (!o || typeof o !== "object") return;
    var ks = ["x","y","x1","y1","x2","y2","cx","cy"];
    for (var i=0;i<ks.length;i++) {
      var k = ks[i];
      if (typeof o[k] === "number") {
        if (k === "y" || k === "y1" || k === "y2" || k === "cy") o[k] += dy;
        else o[k] += dx;
      }
    }
    if (Array.isArray(o.points)) {
      for (var p=0;p<o.points.length;p++) {
        var pt = o.points[p];
        if (pt && typeof pt.x === "number") pt.x += dx;
        if (pt && typeof pt.y === "number") pt.y += dy;
      }
    }
  }

  function _wbGetSel() {
    if (selectedId == null) return null;
    for (var i=0;i<state.objects.length;i++) {
      if (state.objects[i].id === selectedId) return state.objects[i];
    }
    return null;
  }

  function _wbCopy() {
    var o = _wbGetSel();
    if (!o) return false;
    wbClipboard = _wbClone(o);
    return true;
  }

  function _wbPaste() {
    if (!wbClipboard) return false;
    var clone = _wbClone(wbClipboard);
    if (!clone) return false;
    clone.id = uid();
    _wbOffset(clone, 20, 20);
    state.objects.push(clone);
    selectedId = clone.id;
    pushHistory(); redraw();
    return true;
  }

  function _wbCut() {
    var o = _wbGetSel();
    if (!o) return false;
    wbClipboard = _wbClone(o);
    state.objects = state.objects.filter(function(x){ return x.id !== selectedId; });
    selectedId = null;
    pushHistory(); redraw();
    return true;
  }

  function _wbDuplicate() {
    var o = _wbGetSel();
    if (!o) return false;
    var clone = _wbClone(o);
    clone.id = uid();
    _wbOffset(clone, 20, 20);
    state.objects.push(clone);
    selectedId = clone.id;
    pushHistory(); redraw();
    return true;
  }

  function _wbSelectAll() {
    // Single-select fallback: pick last (top-most) object
    if (!state.objects.length) return false;
    selectedId = state.objects[state.objects.length - 1].id;
    redraw();
    return true;
  }

  function _wbNudge(dx, dy) {
    var o = _wbGetSel();
    if (!o) return false;
    moveObj(o, dx, dy);
    pushHistory(); redraw();
    return true;
  }

  function _wbDeselect() {
    if (selectedId == null) return false;
    selectedId = null;
    redraw();
    return true;
  }

  function _wbExport() {
    var btn = document.getElementById("wbExport");
    if (btn) { btn.click(); return true; }
    return false;
  }

  function _wbIsEditableTarget(t) {
    if (!t) return false;
    var tag = t.tagName;
    if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return true;
    if (t.isContentEditable) return true;
    return false;
  }

  window.addEventListener("keydown", function (e) {
    // Если пользователь печатает текст — не перехватываем горячие клавиши.
    if (_wbIsEditableTarget(e.target)) return;
    var k = (e.key || "").toLowerCase();
    var ctrl = e.ctrlKey || e.metaKey;

    // Copy / Cut / Paste / Duplicate / Select-all — всегда preventDefault,
    // чтобы браузер не делал нативное действие (selection страницы и т.п.).
    if (ctrl && k === "c") { e.preventDefault(); _wbCopy(); return; }
    if (ctrl && k === "x") { e.preventDefault(); _wbCut(); return; }
    if (ctrl && k === "v") { e.preventDefault(); _wbPaste(); return; }
    if (ctrl && k === "d") { e.preventDefault(); _wbDuplicate(); return; }
    if (ctrl && k === "a") { e.preventDefault(); _wbSelectAll(); return; }
    if (ctrl && k === "s") { e.preventDefault(); _wbExport(); return; }
    if (k === "escape")    { e.preventDefault(); _wbDeselect(); return; }
    if (k === "arrowleft" || k === "arrowright" || k === "arrowup" || k === "arrowdown") {
      var step = e.shiftKey ? 10 : 1;
      var dx = 0, dy = 0;
      if (k === "arrowleft") dx = -step;
      else if (k === "arrowright") dx = step;
      else if (k === "arrowup") dy = -step;
      else dy = step;
      if (_wbNudge(dx, dy)) e.preventDefault();
      return;
    }
  });

  // Paste image from system clipboard onto the whiteboard.
  document.addEventListener("paste", function (e) {
    if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
    if (!e.clipboardData || !e.clipboardData.items) return;
    var items = e.clipboardData.items;
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      if (it && it.kind === "file" && it.type && it.type.indexOf("image/") === 0) {
        var file = it.getAsFile();
        if (!file) continue;
        var reader = new FileReader();
        reader.onload = function (ev) {
          var src = ev.target && ev.target.result;
          if (src && window.WB && typeof window.WB.importImage === "function") {
            window.WB.importImage(src);
          }
        };
        reader.readAsDataURL(file);
        e.preventDefault();
        return;
      }
    }
  });
  // ===== /WB_SHORTCUTS_V1 =====


  document.querySelectorAll("#wbToolbar .wb-tool").forEach(b => b.addEventListener("click", () => setTool(b.dataset.tool)));
  document.querySelectorAll(".wb-color").forEach(b => b.addEventListener("click", () => setColor(b.dataset.color)));
  const thickEl = document.getElementById("wbThickness");
  if (thickEl) thickEl.addEventListener("input", () => { thickness = parseInt(thickEl.value, 10) || 3; });

  document.getElementById("wbUndo").onclick = undo;
  document.getElementById("wbRedo").onclick = redo;
  document.getElementById("wbZoomIn").onclick = function () {
    const r = wrap.getBoundingClientRect();
    zoomAt(r.width / 2, r.height / 2, 1.2);
  };
  document.getElementById("wbZoomOut").onclick = function () {
    const r = wrap.getBoundingClientRect();
    zoomAt(r.width / 2, r.height / 2, 1 / 1.2);
  };
  document.getElementById("wbZoomReset").onclick = function () {
    view = { x: 0, y: 0, scale: 1 }; redraw();
  };
  document.getElementById("wbFit").onclick = fitToContent;

  function fitToContent() {
    if (!state.objects.length) { view = { x: 0, y: 0, scale: 1 }; redraw(); return; }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const o of state.objects) {
      const b = bbox(o);
      if (!b) continue;
      if (b.x < minX) minX = b.x;
      if (b.y < minY) minY = b.y;
      if (b.x + b.w > maxX) maxX = b.x + b.w;
      if (b.y + b.h > maxY) maxY = b.y + b.h;
    }
    if (!isFinite(minX)) return;
    const r = wrap.getBoundingClientRect();
    const pad = 60;
    const sx = (r.width - pad * 2) / (maxX - minX || 1);
    const sy = (r.height - pad * 2) / (maxY - minY || 1);
    view.scale = Math.min(2, Math.max(0.1, Math.min(sx, sy)));
    view.x = pad - minX * view.scale;
    view.y = pad - minY * view.scale;
    redraw();
  }

  document.getElementById("wbClear").onclick = function () {
    if (!state.objects.length) return;
    if (!confirm("Очистить всю доску? После перезагрузки страницы это не отменить.")) return;
    state.objects = [];
    selectedId = null;
    pushHistory();
    redraw();
  };

  document.getElementById("wbExport").onclick = function () {
    if (!state.objects.length) { alert("Доска пуста"); return; }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const o of state.objects) {
      const b = bbox(o);
      if (!b) continue;
      if (b.x < minX) minX = b.x;
      if (b.y < minY) minY = b.y;
      if (b.x + b.w > maxX) maxX = b.x + b.w;
      if (b.y + b.h > maxY) maxY = b.y + b.h;
    }
    const pad = 24;
    const w = (maxX - minX) + pad * 2;
    const h = (maxY - minY) + pad * 2;
    const tmp = document.createElement("canvas");
    tmp.width = Math.max(64, Math.ceil(w));
    tmp.height = Math.max(64, Math.ceil(h));
    const tctx = tmp.getContext("2d");
    tctx.fillStyle = "#ffffff";
    tctx.fillRect(0, 0, tmp.width, tmp.height);
    tctx.translate(pad - minX, pad - minY);
    for (const o of state.objects) {
      if (o.kind === "eraser") continue;
      drawObj(o, tctx);
    }
    tmp.toBlob(function (blob) {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "whiteboard.png"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, "image/png");
  };

  const importInput = document.getElementById("wbImportInput");
  document.getElementById("wbImport").onclick = function () { importInput.click(); };
  importInput.addEventListener("change", function (e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = function (ev) {
      const src = ev.target.result;
      const img = new Image();
      img.onload = function () {
        const r2 = wrap.getBoundingClientRect();
        const center = screenToWorld(r2.width / 2, r2.height / 2);
        const maxDim = 600;
        let iw = img.naturalWidth, ih = img.naturalHeight;
        if (Math.max(iw, ih) > maxDim) {
          const k = maxDim / Math.max(iw, ih);
          iw = Math.round(iw * k); ih = Math.round(ih * k);
        }
        state.objects.push({
          id: uid(), kind: "image", src: src,
          x: center.x - iw / 2, y: center.y - ih / 2, w: iw, h: ih
        });
        pushHistory();
        redraw();
      };
      img.src = src;
    };
    r.readAsDataURL(f);
    importInput.value = "";
  });

  // ── Apply a remote operation locally without echoing it back ─────
  // Used by wb_meet.js when it receives a data packet from another
  // participant.  We bump _suppressBroadcastDepth so the resulting
  // pushHistory() does NOT trigger _diffAndBroadcast (otherwise we'd
  // ping-pong forever).
  function applyRemoteOp(op) {
    if (!op || typeof op !== "object") return;
    _suppressBroadcastDepth++;
    try {
      if (op.op === "snapshot" && op.state && Array.isArray(op.state.objects)) {
        state.objects = JSON.parse(JSON.stringify(op.state.objects));
        if (typeof op.state.nextId === "number") {
          state.nextId = Math.max(state.nextId, op.state.nextId);
        }
        selectedId = null;
      } else if (op.op === "clear") {
        state.objects = [];
        if (typeof op.nextId === "number") {
          state.nextId = Math.max(state.nextId, op.nextId);
        }
        selectedId = null;
      } else if (op.op === "ops") {
        // Last-write-wins: incoming adds replace any local object with
        // the same id; updates overwrite by id; removes delete by id.
        const removeSet = new Set(Array.isArray(op.removes) ? op.removes : []);
        if (removeSet.size) {
          state.objects = state.objects.filter(function (o) { return !removeSet.has(o.id); });
          if (removeSet.has(selectedId)) selectedId = null;
        }
        const byId = new Map();
        for (let i = 0; i < state.objects.length; i++) byId.set(state.objects[i].id, i);
        const upserts = [].concat(
          Array.isArray(op.adds) ? op.adds : [],
          Array.isArray(op.updates) ? op.updates : []
        );
        for (const incoming of upserts) {
          if (!incoming || typeof incoming.id === "undefined") continue;
          const idx = byId.get(incoming.id);
          // Drop transient cached fields (e.g. _img) from the wire.
          const clean = JSON.parse(JSON.stringify(incoming));
          if (typeof idx === "number") {
            state.objects[idx] = clean;
          } else {
            state.objects.push(clean);
            byId.set(clean.id, state.objects.length - 1);
          }
        }
        if (typeof op.nextId === "number") {
          state.nextId = Math.max(state.nextId, op.nextId);
        }
      } else {
        return; // unknown op kind
      }
      // Commit the remote change to history (so undo still works for
      // the local user) AND repaint.  pushHistory will detect the
      // suppression flag and skip the rebroadcast.
      pushHistory();
      redraw();
    } finally {
      _suppressBroadcastDepth--;
    }
  }

  // Public API for tab-switch hook
  window.WB = {
    resize: resize,
    redraw: redraw,
    // ── Collaboration hooks (called by static/js/wb_meet.js) ────────
    // Return a serialisable copy of the canvas state, used by the
    // first responder when a newcomer joins the LiveKit room.
    getSnapshot: function () {
      return { objects: JSON.parse(JSON.stringify(state.objects)), nextId: state.nextId };
    },
    // Apply ONE remote operation (snapshot / clear / ops) locally.
    applyRemoteOp: applyRemoteOp,
    // Apply a batch of operations atomically.
    applyRemoteOps: function (ops) {
      if (!Array.isArray(ops)) return;
      for (const op of ops) applyRemoteOp(op);
    },
    importImage: function (src) {
      if (!src) return;
      const img = new Image();
      img.onload = function () {
        const r2 = wrap.getBoundingClientRect();
        const center = screenToWorld(r2.width / 2, r2.height / 2);
        const maxDim = 700;
        let iw = img.naturalWidth, ih = img.naturalHeight;
        if (Math.max(iw, ih) > maxDim) {
          const k = maxDim / Math.max(iw, ih);
          iw = Math.round(iw * k); ih = Math.round(ih * k);
        }
        state.objects.push({
          id: uid(), kind: "image", src: src,
          x: center.x - iw / 2, y: center.y - ih / 2, w: iw, h: ih
        });
        pushHistory();
        redraw();
      };
      img.src = src;
    },
  };

  // Boot
  loadSaved();
  pushHistory();   // initial snapshot for undo
  resize();
})();
