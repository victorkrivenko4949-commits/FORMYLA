# -*- coding: utf-8 -*-
"""Добавляет тёмный фон сайта в уже построенные чертежи.
Запуск:  python fix_bg.py
"""
import pathlib
import re

BG = '<rect width="620" height="620" fill="#070C18"/>'
folder = pathlib.Path("out/figures")

if not folder.exists():
    print("папки out/figures нет — запускать из корня проекта")
    raise SystemExit(1)

done = 0
already = 0
for f in sorted(folder.glob("*.svg")):
    t = f.read_text(encoding="utf-8")
    if "#070C18" in t:
        already += 1
        continue
    if "</style>" in t:
        t = t.replace("</style>", "</style>" + BG, 1)
    else:
        t = re.sub(r"(<svg[^>]*>)", r"\1" + BG, t, count=1)
    f.write_text(t, encoding="utf-8")
    done += 1

print("поправлено файлов:", done)
print("уже были с фоном:", already)
print("всего чертежей:", done + already)
