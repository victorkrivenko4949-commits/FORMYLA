# -*- coding: utf-8 -*-
"""Добавляет тёмный фон сайта в уже построенные чертежи.
Запуск:  python fix_bg.py
"""
import pathlib
import re

BG = '<rect width="620" height="620" fill="#070C18"/>'
folders = [pathlib.Path("out/figures"), pathlib.Path("out/figures_all")]

total_done = 0
total_already = 0
for folder in folders:
    if not folder.exists():
        print(f"папки {folder} нет — пропускаю")
        continue
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
    print(f"{folder}: поправлено {done}, уже были с фоном {already}")
    total_done += done
    total_already += already

print("итого поправлено:", total_done)
print("итого всего чертежей:", total_done + total_already)
