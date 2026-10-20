# -*- coding: utf-8 -*-
"""Корректор года по сезону в имени файла источника.

    python scripts/olymp_fix_year_by_source.py data/olymp_catalog_fixed/phystech.json [--apply]

Для записей, у которых source — PDF с сезоном в имени («...-24-25.pdf»), год должен быть
годом финала (2025). Без --apply только отчёт; с --apply файл перезаписывается
(бэкап рядом: <файл>.bak), старое значение пишется в qa.year_fix.
"""
import json, re, sys, shutil, collections
from urllib.parse import unquote
SEASON_RE = re.compile(r"(?:^|[-_])(\d{2})-(\d{2})(?=\.|$|[-_])")
def season_year(url):
    name = unquote((url or "").split("?")[0].split("/")[-1])
    m = SEASON_RE.search(name)
    if m and int(m.group(2)) == int(m.group(1)) + 1:
        return 2000 + int(m.group(2))
    return None
def main(argv):
    if not argv:
        print(__doc__); return 2
    path = argv[0]; apply = "--apply" in argv
    data = json.load(open(path, encoding="utf-8"))
    changed = []
    for r in data:
        sy = season_year(r.get("source", ""))
        if sy is None or r.get("year") == sy:
            continue
        changed.append((r.get("year"), sy, r.get("round"), r.get("grade"), r.get("variant")))
        if apply:
            r.setdefault("qa", {})["year_fix"] = {"old_year": r.get("year"), "new_year": sy, "reason": "сезон в имени файла source"}
            r["year"] = sy
    by = collections.Counter(changed)
    print(f"Записей с расхождением года: {len(changed)}")
    for (oy, ny, rnd, g, v), n in sorted(by.items(), key=lambda x: str(x)):
        print(f"  {oy} -> {ny} | {rnd} | {g} кл. | вариант {v or '-'} | задач: {n}")
    groups = collections.defaultdict(lambda: {"with": 0, "without": 0})
    for r in data:
        groups[(r.get("year"), r.get("round"), r.get("grade"))]["with" if r.get("variant") else "without"] += 1
    mixed = {k: v for k, v in groups.items() if v["with"] and v["without"]}
    if mixed:
        print("\nГруппы со смешанными записями (есть variant и без) — проверить вручную:")
        for k, v in sorted(mixed.items(), key=lambda x: str(x)):
            print(f"  {k[0]} | {k[1]} | {k[2]} кл.: с вариантом {v['with']}, без {v['without']}")
    if apply and changed:
        shutil.copy(path, path + ".bak")
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nЗаписано: {path} (бэкап: {path}.bak)")
    elif changed:
        print("\nЭто предпросмотр. Для записи добавьте --apply")
    return 0
if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
