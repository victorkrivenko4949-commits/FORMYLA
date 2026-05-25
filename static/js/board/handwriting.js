/* eslint-disable no-bitwise */
/**
 * FORMYLA — Handwriting Renderer.
 * Renders text onto a 2D canvas with natural-looking hand-written
 * variations (jitter, slight rotation, size wobble). Inspired by
 * Thalamus / Goodnotes "ink" text. Pure client-side (no API),
 * works with any Google handwriting font that is already loaded
 * into the page (e.g. "Caveat", "Marck Script", "Pangolin").
 *
 * Design goals:
 *   - Deterministic for a given `seed` → re-rendering an object
 *     after undo / reload produces the *same* picture.
 *   - Pure function: never mutates `ctx` state outside save/restore.
 *   - No external dependencies, works in any modern browser.
 *
 * Public API (registered on window):
 *   FormylaHandwriting.renderHandwriting(ctx, text, opts)
 *   FormylaHandwriting.measureHandwriting(text, opts)        → {w, h}
 *   FormylaHandwriting.makeSeed()
 *   FormylaHandwriting.AVAILABLE_FONTS                       → string[]
 */
(function (root) {
  "use strict";

  /* ── deterministic PRNG (mulberry32) ────────────────────────────
   * Allows a stable “handwriting fingerprint” per object.            */
  function mulberry32(seedInt) {
    let a = (seedInt >>> 0) || 1;
    return function () {
      a |= 0;
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function hashSeed(input) {
    /* tiny 32-bit hash so a string seed → uint32 */
    let h = 2166136261 >>> 0;
    const s = String(input == null ? "" : input);
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function makeSeed() {
    return (Math.random() * 0xFFFFFFFF) >>> 0;
  }

  /* Fonts must already be loaded via <link href="…fonts.googleapis…">
   * in templates/whiteboard.html. We just declare the *names* here so
   * the UI picker can list them; missing fonts gracefully fall back to
   * the browser's generic "cursive" family. */
  const AVAILABLE_FONTS = [
    { id: "Caveat",         label: "Caveat (универсал, RU/EN)" },
    { id: "Marck Script",   label: "Marck Script (каллиграф., RU/EN)" },
    { id: "Pangolin",       label: "Pangolin (крупный, RU/EN)" },
    { id: "Homemade Apple", label: "Homemade Apple (англ. only)" },
    { id: "Shadows Into Light", label: "Shadows Into Light (EN)" },
    { id: "Kalam",          label: "Kalam (печатный почерк, RU/EN)" },
  ];

  /* ── pixel-precise wrap that respects an explicit maxWidth ───────
   * Returns an array of lines (greedy word-wrap). */
  function wrapToLines(ctx, text, font, maxWidth) {
    ctx.save();
    ctx.font = font;
    const lines = [];
    const rawLines = String(text || "").split(/\r?\n/);
    for (const raw of rawLines) {
      if (!raw) { lines.push(""); continue; }
      // greedy wrap by spaces; if a single word overflows, hard-break.
      const words = raw.split(/(\s+)/);
      let cur = "";
      for (const piece of words) {
        const candidate = cur + piece;
        if (ctx.measureText(candidate).width <= maxWidth || !cur.trim()) {
          cur = candidate;
        } else {
          lines.push(cur.replace(/\s+$/, ""));
          cur = piece.replace(/^\s+/, "");
        }
      }
      if (cur) lines.push(cur);
    }
    ctx.restore();
    return lines;
  }

  /* ── main entry point ────────────────────────────────────────────
   * Returns the rendered bounding box  {x, y, w, h}  in canvas units.
   * The bbox is useful for the board state (hit-test, eraser, undo).
   */
  function renderHandwriting(ctx, text, opts) {
    opts = opts || {};
    const x          = Number(opts.x) || 0;
    const y          = Number(opts.y) || 0;
    const size       = Math.max(8, Number(opts.size) || 28);
    const fontFamily = String(opts.font || "Caveat");
    const color      = String(opts.color || "#1f2937");
    const jitter     = opts.jitter !== false; // default ON
    const maxWidth   = Number(opts.maxWidth) || 480;
    const seed       = opts.seed != null ? opts.seed : makeSeed();
    const rand       = mulberry32(typeof seed === "number" ? seed : hashSeed(seed));

    // Quick "no-op": empty text yields a zero box but always returns it.
    if (!text || !String(text).length) return { x, y, w: 0, h: size };

    const baseFont = size + 'px "' + fontFamily + '", "Caveat", cursive';
    const lines = wrapToLines(ctx, text, baseFont, maxWidth);
    const lineHeight = size * 1.35;

    // jitter ranges — gentle so the result still reads as text.
    const J_X = jitter ? 0.8  : 0;
    const J_Y = jitter ? 1.2  : 0;
    const J_R = jitter ? 0.04 : 0; // radians
    const J_S = jitter ? 0.06 : 0; // ±6% font size variation

    let widestLine = 0;
    let baseY = y + size; // first baseline is one em below the top

    ctx.save();
    ctx.fillStyle = color;
    ctx.textBaseline = "alphabetic";

    for (let li = 0; li < lines.length; li++) {
      const line = lines[li];
      // small per-line baseline wobble
      const lineY = baseY + (rand() - 0.5) * J_Y * 2.0;
      let cursorX = x;
      // measure each char one by one — this keeps spacing tight even with
      // per-character size variation.
      ctx.font = baseFont;
      for (let ci = 0; ci < line.length; ci++) {
        const ch = line[ci];
        const sizeI = size * (1 + (rand() - 0.5) * 2 * J_S);
        const charFont = sizeI + 'px "' + fontFamily + '", "Caveat", cursive';
        ctx.save();
        ctx.font = charFont;
        const w = ctx.measureText(ch).width;
        const jx = (rand() - 0.5) * 2 * J_X;
        const jy = (rand() - 0.5) * 2 * J_Y;
        const jr = (rand() - 0.5) * 2 * J_R;
        ctx.translate(cursorX + jx, lineY + jy);
        ctx.rotate(jr);
        ctx.fillText(ch, 0, 0);
        ctx.restore();
        // advance with small kerning variation so the line doesn't look
        // mechanically equal-spaced.
        cursorX += w * (0.985 + rand() * 0.04);
      }
      widestLine = Math.max(widestLine, cursorX - x);
      baseY += lineHeight;
    }

    ctx.restore();

    return {
      x: x,
      y: y,
      w: Math.max(widestLine, 1),
      h: Math.max(baseY - y - lineHeight * 0.2, size),
    };
  }

  /**
   * Measure a piece of handwriting without drawing it.
   * Uses an off-screen canvas so it can be called before placement.
   */
  function measureHandwriting(text, opts) {
    opts = opts || {};
    const tmp = document.createElement("canvas");
    tmp.width = 1; tmp.height = 1;
    const tctx = tmp.getContext("2d");
    return renderHandwriting(tctx, text, Object.assign({}, opts, {
      // draw at (0,0) into the throwaway canvas to get the bbox cheaply
      x: 0, y: 0,
    }));
  }

  root.FormylaHandwriting = {
    renderHandwriting: renderHandwriting,
    measureHandwriting: measureHandwriting,
    makeSeed: makeSeed,
    AVAILABLE_FONTS: AVAILABLE_FONTS,
  };
})(typeof window !== "undefined" ? window : globalThis);
