/**
 * FORMYLA — Handwriting Modal Controller.
 *
 * Wires the «️ Текст -> Рукопись» button in the whiteboard toolbar to
 * the modal defined in templates/whiteboard.html and the renderer from
 * static/js/board/handwriting.js. Behaviour:
 *
 *   1. Click toolbar btn #wbHandwritingBtn -> modal opens with sane defaults.
 *   2. As the user types / changes font / size / color / jitter, a live
 *      preview is rasterised into <canvas id="hwPreview">.
 *   3. «обработать через ИИ» check-box -> POST /api/handwriting/prepare
 *      with mode="ai_format" before rendering. If the backend can't reach
 *      OpenRouter, it silently returns the raw line-broken text, so the
 *      preview always works (graceful fallback).
 *   4. «Вставить на доску» -> calls window.WB.addHandwritingObject(...)
 *      so the new ink lands in the same stroke-stack as everything else
 *      and inherits undo/redo, eraser, export, collaboration.
 *
 * The module is fully self-contained: it does NOT touch whiteboard.js
 * state directly, only through the public window.WB API exposed there.
 */
(function () {
  "use strict";

  // Visible build-marker so we can confirm in the browser console that the
  // fresh JS reached the user (not a stale cached version).
  console.log("[handwriting_ui] loaded build 2026-05-23.3 — click ️ in left toolbar (or press H)");

  // ── ROBUST GLOBAL CLICK DELEGATION ────────────────────────────────────
  // We attach a *capturing* document-level click handler IMMEDIATELY (before
  // DOMContentLoaded, before whenReady polling, before anything else).
  // This guarantees that clicks on #wbHandwritingBtn open the modal even if:
  //   - bindEvents() hasn't run yet (race with FormylaHandwriting loading),
  //   - some other script stops propagation on a parent,
  //   - the button is re-rendered dynamically by future code.
  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!t) return;
    // .closest() also catches clicks on inner spans/emoji glyphs.
    var btn = (t.closest && t.closest("#wbHandwritingBtn")) ||
              (t.id === "wbHandwritingBtn" ? t : null);
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    console.log("[handwriting_ui] ️ button click captured -> opening modal");
    // openModal is defined below; call via lookup so this works even if
    // declarations haven't been hoisted in some exotic build pipeline.
    try { openModal(); }
    catch (err) { console.error("[handwriting_ui] openModal failed:", err); }
  }, true /* useCapture: fire BEFORE anything else */);

  /** @returns {HTMLElement|null} */
  function $(id) { return document.getElementById(id); }

  /** Wait until window.FormylaHandwriting and window.WB are both ready.
   *  Both modules attach themselves at script-tag eval time, but tag order
   *  in templates/whiteboard.html guarantees they're set by DOMContentLoaded;
   *  we still poll briefly to be safe (e.g. async preloads). */
  function whenReady(cb, tries) {
    tries = tries == null ? 40 : tries;
    if (window.FormylaHandwriting && window.WB && document.getElementById("hwModal")) {
      cb();
      return;
    }
    if (tries <= 0) {
      console.warn("[handwriting_ui] dependencies missing, modal disabled");
      return;
    }
    setTimeout(function () { whenReady(cb, tries - 1); }, 50);
  }

  /* ── State (per-modal session) ─────────────────────────────────────── */
  var st = {
    text: "Теорема Пифагора: $a^2 + b^2 = c^2$",
    font: "Caveat",
    size: 28,
    color: "#1f2937",
    jitter: true,
    ai: false,
    seed: null,            // set on first preview, reused on insert
    processedText: null,   // cached AI-reformatted text (null = use raw)
    aiInFlight: false,
  };

  /* ── Preview rasteriser ────────────────────────────────────────────── */
  function drawPreview() {
    var canvas = $("hwPreview");
    if (!canvas) return;
    var HW = window.FormylaHandwriting;
    if (!HW) return;
    var dpr = window.devicePixelRatio || 1;
    var cssW = canvas.clientWidth || 480;
    var cssH = canvas.clientHeight || 160;
    if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
    }
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
    // Soft paper background so dark ink reads well.
    ctx.fillStyle = "#fafaf5";
    ctx.fillRect(0, 0, cssW, cssH);
    // Faint baseline grid (notebook-style) — purely decorative.
    ctx.strokeStyle = "rgba(60,80,180,0.10)";
    ctx.lineWidth = 1;
    for (var gy = 28; gy < cssH; gy += Math.max(20, Math.round(st.size * 1.35))) {
      ctx.beginPath();
      ctx.moveTo(8, gy + 0.5);
      ctx.lineTo(cssW - 8, gy + 0.5);
      ctx.stroke();
    }

    if (st.seed == null) {
      st.seed = HW.makeSeed();
    }
    // Use processed (AI-formatted) text if available, otherwise raw.
    var textToRender = st.processedText != null ? st.processedText : st.text;
    HW.renderHandwriting(ctx, textToRender, {
      x: 12,
      y: 8,
      size: st.size,
      font: st.font,
      color: st.color,
      jitter: st.jitter,
      maxWidth: cssW - 24,
      seed: st.seed,
    });
  }

  /* ── AI re-format (calls Flask backend) ────────────────────────────── */
  function requestAiFormat() {
    if (st.aiInFlight) return;
    st.aiInFlight = true;
    var btn = $("hwInsertBtn");
    if (btn) { btn.disabled = true; btn.textContent = "⏳ ИИ форматирует…"; }
    fetch("/api/handwriting/prepare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: st.text, mode: "ai_format" }),
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.ok && data.processed_text) {
          st.processedText = data.processed_text;
        } else {
          st.processedText = null;
        }
        drawPreview();
      })
      .catch(function (e) {
        console.warn("[handwriting_ui] AI format failed:", e);
        st.processedText = null;
        drawPreview();
      })
      .finally(function () {
        st.aiInFlight = false;
        if (btn) { btn.disabled = false; btn.textContent = "Вставить на доску ->"; }
      });
  }

  /* ── DOM wiring ────────────────────────────────────────────────────── */
  function populateFontPicker() {
    var sel = $("hwFont");
    if (!sel || sel.dataset.populated === "1") return;
    var fonts = (window.FormylaHandwriting && window.FormylaHandwriting.AVAILABLE_FONTS) || [];
    sel.innerHTML = "";
    fonts.forEach(function (f) {
      var opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = f.label || f.id;
      // Inline style -> option preview in the dropdown (best-effort, browser-dep)
      opt.style.fontFamily = '"' + f.id + '", cursive';
      sel.appendChild(opt);
    });
    sel.value = st.font;
    sel.dataset.populated = "1";
  }

  function openModal() {
    var modal = $("hwModal");
    if (!modal) {
      console.warn("[handwriting_ui] #hwModal element missing in DOM — cannot open");
      return;
    }
    populateFontPicker();
    // Sync DOM with state.
    var ta = $("hwText");        if (ta) ta.value = st.text;
    var fs = $("hwFont");        if (fs) fs.value = st.font;
    var sz = $("hwSize");        if (sz) sz.value = st.size;
    var sl = $("hwSizeLabel");   if (sl) sl.textContent = String(st.size);
    var jt = $("hwJitter");      if (jt) jt.checked  = st.jitter;
    var ai = $("hwAi");          if (ai) ai.checked  = st.ai;
    document.querySelectorAll("#hwModal .hw-ink").forEach(function (b) {
      b.classList.toggle("hw-ink--active", b.dataset.ink === st.color);
    });
    modal.hidden = false;
    modal.classList.add("hw-modal--open");
    // Force a layout pass so the preview canvas knows its clientWidth.
    setTimeout(drawPreview, 30);
    if (ta) ta.focus();
  }

  function closeModal() {
    var modal = $("hwModal");
    if (!modal) return;
    modal.hidden = true;
    modal.classList.remove("hw-modal--open");
  }

  function bindEvents() {
    var btn = $("wbHandwritingBtn");
    if (btn) {
      // Highlight the button so users notice it next to the other tools.
      btn.classList.add("hw-toolbar-btn");
      btn.setAttribute("aria-label", "Текст -> Рукопись (горячая клавиша H)");
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openModal();
      });
      console.log("[handwriting_ui] toolbar button ️ wired up");
    } else {
      console.warn("[handwriting_ui] #wbHandwritingBtn not found in DOM");
    }

    // Keyboard shortcut "H" -> open modal (when not typing in an input/textarea).
    document.addEventListener("keydown", function (e) {
      if (e.defaultPrevented) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "h" || e.key === "H" || e.key === "Р" || e.key === "р") {
        // "Р" — Russian layout equivalent of "H".
        var modal = $("hwModal");
        if (modal && !modal.hidden) return;
        e.preventDefault();
        openModal();
      } else if (e.key === "Escape") {
        var m = $("hwModal");
        if (m && !m.hidden) closeModal();
      }
    });

    // Close handlers (backdrop /  / Cancel).
    document.querySelectorAll("#hwModal [data-hw-close]").forEach(function (el) {
      el.addEventListener("click", function (e) {
        e.preventDefault();
        closeModal();
      });
    });

    // Text input (debounced redraw; AI-mode re-fetch).
    var ta = $("hwText");
    var debounceTimer = null;
    if (ta) {
      ta.addEventListener("input", function () {
        st.text = ta.value;
        st.processedText = null; // invalidate AI cache
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
          if (st.ai) requestAiFormat(); else drawPreview();
        }, 220);
      });
    }

    // Font.
    var fs = $("hwFont");
    if (fs) fs.addEventListener("change", function () {
      st.font = fs.value || "Caveat";
      drawPreview();
    });

    // Size.
    var sz = $("hwSize");
    if (sz) sz.addEventListener("input", function () {
      st.size = Math.max(8, parseInt(sz.value, 10) || 28);
      var sl = $("hwSizeLabel"); if (sl) sl.textContent = String(st.size);
      drawPreview();
    });

    // Ink colour pills.
    document.querySelectorAll("#hwModal .hw-ink").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.preventDefault();
        st.color = b.dataset.ink || "#1f2937";
        document.querySelectorAll("#hwModal .hw-ink").forEach(function (x) {
          x.classList.toggle("hw-ink--active", x === b);
        });
        drawPreview();
      });
    });

    // Jitter check-box.
    var jt = $("hwJitter");
    if (jt) jt.addEventListener("change", function () {
      st.jitter = !!jt.checked;
      drawPreview();
    });

    // AI check-box.
    var ai = $("hwAi");
    if (ai) ai.addEventListener("change", function () {
      st.ai = !!ai.checked;
      if (st.ai) {
        requestAiFormat();
      } else {
        st.processedText = null;
        drawPreview();
      }
    });

    // Insert.
    var ins = $("hwInsertBtn");
    if (ins) ins.addEventListener("click", function (e) {
      e.preventDefault();
      if (!st.text || !st.text.trim()) {
        closeModal();
        return;
      }
      if (!window.WB || typeof window.WB.addHandwritingObject !== "function") {
        console.error("[handwriting_ui] window.WB.addHandwritingObject missing");
        return;
      }
      var textToInsert = st.processedText != null ? st.processedText : st.text;
      window.WB.addHandwritingObject({
        text: textToInsert,
        font: st.font,
        size: st.size,
        color: st.color,
        jitter: st.jitter,
        seed: st.seed != null ? st.seed : null,
        maxWidth: 560,
      });
      // Force-reset seed so the *next* insertion gets a fresh "fingerprint".
      st.seed = null;
      closeModal();
    });

    // Window resize -> redraw preview if visible.
    window.addEventListener("resize", function () {
      var modal = $("hwModal");
      if (modal && !modal.hidden) drawPreview();
    });
  }

  /* ── Boot ──────────────────────────────────────────────────────────── */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { whenReady(bindEvents); });
  } else {
    whenReady(bindEvents);
  }
})();
