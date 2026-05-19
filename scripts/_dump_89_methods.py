# -*- coding: utf-8 -*-
"""Дамп каталога 89 методов в Markdown — точно как на сайте /olympiads/methods.

Запуск:
    python scripts/_dump_89_methods.py
Результат:
    docs/89_methods_list.md
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "olympiads" / "methods_catalog_89.json"
OUT = ROOT / "docs" / "89_methods_list.md"

SECTION_TITLES = {
    "A": "Алгебраические преобразования и тождества",
    "B": "Логика и текстовые рассуждения",
    "C": "Арифметика и комбинаторика чисел",
    "D": "Теория чисел",
    "E": "Принципы и идеи (инвариант, экстремум, индукция, …)",
    "F": "Геометрия",
    "G": "Анализ и неравенства",
    "H": "Графы и продвинутая комбинаторика",
}


def _safe(k):
    return (
        k.get("section", "Z"),
        int(k.get("sort_order") or 999),
        k.get("method_code", ""),
    )


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    data.sort(key=_safe)

    lines: list[str] = [
        "# Каталог 89 методов FORMYLA",
        "",
        "Источник: `data/olympiads/methods_catalog_89.json` — тот же файл, что подгружается на странице **/olympiads/methods** (раздел «Каталог методов»).",
        "",
        f"Всего методов: **{len(data)}**",
        "",
    ]

    current = None
    for m in data:
        s = m.get("section", "?")
        if s != current:
            lines.append("")
            title = SECTION_TITLES.get(s, "?")
            lines.append(f"## Раздел {s} — {title}")
            lines.append("")
            current = s
        code = m.get("method_code", "?")
        name = m.get("method_name", "(без названия)")
        lines.append(f"- **{code}** — {name}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: {OUT} ({len(data)} методов)")


if __name__ == "__main__":
    main()
