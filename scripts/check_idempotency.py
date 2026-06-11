# -*- coding: utf-8 -*-
r"""Проверка идемпотентности normalize_roots по ВСЕМ полям данных.

Применяет normalize_roots дважды к каждому текстовому полю в JSON-файлах
и проверяет, что pass1 == pass2 везде (после первого прохода строка
стабильна). Падает с ненулевым кодом при первом расхождении.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.latex_root_normalizer import normalize_roots  # noqa: E402

DATA_FILES = [
    "data/olympiads/vsosh_10_11_full.json",
    "data/adaptive/adaptive_full_9120.json",
]


def walk(obj, path=""):
    """Рекурсивно выдаёт (путь, строка) для всех строковых значений."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def main():
    failures = 0
    checked = 0
    for rel in DATA_FILES:
        p = ROOT / rel
        data = json.loads(p.read_text(encoding="utf-8"))
        for path, s in walk(data):
            if not s:
                continue
            p1 = normalize_roots(s)
            p2 = normalize_roots(p1)
            checked += 1
            if p1 != p2:
                failures += 1
                print(f"NOT IDEMPOTENT in {rel}{path}")
                print(f"  pass1: {p1!r}")
                print(f"  pass2: {p2!r}")
    print(f"\nПроверено строк: {checked}   Несовпадений: {failures}")
    if failures:
        sys.exit(1)
    print("OK: normalize_roots идемпотентна на всех полях данных.")


if __name__ == "__main__":
    main()
