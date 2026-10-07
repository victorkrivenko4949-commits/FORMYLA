# -*- coding: utf-8 -*-
"""Собирает все чертежи в одну HTML-страницу для удобного просмотра —
тёмный фон страницы, сетка, подпись имени файла под каждым чертежом.

Запуск:
    python make_gallery.py

Откроет out\\gallery.html — двойной щелчок открывает в браузере.
"""
import pathlib

folder = pathlib.Path("out/figures_all")
if not folder.exists():
    folder = pathlib.Path("out/figures")
if not folder.exists():
    print("нет ни out/figures_all, ни out/figures")
    raise SystemExit(1)

files = sorted(folder.glob("*.svg"))
base = [f for f in files if not f.name.endswith("_aux.svg")]
aux = {f.name[:-8]: f for f in files if f.name.endswith("_aux.svg")}

cards = []
for f in base:
    uid = f.stem
    rel = f.relative_to(folder.parent.parent) if folder.parent.parent in f.parents else f
    a = aux.get(uid)
    cards.append(f'''
    <div class="card">
      <div class="imgs">
        <div><img src="{f.as_posix()}"><div class="tag">базовый</div></div>
        {f'<div><img src="{a.as_posix()}"><div class="tag">с доп. построением</div></div>' if a else ''}
      </div>
      <div class="name">{uid[:12]}</div>
    </div>''')

html = f'''<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body {{ background:#070C18; color:#8C9ABC; font-family:system-ui,sans-serif;
          margin:0; padding:24px; }}
  h1 {{ color:#E6EBF7; font-size:18px; }}
  .grid {{ display:flex; flex-wrap:wrap; gap:20px; }}
  .card {{ background:#0E1830; border:1px solid #1C2B4F; border-radius:14px;
           padding:12px; width:640px; }}
  .imgs {{ display:flex; gap:8px; }}
  .imgs img {{ width:100%; max-width:310px; border-radius:8px; }}
  .tag {{ text-align:center; font-size:11px; margin-top:4px; }}
  .name {{ text-align:center; margin-top:8px; font-size:12px; color:#5A5957; }}
</style></head>
<body>
<h1>Чертежи FORMYLA — {len(base)} штук, из них {len(aux)} с доп. построением</h1>
<div class="grid">
{"".join(cards)}
</div>
</body></html>'''

out = pathlib.Path("out/gallery.html")
out.write_text(html, encoding="utf-8")
print(f"готово: {out} — {len(base)} чертежей, {len(aux)} с доп. построением")
