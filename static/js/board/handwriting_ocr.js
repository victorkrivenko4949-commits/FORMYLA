/**
 * FORMYLA — On-demand selective OCR for the whiteboard pencil.
 *
 * UX:
 *   1. User scribbles whatever they want with the pen tool.
 *   2. When they want a fragment converted to beautiful Caveat
 *      handwriting, they press the  button (or hit Shift+H).
 *   3. The cursor turns into a crosshair, a hint pill appears in
 *      the bottom-center: «Обведи прямоугольником то, что нужно
 *      распознать. Esc — отмена.»
 *   4. User drags a rectangle over the strokes they want — a dashed
 *      purple selection box follows the cursor.
 *   5. On mouseup we collect every pen-stroke object whose own bbox
 *      INTERSECTS the selection rectangle, rasterise just those into
 *      an offscreen PNG (NOT the original whole canvas), and POST it
 *      to `/api/handwriting/recognize`.
 *   6. Backend returns `{text: "...", font: "Caveat"}` from Claude
 *      Opus 4.7. We atomically replace the selected pen strokes with
 *      one handwriting object at the selection bbox.
 *   7. Esc cancels the selection at any time without touching the
 *      board.
 *
 * Public API on `window.FormylaHWOcr`:
 *   startSelection()  — enter lasso mode (same as the button click)
 *   cancelSelection() — leave lasso mode without doing anything
 */
(function (root) {
  "use strict";

  // ── Tunables ─────────────────────────────────────────────────────────
  var PAD_PX = 14;               // padding around bbox for OCR canvas
  var SUPERSAMPLE = 2;           // 2× pixel density -> crisper glyphs
  var MIN_RECT = 12;             // ignore micro selections (accidental click)
  var ENDPOINT = "/api/handwriting/recognize";

  // ── State ────────────────────────────────────────────────────────────
  var inflight = false;          // OCR request in progress
  var lasso = null;              // { overlay, hint, rect, startX, startY, isDown }

  // ── Stroke helpers ───────────────────────────────────────────────────
  function _bboxOfPoints(points) {
    if (!points || !points.length) return null;
    var x0 = points[0].x, y0 = points[0].y, x1 = x0, y1 = y0;
    for (var i = 1; i < points.length; i++) {
      var p = points[i];
      if (p.x < x0) x0 = p.x; else if (p.x > x1) x1 = p.x;
      if (p.y < y0) y0 = p.y; else if (p.y > y1) y1 = p.y;
    }
    return { x0: x0, y0: y0, x1: x1, y1: y1 };
  }

  function _bboxIntersects(a, b) {
    return !(a.x1 < b.x0 || a.x0 > b.x1 || a.y1 < b.y0 || a.y0 > b.y1);
  }

  function _collectPenObjectsInside(worldRect) {
    // Snapshot every pen-stroke whose bbox intersects the world-rect
    // chosen by the user. Pure intersection (not "fully contained")
    // matches user intuition — a stroke clipped by the rect edge is
    // probably part of what they meant.
    if (!window.WB || typeof WB.getObjects !== "function") return [];
    var objects = WB.getObjects();
    var out = [];
    for (var i = 0; i < objects.length; i++) {
      var o = objects[i];
      if (!o || o.kind !== "pen" || !o.points || !o.points.length) continue;
      var bb = _bboxOfPoints(o.points);
      if (!bb) continue;
      if (!_bboxIntersects(bb, worldRect)) continue;
      out.push({
        id: o.id, points: o.points, color: o.color,
        thickness: o.thickness, bbox: bb,
      });
    }
    return out;
  }

  function _unionBbox(items) {
    if (!items.length) return null;
    var b = Object.assign({}, items[0].bbox);
    for (var i = 1; i < items.length; i++) {
      var it = items[i].bbox; if (!it) continue;
      if (it.x0 < b.x0) b.x0 = it.x0;
      if (it.y0 < b.y0) b.y0 = it.y0;
      if (it.x1 > b.x1) b.x1 = it.x1;
      if (it.y1 > b.y1) b.y1 = it.y1;
    }
    return b;
  }

  function _renderToPng(items, bbox) {
    var pad = PAD_PX;
    var w = Math.max(1, Math.ceil(bbox.x1 - bbox.x0 + pad * 2));
    var h = Math.max(1, Math.ceil(bbox.y1 - bbox.y0 + pad * 2));
    var cv = document.createElement("canvas");
    cv.width  = w * SUPERSAMPLE;
    cv.height = h * SUPERSAMPLE;
    var c = cv.getContext("2d");
    c.fillStyle = "#ffffff";
    c.fillRect(0, 0, cv.width, cv.height);
    c.scale(SUPERSAMPLE, SUPERSAMPLE);
    c.translate(pad - bbox.x0, pad - bbox.y0);
    c.lineCap = "round";
    c.lineJoin = "round";
    c.strokeStyle = "#0a0a0a";    // OCR likes high-contrast B&W
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var pts = it.points || [];
      if (pts.length < 1) continue;
      c.lineWidth = Math.max(2, (it.thickness || 2) * 1.2);
      c.beginPath();
      c.moveTo(pts[0].x, pts[0].y);
      for (var j = 1; j < pts.length; j++) c.lineTo(pts[j].x, pts[j].y);
      if (pts.length === 1) c.lineTo(pts[0].x + 0.5, pts[0].y + 0.5);
      c.stroke();
    }
    return cv.toDataURL("image/png");
  }

  // ── OCR pipeline (only run on the selected items) ───────────────────
  function _runOcr(items, selectionBbox) {
    if (items.length === 0) {
      _toast("В выделении нет рукописных штрихов.");
      return;
    }
    var bboxItems = _unionBbox(items);
    if (!bboxItems) return;
    inflight = true;
    _setBtnBusy(true);
    _showSpinner(true);

    var png;
    try { png = _renderToPng(items, bboxItems); }
    catch (e) {
      console.warn("[hwocr] raster failed:", e);
      inflight = false; _setBtnBusy(false); _showSpinner(false);
      _toast("Не удалось подготовить картинку.");
      return;
    }

    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: png }),
    })
      .then(function (r) { return r.json().then(function (j) { return { http: r.status, body: j }; }); })
      .then(function (pkg) {
        var j = pkg.body || {};
        if (pkg.http !== 200 || !j.ok) {
          console.warn("[hwocr] OCR failed:", j && j.error);
          _toast("Не получилось распознать: " + ((j && j.error) || "ошибка"));
          return;
        }
        var text = (j.text || "").trim();
        if (!text) {
          _toast("Модель не разобрала текст. Попробуй написать крупнее и чётче.");
          return;
        }
        if (!window.WB || typeof WB.replacePenStrokesWithHandwriting !== "function") {
          _toast("Внутренняя ошибка: WB API недоступен.");
          return;
        }
        var penIds = items.map(function (it) { return it.id; });
        var rawH = bboxItems.y1 - bboxItems.y0;
        var hwSize = Math.max(22, Math.min(80, Math.round(rawH * 0.85)));
        var hwColor = items[0].color || "#e6e8ff";
        WB.replacePenStrokesWithHandwriting(penIds, {
          text: text,
          x: bboxItems.x0 - 4,
          y: bboxItems.y0 - 4,
          size: hwSize,
          color: hwColor,
          font: j.font || "Caveat",
          maxWidth: Math.max(160, (bboxItems.x1 - bboxItems.x0) + 80),
        });
        _toast(" Готово: «" + text.slice(0, 70) + (text.length > 70 ? "…»" : "»"), true);
      })
      .catch(function (e) {
        console.warn("[hwocr] fetch failed:", e);
        _toast("Сеть не отвечает.");
      })
      .finally(function () {
        inflight = false;
        _setBtnBusy(false);
        _showSpinner(false);
      });
  }

  // ── Lasso selection overlay ─────────────────────────────────────────
  function startSelection() {
    if (inflight) {
      _toast("Подожди, идёт распознавание предыдущего фрагмента…");
      return;
    }
    if (lasso) return;       // already in selection mode
    if (!window.WB || typeof WB.getCanvasEl !== "function" || typeof WB.screenToWorld !== "function") {
      _toast("Доска ещё не готова. Попробуй через секунду.");
      return;
    }
    var canvasEl = WB.getCanvasEl();
    if (!canvasEl) return;
    var wrap = canvasEl.parentElement || document.body;

    // Full-coverage overlay above the canvas. pointer-events:auto so we
    // intercept the drag without disturbing the whiteboard.
    var overlay = document.createElement("div");
    overlay.className = "hwocr-lasso-overlay";
    wrap.appendChild(overlay);

    // The dashed selection rectangle that follows the cursor.
    var rect = document.createElement("div");
    rect.className = "hwocr-lasso-rect";
    rect.style.display = "none";
    overlay.appendChild(rect);

    // Bottom-center hint pill.
    var hint = document.createElement("div");
    hint.className = "hwocr-hint";
    hint.innerHTML = " Обведи рамкой то, что нужно распознать. <b>Esc</b> — отмена.";
    document.body.appendChild(hint);

    lasso = {
      overlay: overlay, rect: rect, hint: hint,
      isDown: false, startSX: 0, startSY: 0,
      lastSX: 0, lastSY: 0,
    };

    // Mouse / touch handlers — work in screen coords RELATIVE to overlay.
    function _local(ev) {
      var r = overlay.getBoundingClientRect();
      var t = (ev.touches && ev.touches[0]) || ev;
      return { x: t.clientX - r.left, y: t.clientY - r.top };
    }

    function _onDown(ev) {
      ev.preventDefault();
      var p = _local(ev);
      lasso.isDown = true;
      lasso.startSX = p.x; lasso.startSY = p.y;
      lasso.lastSX = p.x;  lasso.lastSY = p.y;
      rect.style.display = "block";
      rect.style.left   = p.x + "px";
      rect.style.top    = p.y + "px";
      rect.style.width  = "0px";
      rect.style.height = "0px";
    }

    function _onMove(ev) {
      if (!lasso.isDown) return;
      var p = _local(ev);
      lasso.lastSX = p.x; lasso.lastSY = p.y;
      var x = Math.min(lasso.startSX, p.x);
      var y = Math.min(lasso.startSY, p.y);
      var w = Math.abs(p.x - lasso.startSX);
      var h = Math.abs(p.y - lasso.startSY);
      rect.style.left   = x + "px";
      rect.style.top    = y + "px";
      rect.style.width  = w + "px";
      rect.style.height = h + "px";
    }

    function _onUp(ev) {
      if (!lasso.isDown) return;
      lasso.isDown = false;
      var w = Math.abs(lasso.lastSX - lasso.startSX);
      var h = Math.abs(lasso.lastSY - lasso.startSY);
      if (w < MIN_RECT && h < MIN_RECT) {
        _toast("Слишком маленькая рамка. Обведи область побольше.");
        return;
      }
      // Convert SCREEN coordinates (relative to overlay = relative to canvas)
      // to WORLD via WB.screenToWorld(sx, sy).
      var sx0 = Math.min(lasso.startSX, lasso.lastSX);
      var sy0 = Math.min(lasso.startSY, lasso.lastSY);
      var sx1 = Math.max(lasso.startSX, lasso.lastSX);
      var sy1 = Math.max(lasso.startSY, lasso.lastSY);
      var w0 = WB.screenToWorld(sx0, sy0);
      var w1 = WB.screenToWorld(sx1, sy1);
      var worldRect = {
        x0: Math.min(w0.x, w1.x),
        y0: Math.min(w0.y, w1.y),
        x1: Math.max(w0.x, w1.x),
        y1: Math.max(w0.y, w1.y),
      };
      var items = _collectPenObjectsInside(worldRect);
      cancelSelection();              // tear down overlay first
      _runOcr(items, worldRect);
    }

    overlay.addEventListener("pointerdown", _onDown);
    overlay.addEventListener("pointermove", _onMove);
    overlay.addEventListener("pointerup",   _onUp);
    overlay.addEventListener("pointercancel", function () { cancelSelection(); });

    // Esc cancels.
    function _onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelSelection();
      }
    }
    document.addEventListener("keydown", _onKey);
    lasso._cleanup = function () {
      document.removeEventListener("keydown", _onKey);
    };
  }

  function cancelSelection() {
    if (!lasso) return;
    try { lasso._cleanup && lasso._cleanup(); } catch (_) {}
    try { lasso.overlay.remove(); } catch (_) {}
    try { lasso.hint.remove();    } catch (_) {}
    lasso = null;
  }

  // ── UI bits ──────────────────────────────────────────────────────────
  var _spin = null;
  function _showSpinner(on) {
    try {
      if (on) {
        if (!_spin) {
          _spin = document.createElement("div");
          _spin.className = "hwocr-spinner";
          _spin.innerHTML = "<span> Claude Opus распознаёт…</span>";
          document.body.appendChild(_spin);
        }
        _spin.style.display = "block";
      } else if (_spin) {
        _spin.style.display = "none";
      }
    } catch (_) {}
  }

  var _toastEl = null;
  var _toastTimer = null;
  function _toast(msg, good) {
    try {
      if (!_toastEl) {
        _toastEl = document.createElement("div");
        _toastEl.className = "hwocr-toast";
        document.body.appendChild(_toastEl);
      }
      _toastEl.textContent = msg;
      _toastEl.classList.toggle("hwocr-toast--good", !!good);
      _toastEl.style.display = "block";
      if (_toastTimer) clearTimeout(_toastTimer);
      _toastTimer = setTimeout(function () {
        if (_toastEl) _toastEl.style.display = "none";
      }, good ? 3000 : 4500);
    } catch (_) {}
  }

  function _setBtnBusy(busy) {
    var btn = document.getElementById("wbOcrRecognizeBtn");
    if (!btn) return;
    btn.classList.toggle("is-busy", !!busy);
    btn.disabled = !!busy;
  }

  function _findOrCreateButton() {
    var btn = document.getElementById("wbOcrRecognizeBtn");
    if (btn) return btn;
    var tb = document.getElementById("wbToolbar");
    if (!tb) return null;
    btn = document.createElement("button");
    btn.id = "wbOcrRecognizeBtn";
    btn.className = "icon-btn hwocr-btn";
    btn.type = "button";
    btn.title = "Распознать выделенную рукопись (Shift+H)";
    btn.innerHTML = "";
    var anchor = document.getElementById("wbHandwritingBtn");
    if (anchor && anchor.parentNode === tb) {
      tb.insertBefore(btn, anchor.nextSibling);
    } else {
      tb.appendChild(btn);
    }
    return btn;
  }

  function _bind() {
    var btn = _findOrCreateButton();
    if (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        startSelection();
      });
    }
    document.addEventListener("click", function (e) {
      var t = e.target;
      var hit = (t && (t.id === "wbOcrRecognizeBtn"
                     || (t.closest && t.closest("#wbOcrRecognizeBtn"))));
      if (!hit) return;
      e.preventDefault();
      e.stopPropagation();
      startSelection();
    }, true);
    document.addEventListener("keydown", function (e) {
      if (!e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
      var k = (e.key || "").toLowerCase();
      if (k !== "h" && k !== "р") return;
      var t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      e.preventDefault();
      startSelection();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _bind);
  } else {
    _bind();
  }

  root.FormylaHWOcr = {
    startSelection: startSelection,
    cancelSelection: cancelSelection,
    // Exposed for tests / debugging.
    _collectPenObjectsInside: _collectPenObjectsInside,
    _bboxIntersects: _bboxIntersects,
    _renderToPng: _renderToPng,
  };
  console.info("[FormylaHWOcr] loaded build 2026-05-24.2 (lasso-select, Claude Opus 4.7, no-LaTeX)");
})(typeof window !== "undefined" ? window : globalThis);
