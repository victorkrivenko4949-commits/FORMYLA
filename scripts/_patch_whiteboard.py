# -*- coding: utf-8 -*-
"""Patch static/js/whiteboard.js with keyboard shortcuts.
Encodes JS using @LB@ / @RB@ tokens for curly braces to avoid tooling issues."""
import os, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "static", "js", "whiteboard.js")

with open(TARGET, "r", encoding="utf-8") as f:
    src = f.read()

if "WB_SHORTCUTS_V1" in src:
    print("[skip] already patched")
    sys.exit(0)

# JS payload — curly braces written as @LB@ / @RB@, dollar signs as @DS@,
# backticks as @BT@. We rehydrate before splicing.
JS_RAW = r"""
  // ===== WB_SHORTCUTS_V1 =====
  var wbClipboard = null;

  function _wbClone(o) @LB@
    try @LB@ return JSON.parse(JSON.stringify(o)); @RB@ catch (_) @LB@ return null; @RB@
  @RB@

  function _wbOffset(o, dx, dy) @LB@
    if (!o || typeof o !== "object") return;
    var ks = ["x","y","x1","y1","x2","y2","cx","cy"];
    for (var i=0;i<ks.length;i++) @LB@
      var k = ks[i];
      if (typeof o[k] === "number") @LB@
        if (k === "y" || k === "y1" || k === "y2" || k === "cy") o[k] += dy;
        else o[k] += dx;
      @RB@
    @RB@
    if (Array.isArray(o.points)) @LB@
      for (var p=0;p<o.points.length;p++) @LB@
        var pt = o.points[p];
        if (pt && typeof pt.x === "number") pt.x += dx;
        if (pt && typeof pt.y === "number") pt.y += dy;
      @RB@
    @RB@
  @RB@

  function _wbGetSel() @LB@
    if (selectedId == null) return null;
    for (var i=0;i<state.objects.length;i++) @LB@
      if (state.objects[i].id === selectedId) return state.objects[i];
    @RB@
    return null;
  @RB@

  function _wbCopy() @LB@
    var o = _wbGetSel();
    if (!o) return false;
    wbClipboard = _wbClone(o);
    return true;
  @RB@

  function _wbPaste() @LB@
    if (!wbClipboard) return false;
    var clone = _wbClone(wbClipboard);
    if (!clone) return false;
    clone.id = uid();
    _wbOffset(clone, 20, 20);
    state.objects.push(clone);
    selectedId = clone.id;
    pushHistory(); redraw();
    return true;
  @RB@

  function _wbCut() @LB@
    var o = _wbGetSel();
    if (!o) return false;
    wbClipboard = _wbClone(o);
    state.objects = state.objects.filter(function(x)@LB@ return x.id !== selectedId; @RB@);
    selectedId = null;
    pushHistory(); redraw();
    return true;
  @RB@

  function _wbDuplicate() @LB@
    var o = _wbGetSel();
    if (!o) return false;
    var clone = _wbClone(o);
    clone.id = uid();
    _wbOffset(clone, 20, 20);
    state.objects.push(clone);
    selectedId = clone.id;
    pushHistory(); redraw();
    return true;
  @RB@

  function _wbSelectAll() @LB@
    // Single-select fallback: pick last (top-most) object
    if (!state.objects.length) return false;
    selectedId = state.objects[state.objects.length - 1].id;
    redraw();
    return true;
  @RB@

  function _wbNudge(dx, dy) @LB@
    var o = _wbGetSel();
    if (!o) return false;
    moveObj(o, dx, dy);
    pushHistory(); redraw();
    return true;
  @RB@

  function _wbDeselect() @LB@
    if (selectedId == null) return false;
    selectedId = null;
    redraw();
    return true;
  @RB@

  function _wbExport() @LB@
    var btn = document.getElementById("wbExport");
    if (btn) @LB@ btn.click(); return true; @RB@
    return false;
  @RB@

  window.addEventListener("keydown", function (e) @LB@
    if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
    var k = (e.key || "").toLowerCase();
    var ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && k === "c") @LB@ if (_wbCopy()) e.preventDefault(); return; @RB@
    if (ctrl && k === "x") @LB@ if (_wbCut()) e.preventDefault(); return; @RB@
    if (ctrl && k === "v") @LB@ if (_wbPaste()) e.preventDefault(); return; @RB@
    if (ctrl && k === "d") @LB@ if (_wbDuplicate()) e.preventDefault(); return; @RB@
    if (ctrl && k === "a") @LB@ if (_wbSelectAll()) e.preventDefault(); return; @RB@
    if (ctrl && k === "s") @LB@ if (_wbExport()) e.preventDefault(); return; @RB@
    if (k === "escape") @LB@ if (_wbDeselect()) e.preventDefault(); return; @RB@
    if (k === "arrowleft" || k === "arrowright" || k === "arrowup" || k === "arrowdown") @LB@
      var step = e.shiftKey ? 10 : 1;
      var dx = 0, dy = 0;
      if (k === "arrowleft") dx = -step;
      else if (k === "arrowright") dx = step;
      else if (k === "arrowup") dy = -step;
      else dy = step;
      if (_wbNudge(dx, dy)) e.preventDefault();
      return;
    @RB@
  @RB@);

  // Paste image from system clipboard onto the whiteboard.
  document.addEventListener("paste", function (e) @LB@
    if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
    if (!e.clipboardData || !e.clipboardData.items) return;
    var items = e.clipboardData.items;
    for (var i = 0; i < items.length; i++) @LB@
      var it = items[i];
      if (it && it.kind === "file" && it.type && it.type.indexOf("image/") === 0) @LB@
        var file = it.getAsFile();
        if (!file) continue;
        var reader = new FileReader();
        reader.onload = function (ev) @LB@
          var src = ev.target && ev.target.result;
          if (src && window.WB && typeof window.WB.importImage === "function") @LB@
            window.WB.importImage(src);
          @RB@
        @RB@;
        reader.readAsDataURL(file);
        e.preventDefault();
        return;
      @RB@
    @RB@
  @RB@);
  // ===== /WB_SHORTCUTS_V1 =====
"""

js = JS_RAW.replace("@LB@", "{").replace("@RB@", "}")

# Insert AFTER the existing keyup handler (line 513-515)
ANCHOR = (
    'window.addEventListener("keyup", function (e) {\n'
    '    if (e.code === "Space") { spaceDown = false; '
    'canvasEl.style.cursor = tool === "select" ? "default" : "crosshair"; }\n'
    '  });'
)

if ANCHOR not in src:
    # Try a slightly relaxed regex match
    m = re.search(
        r'window\.addEventListener\("keyup",\s*function\s*\(e\)\s*\{[^}]*spaceDown\s*=\s*false[^}]*\}\s*\)\s*;',
        src, re.DOTALL,
    )
    if not m:
        print("[ERROR] keyup anchor not found")
        sys.exit(1)
    insert_at = m.end()
else:
    insert_at = src.index(ANCHOR) + len(ANCHOR)

new_src = src[:insert_at] + "\n" + js + src[insert_at:]

with open(TARGET, "w", encoding="utf-8") as f:
    f.write(new_src)

print(f"[ok] patched whiteboard.js: +{len(js)} chars (total {len(new_src)} chars)")
