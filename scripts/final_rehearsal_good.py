# -*- coding: utf-8 -*-
"""CH29: галерея ТОЛЬКО хороших чертежей + удаление плохих SVG."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "output", "final_rehearsal")
_SVG_DIR = os.path.join(_OUT, "svg")


def main():
    results = json.load(open(os.path.join(_OUT, "results.json"), encoding="utf-8"))
    rows = results["rows"]

    good = [r for r in rows if r["base_built"] and r["aux_status"] in ("AUX_BUILT", "AUX_NOT_NEEDED")]
    bad = [r for r in rows if r not in good]

    # Удаляем плохие SVG.
    removed = 0
    for r in bad:
        for p in (r.get("base_path"), r.get("aux_path")):
            if p and os.path.exists(p):
                os.remove(p)
                removed += 1

    # Галерея только хороших.
    cards = []
    for r in good:
        base = open(r["base_path"], encoding="utf-8").read() if r["base_path"] and os.path.exists(r["base_path"]) else ""
        aux = open(r["aux_path"], encoding="utf-8").read() if r["aux_path"] and os.path.exists(r["aux_path"]) else ""
        cards.append({
            "uid": r["task_uid"],
            "aux_status": r["aux_status"],
            "base": base,
            "aux": aux,
            "statement": r["statement"],
        })

    parts = ["""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>CH29 good figures</title>
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
.badge.not-needed{background:#22304a;color:#A6B7CC}
.pair{display:flex;flex-direction:column;gap:8px}
.pane{background:#0F1729;border-radius:6px;padding:4px;overflow:hidden}
.pane-label{font-size:11px;color:#73B6E6;margin:4px 6px 2px}
.pane svg{width:100%;height:auto;display:block}
.missing{padding:24px;text-align:center;color:#7a8fa8;font-size:12px}
</style></head><body>
<h1>CH29 — хорошие чертежи (17)</h1>
<div class="sub">Фон #0F1729 · только валидные base/aux</div>
<div class="grid">
"""]
    for c in cards:
        badge = "built" if c["aux_status"] == "AUX_BUILT" else "not-needed"
        aux_block = c["aux"] or '<div class="missing">aux не нужен</div>'
        base_block = c["base"] or '<div class="missing">нет base</div>'
        parts.append(f"""
<div class="card">
  <div class="meta">
    <span class="uid">{c['uid']}</span>
    <span class="badge {badge}">{c['aux_status']}</span><br>
    {c['statement']}
  </div>
  <div class="pair">
    <div class="pane"><div class="pane-label">base</div>{base_block}</div>
    <div class="pane"><div class="pane-label">aux</div>{aux_block}</div>
  </div>
</div>""")
    parts.append("</div></body></html>")

    out = os.path.join(_OUT, "good_gallery.html")
    open(out, "w", encoding="utf-8").write("".join(parts))
    print(f"Удалено плохих SVG: {removed}")
    print(f"Хороших чертежей: {len(cards)}")
    print(f"Галерея: {out}")


if __name__ == "__main__":
    main()
