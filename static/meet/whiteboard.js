/* whiteboard.js — FORMYLA интерактивная доска v2 (ядро: константы, иконки, стили + загрузчик частей из папки wb/)
   Источник: репозиторий formyla-meet (whiteboard.js + wb/). API: new Whiteboard(root, { title, overlay, onClose, onChange, onCursor, collaborators, fitSpace, underlay }) */
(function () {
  'use strict';
  const COLORS = ['#0f172a', '#ef4444', '#f59e0b', '#22c55e', '#38bdf8', '#8b5cf6', '#ec4899', '#ffffff'];
  const SIZES = [2, 4, 8, 14];
  const NOTE_COLORS = ['#fef08a', '#bbf7d0', '#bae6fd', '#e9d5ff', '#fecdd3'];
  const STAMPS = ['👍', '✅', '❗', '🔥', '💡', '⭐', '🎯', '❤️', '❓', '✏️'];
  const PIE_COLORS = ['#6d28d9', '#38bdf8', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6', '#ec4899'];
  const TEMPLATES = {
    lesson: { name: 'Разбор задачи: условие · дано · решение · ответ', icon: 'type' },
    kanban: { name: 'Канбан-доска проекта', icon: 'board' },
    swot: { name: 'SWOT-анализ', icon: 'grid' },
    bmc: { name: 'Business Model Canvas', icon: 'layout' },
    roadmap: { name: 'Дорожная карта (кварталы)', icon: 'calendar' },
    retro: { name: 'Ретроспектива команды', icon: 'smile' },
    eisenhower: { name: 'Матрица Эйзенхауэра', icon: 'filter' },
  };
  const BGS = [['plain', 'Без сетки', 'square'], ['grid', 'Клетка', 'grid'], ['dots', 'Точки', 'more'], ['lined', 'Линейка', 'layout']];
  const FONT = 'Satoshi, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  const EMOJI_FONT = '"Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif';
  const MIN_ZOOM = 0.1, MAX_ZOOM = 8;
  const LINE_TYPES = { line: 1, arrow: 1, darrow: 1 };
  const clone = o => JSON.parse(JSON.stringify(o));
  const uid = () => Date.now() + Math.random();
  const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const svg = p => `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
  const ICONS = {
    board: svg('<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>'),
    cursor: svg('<path d="M4 3l7 17 2.5-6.5L20 11z"/>'),
    hand: svg('<path d="M8 13V5a2 2 0 1 1 4 0v6M12 11V4a2 2 0 1 1 4 0v7M16 11V6a2 2 0 1 1 4 0v8a7 7 0 0 1-14 0v-3a2 2 0 1 1 4 0"/>'),
    pen: svg('<path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/>'),
    highlighter: svg('<path d="M9 11l-6 6v3h9l3-3"/><path d="M22 12l-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>'),
    line: svg('<path d="M4 20L20 4"/>'),
    arrow: svg('<path d="M5 19L19 5M9 5h10v10"/>'),
    darrow: svg('<path d="M4 12h16M8 8l-4 4 4 4M16 8l4 4-4 4"/>'),
    square: svg('<rect x="4" y="4" width="16" height="16" rx="2"/>'),
    circle: svg('<circle cx="12" cy="12" r="9"/>'),
    triangle: svg('<path d="M12 4l9 16H3z"/>'),
    diamond: svg('<path d="M12 3l9 9-9 9-9-9z"/>'),
    type: svg('<path d="M4 7V4h16v3M9 20h6M12 4v16"/>'),
    note: svg('<path d="M4 4h16v10l-6 6H4z"/><path d="M14 20v-6h6"/>'),
    smile: svg('<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/>'),
    chart: svg('<path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/>'),
    eraser: svg('<path d="M20 20H8L3.5 15.5a2 2 0 0 1 0-2.8L13 3.3a2 2 0 0 1 2.8 0l5 5a2 2 0 0 1 0 2.8L13 19"/><path d="M6.5 12.5l6 6"/>'),
    laser: svg('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>'),
    undo: svg('<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>'),
    redo: svg('<path d="M15 14l5-5-5-5"/><path d="M20 9H9a5 5 0 0 0 0 10h3"/>'),
    trash: svg('<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>'),
    more: svg('<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>'),
    x: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
    check: svg('<path d="M5 12l5 5L20 7"/>'),
    grid: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>'),
    plus: svg('<path d="M12 5v14M5 12h14"/>'),
    copy: svg('<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>'),
    image: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>'),
    download: svg('<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>'),
    upload: svg('<path d="M12 15V3M7 8l5-5 5 5M4 21h16"/>'),
    keyboard: svg('<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>'),
    zoomIn: svg('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M11 8v6M8 11h6"/>'),
    zoomOut: svg('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3M8 11h6"/>'),
    maximize: svg('<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"/>'),
    fit: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12h8M12 8v8"/>'),
    layout: svg('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>'),
    calendar: svg('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
    filter: svg('<path d="M3 5h18l-7 8v6l-4 2v-8z"/>'),
    chevUp: svg('<path d="M6 15l6-6 6 6"/>'),
    chevDown: svg('<path d="M6 9l6 6 6-6"/>'),
    fill: svg('<path d="M19 11l-8-8-8 8 8 8z"/><path d="M21 17c0 1.5-1 3-2 3s-2-1.5-2-3 2-4 2-4 2 2.5 2 4z"/>'),
    file: svg('<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>'),
  };
  const ic = n => {
    try { if (typeof window.icon === 'function') { const r = window.icon(n); if (typeof r === 'string' && r.indexOf('<svg') >= 0) return r; } } catch (e) { }
    return ICONS[n] || '';
  };
  const TOOL_GROUPS = [
    [['move', 'cursor', 'Выделение и перемещение (V)'], ['hand', 'hand', 'Рука — двигать холст (или удерживайте пробел / правую кнопку мыши)']],
    [['pen', 'pen', 'Перо (P)'], ['highlighter', 'highlighter', 'Маркер (H)'], ['eraser', 'eraser', 'Ластик (E) · размер — [ и ]']],
    [['line', 'line', 'Линия (L)'], ['arrow', 'arrow', 'Стрелка (A)'], ['darrow', 'darrow', 'Двойная стрелка (B)'], ['rect', 'square', 'Прямоугольник (R)'], ['ellipse', 'circle', 'Эллипс (O)'], ['triangle', 'triangle', 'Треугольник (G)'], ['diamond', 'diamond', 'Ромб (D)']],
    [['text', 'type', 'Текст (T)'], ['note', 'note', 'Стикер (N)'], ['stamp', 'smile', 'Штамп-эмодзи (M)'], ['chart', 'chart', 'Диаграмма (C)'], ['laser', 'laser', 'Лазерная указка (K)']],
  ];
  const TOOL_NAMES = {};
  TOOL_GROUPS.forEach(g => g.forEach(t => { TOOL_NAMES[t[0]] = t[2].replace(/\s*\(.*$/, '').replace(/ —.*$/, ''); }));
  const HINTS = {
    move: 'Клик — выбрать · растяните рамку — выделить несколько · Shift+клик — добавить · за уголки — размер · двойной клик по тексту — править · Delete — удалить',
    hand: 'Тяните холст. Ещё: правая/средняя кнопка мыши, пробел+мышь, колесо; Ctrl+колесо — масштаб',
    pen: 'Рисуйте. Shift — прямая линия · Ctrl+Z — отмена · правая кнопка — двигать холст',
    highlighter: 'Полупрозрачный маркер. Shift — прямая линия',
    eraser: 'Проведите по линии — сотрётся только задетая часть. «Объект» — убирает фигуру целиком. [ и ] — размер',
    line: 'Растяните линию. Shift — ровно по 45°',
    arrow: 'Растяните стрелку. Shift — ровно по 45°',
    darrow: 'Растяните двойную стрелку. Shift — ровно по 45°',
    rect: 'Растяните фигуру. Shift — квадрат · «Заливка» — залить цветом',
    ellipse: 'Растяните фигуру. Shift — круг · «Заливка» — залить цветом',
    triangle: 'Растяните фигуру. Shift — равные стороны',
    diamond: 'Растяните фигуру. Shift — равные стороны',
    text: 'Клик — поставить текст. Enter — готово, Shift+Enter — новая строка. Размер текста — кнопки толщины',
    note: 'Клик — стикер. Цвет — на панели выше. Двойной клик по стикеру — править',
    stamp: 'Клик — поставить эмодзи. Выбор — на панели выше',
    chart: 'Растяните область — откроется редактор данных. Двойной клик по диаграмме — изменить',
    laser: 'Указка видна участникам. Ничего не рисует',
  };
  const CSS = `
.wb.wb-v2{display:flex;flex-direction:column;height:100%;min-height:0;background:#fbfbfe;color:#0f172a;font:14px/1.3 ${FONT};position:relative;box-sizing:border-box}
.wb-v2 *,.wb-v2 *::before,.wb-v2 *::after{box-sizing:border-box}
.wb-v2 .wb-top{display:flex;align-items:center;gap:10px;padding:6px 10px;background:#fff;border-bottom:1px solid #e2e8f0;flex-wrap:wrap;position:relative;z-index:6}
.wb-v2 .wb-top.collapsed .wb-tools,.wb-v2 .wb-top.collapsed+.wb-sub{display:none}
.wb-v2 .wb-title{display:flex;align-items:center;gap:6px;font-weight:800;min-width:0}
.wb-v2 .wb-title svg{width:18px;height:18px;color:#6d28d9;flex:none}
.wb-v2 .wb-title input{border:none;background:transparent;font:inherit;font-weight:800;color:inherit;width:170px;outline:none;border-bottom:1px dashed transparent;padding:2px 0}
.wb-v2 .wb-title input:focus{border-bottom-color:#6d28d9}
.wb-v2 .wb-tools{display:flex;align-items:center;gap:4px;flex-wrap:wrap;flex:1}
.wb-v2 .wb-group{display:flex;gap:2px;padding:2px;border-radius:10px;background:#f1f5f9}
.wb-v2 .wb-tool{width:34px;height:34px;border-radius:8px;border:none;background:transparent;color:#334155;display:grid;place-items:center;cursor:pointer;padding:0;position:relative;font:inherit}
.wb-v2 .wb-tool svg{width:18px;height:18px}
.wb-v2 .wb-tool:hover{background:#e2e8f0}
.wb-v2 .wb-tool.active{background:#6d28d9;color:#fff;box-shadow:0 2px 8px rgba(109,40,217,.35)}
.wb-v2 .wb-tool:disabled{opacity:.35;cursor:default;background:transparent}
.wb-v2 .wb-sep{width:1px;height:24px;background:#e2e8f0;margin:0 4px;flex:none}
.wb-v2 .wb-colors,.wb-v2 .wb-sizes{display:flex;gap:4px;align-items:center}
.wb-v2 .wb-color{width:22px;height:22px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #cbd5e1;cursor:pointer;padding:0;position:relative;overflow:hidden;flex:none}
.wb-v2 .wb-color.active{box-shadow:0 0 0 2px #6d28d9;transform:scale(1.15)}
.wb-v2 .wb-color input{opacity:0;position:absolute;inset:0;width:100%;height:100%;cursor:pointer}
.wb-v2 .wb-size{width:28px;height:28px;border-radius:8px;border:none;background:transparent;display:grid;place-items:center;cursor:pointer;color:#334155;padding:0}
.wb-v2 .wb-size i{display:block;border-radius:50%;background:currentColor}
.wb-v2 .wb-size.active{background:#ede9fe;color:#6d28d9}
.wb-v2 .wb-sub{display:none;align-items:center;gap:12px;padding:5px 12px;background:#f8fafc;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;flex-wrap:wrap;position:relative;z-index:5;min-height:36px}
.wb-v2 .wb-sub.show{display:flex}
.wb-v2 .wb-sub>span{display:inline-flex;align-items:center;gap:10px}
.wb-v2 .wb-sub label{display:inline-flex;align-items:center;gap:6px;font-weight:600}
.wb-v2 .wb-sub input[type=range]{width:150px;accent-color:#6d28d9}
.wb-v2 .wb-eraser-val{min-width:44px;font-weight:800;color:#0f172a}
.wb-v2 .wb-eraser-preview{display:inline-block;border-radius:50%;border:2px solid #6d28d9;background:rgba(109,40,217,.15);flex:none}
.wb-v2 .wb-seg{display:inline-flex;border:1px solid #cbd5e1;border-radius:8px;overflow:hidden;background:#fff}
.wb-v2 .wb-seg button{border:none;background:#fff;padding:4px 10px;font:inherit;font-weight:600;cursor:pointer;color:#334155}
.wb-v2 .wb-seg button.active{background:#6d28d9;color:#fff}
.wb-v2 .wb-palette{display:none;gap:5px;align-items:center}
.wb-v2 .wb-palette.show{display:inline-flex}
.wb-v2 .wb-palette button{width:26px;height:26px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #cbd5e1;cursor:pointer;padding:0;font-size:16px;line-height:1;background:#fff}
.wb-v2 .wb-palette button.active{box-shadow:0 0 0 2px #6d28d9;transform:scale(1.12)}
.wb-v2 .wb-stamp-palette button{border-radius:8px;width:30px;height:30px}
.wb-v2 .wb-sub-note{color:#64748b}
.wb-v2 .wb-canvas-wrap{flex:1;position:relative;overflow:hidden;min-height:0;background:#fff;touch-action:none;user-select:none;-webkit-user-select:none}
.wb-v2 .wb-canvas-wrap canvas{position:absolute;inset:0;width:100%;height:100%;display:block}
.wb-v2 .wb-canvas-wrap.dots{background-color:#fff;background-image:radial-gradient(#cbd5e1 1px,transparent 1.5px);background-size:24px 24px}
.wb-v2 .wb-canvas-wrap.grid{background-color:#fff;background-image:linear-gradient(#e2e8f0 1px,transparent 1px),linear-gradient(90deg,#e2e8f0 1px,transparent 1px);background-size:24px 24px}
.wb-v2 .wb-canvas-wrap.lined{background-color:#fff;background-image:linear-gradient(#dbeafe 1px,transparent 1px);background-size:100% 32px}
.wb-v2 .wb-canvas-wrap.plain{background:#fff}
.wb-v2 .wb-canvas-wrap.clear{background:transparent}
.wb-v2 .wb-canvas-wrap.tool-pen,.wb-v2 .wb-canvas-wrap.tool-highlighter,.wb-v2 .wb-canvas-wrap.tool-line,.wb-v2 .wb-canvas-wrap.tool-arrow,.wb-v2 .wb-canvas-wrap.tool-darrow,.wb-v2 .wb-canvas-wrap.tool-rect,.wb-v2 .wb-canvas-wrap.tool-ellipse,.wb-v2 .wb-canvas-wrap.tool-triangle,.wb-v2 .wb-canvas-wrap.tool-diamond,.wb-v2 .wb-canvas-wrap.tool-chart{cursor:crosshair}
.wb-v2 .wb-canvas-wrap.tool-move{cursor:default}
.wb-v2 .wb-canvas-wrap.tool-hand,.wb-v2 .wb-canvas-wrap.space-pan{cursor:grab}
.wb-v2 .wb-canvas-wrap.tool-text,.wb-v2 .wb-canvas-wrap.tool-note{cursor:text}
.wb-v2 .wb-canvas-wrap.tool-stamp{cursor:copy}
.wb-v2 .wb-canvas-wrap.tool-eraser,.wb-v2 .wb-canvas-wrap.tool-laser{cursor:none}
.wb-v2 .wb-canvas-wrap.panning{cursor:grabbing!important}
.wb-v2 .wb-eraser-cursor{position:absolute;border:2px solid #6d28d9;border-radius:50%;background:rgba(109,40,217,.14);pointer-events:none;transform:translate(-50%,-50%);display:none;z-index:4;box-shadow:0 0 0 1px rgba(255,255,255,.95),0 2px 8px rgba(15,23,42,.25)}
.wb-v2 .wb-eraser-cursor.show{display:block}
.wb-v2 .wb-eraser-cursor.down{background:rgba(239,68,68,.25);border-color:#ef4444}
.wb-v2 .wb-eraser-cursor::after{content:'';position:absolute;left:50%;top:50%;width:4px;height:4px;margin:-2px 0 0 -2px;border-radius:50%;background:#6d28d9}
.wb-v2 .wb-eraser-cursor.down::after{background:#ef4444}
.wb-v2 .wb-laser-dot{position:absolute;width:14px;height:14px;border-radius:50%;background:#ef4444;box-shadow:0 0 0 4px rgba(239,68,68,.3),0 0 18px #ef4444;transform:translate(-50%,-50%);pointer-events:none;z-index:4}
.wb-v2 .wb-textbox{position:absolute;min-width:60px;font:600 18px ${FONT};color:#0f172a;background:rgba(255,255,255,.92);border:1px dashed #6d28d9;border-radius:6px;outline:none;z-index:5;white-space:pre-wrap;word-break:break-word;line-height:1.3}
.wb-v2 .wb-textbox:empty::before{content:attr(data-placeholder);color:#94a3b8}
.wb-v2 .wb-cursors{position:absolute;inset:0;pointer-events:none;z-index:3;overflow:hidden}
.wb-v2 .wb-cursor{position:absolute;transition:left .1s,top .1s,opacity .4s;display:flex;align-items:flex-start;gap:2px}
.wb-v2 .wb-cursor svg{width:18px;height:18px}
.wb-v2 .wb-cursor span{font-size:11px;font-weight:700;color:#fff;padding:2px 6px;border-radius:6px;margin-top:14px;white-space:nowrap}
.wb-v2 .wb-bottom{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:5px 12px;background:#fff;border-top:1px solid #e2e8f0;font-size:13px;color:#475569;flex-wrap:wrap;position:relative;z-index:5}
.wb-v2 .wb-pages{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
.wb-v2 .wb-pages button{border:1px solid #e2e8f0;background:#fff;border-radius:8px;padding:4px 10px;font:inherit;font-weight:600;cursor:pointer;color:#334155;display:inline-flex;align-items:center;gap:4px}
.wb-v2 .wb-pages button.active{background:#6d28d9;color:#fff;border-color:#6d28d9}
.wb-v2 .wb-pages button svg{width:14px;height:14px}
.wb-v2 .wb-status{flex:1;min-width:120px;text-align:center;color:#64748b;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.wb-v2 .wb-status b{color:#0f172a}
.wb-v2 .wb-collab{display:flex;align-items:center;gap:4px;font-size:12px;color:#64748b;white-space:nowrap}
.wb-v2 .wb-collab .avatar{width:22px;height:22px;border-radius:50%;display:inline-grid;place-items:center;color:#fff;font-size:10px;font-weight:800;margin-left:-4px;border:2px solid #fff}
.wb-v2 .wb-zoom{display:flex;align-items:center;gap:4px}
.wb-v2 .wb-zoom button{border:none;background:#f1f5f9;border-radius:6px;width:28px;height:28px;display:grid;place-items:center;cursor:pointer;color:#334155;padding:0}
.wb-v2 .wb-zoom button:hover{background:#e2e8f0}
.wb-v2 .wb-zoom button svg{width:16px;height:16px}
.wb-v2 .wb-zoom-val{min-width:46px;text-align:center;font-weight:700;cursor:pointer}
.wb-v2 .wb-menu{position:absolute;right:10px;top:calc(100% + 4px);width:320px;max-height:min(72vh,600px);overflow:auto;background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 20px 48px rgba(15,23,42,.22);padding:8px;z-index:40;display:flex;flex-direction:column;gap:2px;color:#0f172a;text-align:left}
.wb-v2 .wb-menu h5{margin:6px 8px 2px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#64748b;font-weight:800}
.wb-v2 .wb-menu button,.wb-v2 .wb-menu label{display:flex;align-items:center;gap:8px;border:none;background:transparent;text-align:left;padding:7px 10px;border-radius:8px;font:inherit;font-weight:600;cursor:pointer;color:inherit;width:100%}
.wb-v2 .wb-menu button:hover,.wb-v2 .wb-menu label:hover{background:#f1f5f9}
.wb-v2 .wb-menu button:disabled{opacity:.4;cursor:default}
.wb-v2 .wb-menu svg{width:16px;height:16px;color:#6d28d9;flex:none}
.wb-v2 .wb-menu .wb-check{margin-left:auto;color:#16a34a}
.wb-v2 .wb-menu hr{border:none;border-top:1px solid #e2e8f0;margin:4px 0;width:100%}
.wb-v2 .sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.wb-v2 .wb-chart-editor,.wb-v2 .wb-modal{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:60;width:min(440px,92%);background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 20px 48px rgba(15,23,42,.3);padding:16px;display:flex;flex-direction:column;gap:10px;color:#0f172a;max-height:88%;overflow:auto}
.wb-v2 .wb-chart-editor h5,.wb-v2 .wb-modal h5{font-size:15px;font-weight:900;display:flex;gap:8px;align-items:center;margin:0}
.wb-v2 .wb-chart-editor h5 svg,.wb-v2 .wb-modal h5 svg{width:17px;height:17px;color:#6d28d9}
.wb-v2 .wb-chart-editor textarea,.wb-v2 .wb-chart-editor input,.wb-v2 .wb-chart-editor select{font:inherit;border:1px solid #cbd5e1;border-radius:8px;padding:7px 9px;width:100%;background:#fff;color:inherit}
.wb-v2 .wb-chart-row{display:flex;gap:8px}
.wb-v2 .wb-chart-actions,.wb-v2 .wb-modal-actions{display:flex;justify-content:flex-end;gap:8px}
.wb-v2 .wb-chart-actions button,.wb-v2 .wb-modal-actions button{border:none;border-radius:8px;padding:8px 14px;font:inherit;font-weight:700;cursor:pointer;background:#f1f5f9;color:#334155}
.wb-v2 .wb-chart-actions .wb-chart-save,.wb-v2 .wb-modal-actions .primary{background:#6d28d9;color:#fff}
.wb-v2 .wb-modal ul{list-style:none;margin:0;padding:0;display:grid;gap:4px;font-size:13px}
.wb-v2 .wb-modal li{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px solid #f1f5f9}
.wb-v2 .wb-modal kbd{font-family:inherit;font-weight:800;background:#f1f5f9;padding:1px 8px;border-radius:6px;white-space:nowrap}
.wb-v2 .wb-backdrop{position:absolute;inset:0;z-index:55;background:rgba(15,23,42,.25)}
.wb-v2 .wb-toast{position:absolute;left:50%;bottom:54px;transform:translateX(-50%);background:#0f172a;color:#fff;padding:9px 14px;border-radius:10px;font-weight:600;font-size:13px;z-index:70;max-width:92%;pointer-events:none;opacity:0;transition:opacity .2s;text-align:center}
.wb-v2 .wb-toast.show{opacity:1}
.wb-v2 .wb-toast.bad{background:#b91c1c}
.wb-v2 .wb-dropzone{position:absolute;inset:8px;border:3px dashed #6d28d9;border-radius:14px;background:rgba(109,40,217,.08);display:none;place-items:center;font-weight:800;color:#6d28d9;z-index:8;pointer-events:none}
.wb-v2.dragover .wb-dropzone{display:grid}
.wb-v2 .small{font-size:12px}
@media (max-width:720px){.wb-v2 .wb-tool{width:30px;height:30px}.wb-v2 .wb-title input{width:110px}.wb-v2 .wb-status{display:none}}
`;
  function injectCss() {
    if (document.getElementById('wb-v2-css')) return;
    const pre = document.getElementById('fm') ? '#fm ' : '';
    const st = document.createElement('style'); st.id = 'wb-v2-css';
    st.textContent = pre ? CSS.replace(/(^|\n|\{)(\.wb)/g, '$1' + pre + '$2') : CSS;
    document.head.appendChild(st);
  }
  window.__WB = { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss };
  const PARTS = ["wb/whiteboard.part1.js", "wb/whiteboard.part2.js", "wb/whiteboard.part3.js", "wb/whiteboard.part4.js", "wb/whiteboard.part5.js", "wb/whiteboard.part6.js", "wb/whiteboard.part7.js"];
  const cs = document.currentScript;
  const base = cs && cs.src ? cs.src.replace(/[^/]*$/, '') : '';
  const ver = '?v=2.0.1';
  if (document.readyState === 'loading' && cs && !cs.async && !cs.defer) {
    PARTS.forEach(p => document.write('<script src="' + base + p + ver + '"><\\/script>'));
  } else {
    (function next(i) { if (i >= PARTS.length) return; const s = document.createElement('script'); s.src = base + PARTS[i] + ver; s.onload = () => next(i + 1); document.head.appendChild(s); })(0);
  }
})();
