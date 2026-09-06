# -*- coding: utf-8 -*-
"""CH24: собрать тёмную HTML-галерею всех SVG из output/ch24.

Пары base/aux с подписью task_uid, solution_style, aux_status.
Фон галереи #0F1729.

Запуск: python scripts/ch24_gallery.py
"""
import csv
import html
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OUT = os.path.join(_ROOT, "output", "ch24")
_SVG_DIR = os.path.join(_OUT, "svg")
_GALLERY_DIR = os.path.join(_OUT, "gallery")


def _safe(uid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(uid))


def load_rows():
    results_path = os.path.join(_OUT, "results.csv")
    rows = []
    if not os.path.exists(results_path):
        return rows
    with open(results_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def read_svg_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def main():
    rows = load_rows()
    if not rows:
        print("Нет results.csv — прогон ещё не завершён.")
        return

    os.makedirs(_GALLERY_DIR, exist_ok=True)

    cards = []
    for r in rows:
        uid = r.get("task_uid", "?")
        safe = _safe(uid)
        style = r.get("solution_style", "") or "unknown"
        status = r.get("status", "")
        aux_status = r.get("aux_status", "") or "-"

        base_path = os.path.join(_SVG_DIR, f"{safe}_base.svg")
        aux_path = os.path.join(_SVG_DIR, f"{safe}_aux.svg")
        base_svg = read_svg_text(base_path)
        aux_svg = read_svg_text(aux_path)

        base_block = ""
        aux_block = ""
        if base_svg:
            base_block = base_svg
        else:
            base_block = (
                '<div class="missing">нет base.svg</div>'
            )
        if aux_svg:
            aux_block = aux_svg
        else:
            aux_block = (
                f'<div class="missing">нет aux.svg '
                f'(status={html.escape(status)})</div>'
            )

        cards.append({
            "uid": html.escape(uid),
            "style": html.escape(style),
            "status": html.escape(status),
            "aux_status": html.escape(aux_status),
            "base": base_block,
            "aux": aux_block,
        })

    # Построим HTML.
    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>CH24 gallery</title>
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
  .badge.aux-built { background: #0f3d2e; color: #55D6BE; }
  .badge.aux-not-needed { background: #22304a; color: #A6B7CC; }
  .pair { display: flex; flex-direction: column; gap: 8px; }
  .pane { background: #0F1729; border-radius: 6px; padding: 4px; overflow: hidden; }
  .pane-label { font-size: 11px; color: #73B6E6; margin: 4px 6px 2px; }
  .pane svg { width: 100%; height: auto; display: block; }
  .missing { padding: 24px; text-align: center; color: #7a8fa8; font-size: 12px; }
</style>
</head>
<body>
<h1>CH24 gallery — все SVG (base / aux)</h1>
<div class="sub">Фон #0F1729 · пары по task_uid · solution_style · aux_status</div>
<div class="grid">
""")

    for c in cards:
        status_badge = "done" if c["status"] == "done" else "failed"
        aux_badge_class = (
            "aux-built" if c["aux_status"] == "AUX_BUILT"
            else "aux-not-needed"
        )
        parts.append(f"""
<div class="card">
  <div class="meta">
    <span class="uid">{c['uid']}</span>
    <span class="badge {status_badge}">{c['status']}</span>
    <span class="badge {aux_badge_class}">{c['aux_status']}</span><br>
    style: {c['style']}
  </div>
  <div class="pair">
    <div class="pane"><div class="pane-label">base</div>{c['base']}</div>
    <div class="pane"><div class="pane-label">aux</div>{c['aux']}</div>
  </div>
</div>""")

    parts.append("""
</div>
</body>
</html>
""")

    gallery_path = os.path.join(_GALLERY_DIR, "index.html")
    with open(gallery_path, "w", encoding="utf-8") as f:
        f.write("".join(parts))

    n_base = sum(1 for c in cards if "missing" not in c["base"])
    n_aux = sum(1 for c in cards if "missing" not in c["aux"])
    print(f"[ch24] gallery written: {gallery_path}")
    print(f"[ch24] cards={len(cards)} with_base={n_base} with_aux={n_aux}")


if __name__ == "__main__":
    main()
