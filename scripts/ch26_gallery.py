# -*- coding: utf-8 -*-
"""CH26: собрать тёмную HTML-галерею из output/ch26/svg."""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "output", "ch26")
_SVG_DIR = os.path.join(_OUT, "svg")
_GALLERY = os.path.join(_OUT, "gallery")


def main():
    os.makedirs(_GALLERY, exist_ok=True)
    svg_files = sorted(
        f for f in os.listdir(_SVG_DIR) if f.endswith("_base.svg")
    ) if os.path.isdir(_SVG_DIR) else []

    # Метаданные из probe_results.json.
    meta = {}
    results_path = os.path.join(_OUT, "probe_results.json")
    if os.path.exists(results_path):
        data = json.load(open(results_path, encoding="utf-8"))
        for r in data:
            uid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(r.get("task_uid", "")))
            meta[uid] = {
                "inscribed": r.get("used_inscribed"),
                "poc": r.get("used_point_on_circle"),
                "inc": r.get("n_incidences"),
                "dev": r.get("max_dev"),
                "status": r.get("status"),
                "cond": (r.get("condition") or "")[:90],
            }

    cards = []
    for fn in svg_files:
        uid = fn[:-len("_base.svg")]
        svg_text = open(os.path.join(_SVG_DIR, fn), encoding="utf-8").read()
        m = meta.get(uid, {})
        cards.append({
            "uid": uid,
            "status": m.get("status", "?"),
            "inscribed": m.get("inscribed"),
            "poc": m.get("poc"),
            "inc": m.get("inc"),
            "dev": m.get("dev"),
            "cond": m.get("cond", ""),
            "svg": svg_text,
        })

    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>CH26 gallery</title>
<style>
  body { background: #0F1729; color: #D9E5F5; font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 20px; }
  h1 { font-size: 22px; margin-bottom: 6px; }
  .sub { color: #A6B7CC; font-size: 13px; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); gap: 18px; }
  .card { background: #16233c; border: 1px solid #2a3a58; border-radius: 8px; padding: 12px; }
  .meta { font-size: 12px; color: #A6B7CC; margin-bottom: 8px; line-height: 1.5; }
  .meta .uid { color: #EAF1FA; font-weight: bold; }
  .meta .badge { display: inline-block; padding: 1px 7px; border-radius: 4px; font-size: 11px; margin-left: 4px; }
  .badge.done { background: #0f3d2e; color: #55D6BE; }
  .badge.failed { background: #3d1f1f; color: #F6B44C; }
  .pane { background: #0F1729; border-radius: 6px; padding: 4px; overflow: hidden; }
  .pane svg { width: 100%; height: auto; display: block; }
</style>
</head>
<body>
<h1>CH26 gallery — base-чертежи (инцидентность)</h1>
<div class="sub">Фон #0F1729 · inscribed_polygon / point_on_circle</div>
<div class="grid">
""")

    for c in cards:
        badge = "done" if c["status"] == "done" else "failed"
        parts.append(f"""
<div class="card">
  <div class="meta">
    <span class="uid">{c['uid']}</span>
    <span class="badge {badge}">{c['status']}</span><br>
    inscribed={c['inscribed']} · point_on_circle={c['poc']} · incidences={c['inc']} · max_dev={c['dev']}<br>
    {c['cond']}
  </div>
  <div class="pane">{c['svg']}</div>
</div>""")

    parts.append("""
</div>
</body>
</html>
""")

    out_path = os.path.join(_GALLERY, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print(f"[ch26] gallery written: {out_path} ({len(cards)} cards)")


if __name__ == "__main__":
    main()
