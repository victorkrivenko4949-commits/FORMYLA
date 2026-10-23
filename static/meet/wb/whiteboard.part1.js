/* FORMYLA доска v2 — часть модуля, подключается из whiteboard.js */
(function () {
  'use strict';
  const { COLORS, SIZES, NOTE_COLORS, STAMPS, PIE_COLORS, TEMPLATES, BGS, FONT, EMOJI_FONT, MIN_ZOOM, MAX_ZOOM, LINE_TYPES, clone, uid, esc, clamp, ic, TOOL_GROUPS, TOOL_NAMES, HINTS, injectCss } = window.__WB;

  class Whiteboard {
    constructor(root, opts = {}) {
      injectCss();
      this.sel = [];
      this.root = root;
      this.opts = opts;
      this.title = opts.title || 'Доска без названия';
      this.pages = [{ shapes: [], undo: [], redo: [] }];
      this.page = 0;
      this.tool = 'pen';
      this.color = COLORS[0];
      this.size = SIZES[1];
      this.fill = false;
      this.eraserSize = 18;
      this.eraserMode = 'stroke';
      this.eraserPos = null;
      this.noteColor = NOTE_COLORS[0];
      this.stamp = STAMPS[0];
      this.overlay = !!opts.overlay;
      this.bg = this.overlay ? 'clear' : (opts.bg || 'dots');
      this.zoom = 1; this.panX = 0; this.panY = 0;
      this.drawing = null; this.marquee = null; this.resizing = null; this.dragging = null; this.panning = null;
      this.editing = null;
      this.imgCache = new Map();
      this.lastMouse = null;
      this.pointers = new Map();
      this.pinch = null;
      this.spaceDown = false;
      this.collab = opts.collaborators || [];
      if (opts.storageKey) this.restoreLocal();
      this.build();
      this.bind();
      this.resize();
      this.setTool(this.tool);
      this.render();
    }

    get shapes() { return this.pages[this.page].shapes; }
    get selected() { return this.sel[0] || null; }
    set selected(s) { this.sel = s ? [s] : []; }

  }
  window.Whiteboard = Whiteboard;
  Whiteboard.VERSION = '2.0.1';
})();
