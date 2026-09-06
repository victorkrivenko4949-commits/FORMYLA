# -*- coding: utf-8 -*-
"""CH27: тёмная HTML-галерея (base/aux парами) из output/ch27/svg."""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "output", "ch27")
_SVG_DIR = os.path.join(_OUT, "svg")


def _safe(uid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", uid)


def main():
    meta = {}
    results_path = os.path.join(_OUT, "probe_results.json")
    if os.path.exists(results_path):
        for r in json.load(open(results_path, encoding="utf-8")):
            meta[r["uid"]] = r

    cards = []
    for fn in sorted(os.listdir(_SVG_DIR)):
        if not fn.endswith("_base.svg"):
            continue
        uid = _safe(fn[:-len("_base.svg")])
        m = meta.get(uid, {})
        base_svg = open(os.path.join(_SVG_DIR, fn), encoding="utf-8").read()
        aux_fn = f"{uid}_aux.svg"
        aux_svg = ""
        if os.path.exists(os.path.join(_SVG_DIR, aux_fn)):
            aux_svg = open(os.path.join(_SVG_DIR, aux_fn), encoding="utf-8").read()
        cards.append({
            "uid": uid,
            "note": m.get("note", ""),
            "aux_status": m.get("aux_status", ""),
            "check": m.get("check", ""),
            "base": base_svg,
            "aux": aux_svg,
        })

    parts = ["""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>CH27 gallery</title>
<style>
body{background:#0F1729;color:#D9E5F5;font-family:Arial,Helvetica,sans-serif;margin:0;padding:20px}
h1{font-size:22px;margin-bottom:6px}
.sub{color:#A6B7CC;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:18px}
.card{background:#16233c;border:1px solid #2a3a58;border-radius:8px;padding:12px}
.meta{font-size:12px;color:#A6B7CC;margin-bottom:8px;line-height:1.5}
.meta .uid{color:#EAF1FA;font-weight:bold}
.badge{display:inline-block;padding:1px 7px;border-radius:4px;font-size:11px;margin-left:4px}
.badge.built{background:#0f3d2e;color:#55D6BE}
.badge.unsup{background:#3d2a1f;color:#F6B44C}
.pair{display:flex;flex-direction:column;gap:8px}
.pane{background:#0F1729;border-radius:6px;padding:4px;overflow:hidden}
.pane-label{font-size:11px;color:#73B6E6;margin:4px 6px 2px}
.pane svg{width:100%;height:auto;display:block}
.missing{padding:24px;text-align:center;color:#7a8fa8;font-size:12px}
</style></head><body>
<h1>CH27 gallery — reflect_point / rotate_point / mark_intersection(id)</h1>
<div class="sub">Фон #0F1729 · base/aux парами · note + численная проверка</div>
<div class="grid">
"""]

    for c in cards:
        badge = "built" if c["aux_status"] == "AUX_BUILT" else "unsup"
        aux_block = c["aux"] or '<div class="missing">нет aux.svg</div>'
        parts.append(f"""
<div class="card">
  <div class="meta">
    <span class="uid">{c['uid']}</span>
    <span class="badge {badge}">{c['aux_status'] or '-'}</span><br>
    {c['note']}<br>{c['check']}
  </div>
  <div class="pair">
    <div class="pane"><div class="pane-label">base</div>{c['base']}</div>
    <div class="pane"><div class="pane-label">aux</div>{aux_block}</div>
  </div>
</div>""")

    parts.append("</div></body></html>")
    out = os.path.join(_OUT, "gallery.html")
    open(out, "w", encoding="utf-8").write("".join(parts))
    print(f"[ch27] gallery written: {out} ({len(cards)} cards)")


if __name__ == "__main__":
    main()
