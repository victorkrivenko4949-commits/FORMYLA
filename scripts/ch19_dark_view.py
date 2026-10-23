# -*- coding: utf-8 -*-
"""Создать HTML-галерею сгенерированных SVG на тёмном фоне (для ручной проверки)."""
import io
import os
import re
import sys
import html

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SVG_DIR = os.path.join("output", "ch19", "svg")
OUT = os.path.join("output", "ch19", "manual_review", "view_dark.html")

DARK_BG = "#0b1020"  # тёмно-синий, близкий к теме dark_geometry


def safe(uid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", uid)


def main():
    svgs = sorted(f for f in os.listdir(SVG_DIR) if f.endswith(".svg"))
    if not svgs:
        print("нет SVG")
        return

    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="ru"><head><meta charset="utf-8">')
    parts.append("<title>CH19 — чертежи (тёмный фон)</title>")
    parts.append(
        "<style>body{background:%s;color:#c8d6e5;"
        "font-family:Arial,Helvetica,sans-serif;margin:20px;}"
        ".fig{margin:24px 0;padding:16px;border:1px solid #2a3a55;"
        "border-radius:8px;display:inline-block;vertical-align:top;}"
        ".cap{font-size:13px;color:#7a8fa8;margin-bottom:6px;word-break:break-all;}"
        "svg{background:%s;display:block;}</style>" % (DARK_BG, DARK_BG)
    )
    parts.append("</head><body>")
    parts.append("<h2>CH19 — сгенерированные base-чертежи (тёмный фон)</h2>")

    for name in svgs:
        path = os.path.join(SVG_DIR, name)
        with open(path, encoding="utf-8") as f:
            svg_text = f.read()
        # Убираем XML-декларацию и встраиваем как есть.
        svg_body = re.sub(r"<\?xml[^>]*\?>", "", svg_text).strip()
        parts.append('<div class="fig">')
        parts.append(f'<div class="cap">{html.escape(name)}</div>')
        parts.append(svg_body)
        parts.append("</div>")

    parts.append("</body></html>")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print("wrote", OUT, "(", len(svgs), "SVG )")


if __name__ == "__main__":
    main()
