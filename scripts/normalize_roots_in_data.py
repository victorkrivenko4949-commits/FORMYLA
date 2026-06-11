# -*- coding: utf-8 -*-
r"""Канонизатор корней для ВСЕХ JSON-сидеров банка задач.

Проходит по активным data-файлам, прогоняет поля задач через
services.latex_root_normalizer.normalize_roots и переписывает файлы,
если что-то изменилось. Покрывает ВСЕ задачи (не только G6.17).

Запуск:
    python3 scripts/normalize_roots_in_data.py            # применить
    python3 scripts/normalize_roots_in_data.py --dry-run  # только показать
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from services.latex_root_normalizer import normalize_root_fields  # noqa: E402

# Активные источники данных (бэкапы НЕ трогаем).
DATA_FILES = [
    "data/olympiads/vsosh_10_11_full.json",
    "data/olympiads/vsosh9_full.json",
    "data/olympiads/master_5345.json",
    "data/olympiads/methods_catalog_105.json",
    "data/olympiads/methods_catalog_89.json",
    "data/olympiads/theory_65_methods.json",
    "data/olympiads/theory_24_methods.json",
    "data/olympiads/vsosh_9_2027_tasks.json",
    "data/olympiads/vsosh_9_2027_theory.json",
    "data/olympiads/grade_5_6_tasks.json",
    "data/adaptive/adaptive_full_9120.json",
    "adaptive_data/final/formyla_adaptive_final_polished.json",
]

FIELDS = ("text", "statement", "solution", "idea", "answer", "task_text",
          "solution_idea", "content")


def detect_indent(raw, data):
    """Определяет родной отступ файла (1..4), чтобы переписать минимально-диффно."""
    for ind in (1, 2, 3, 4):
        if json.dumps(data, ensure_ascii=False, indent=ind).strip() == raw.strip():
            return ind
    return 2


def process_file(rel, dry_run):
    p = ROOT / rel
    if not p.is_file():
        return None
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    indent = detect_indent(raw, data)
    wrapped = isinstance(data, dict)
    items = [data] if wrapped else data
    if not isinstance(items, list):
        return None
    changed_items = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        new_item, changed = normalize_root_fields(item, fields=FIELDS)
        if changed:
            ident = item.get("number") or item.get("id") or item.get("title") or idx
            pcode = item.get("probnik_code", "")
            changed_items.append((ident, pcode, changed))
            items[idx] = new_item
    if changed_items and not dry_run:
        out = items[0] if wrapped else items
        text = json.dumps(out, ensure_ascii=False, indent=indent)
        if raw.endswith("\n"):
            text += "\n"
        p.write_text(text, encoding="utf-8")
    return changed_items


def main():
    dry_run = "--dry-run" in sys.argv
    total = 0
    print(f"{'DRY-RUN' if dry_run else 'APPLY'} — канонизация корней в данных\n")
    for rel in DATA_FILES:
        res = process_file(rel, dry_run)
        if res is None:
            continue
        if res:
            print(f"=== {rel}: {len(res)} задач изменено ===")
            for ident, pcode, flds in res:
                print(f"    {ident} ({pcode}) поля: {', '.join(flds)}")
            total += len(res)
        else:
            print(f"  OK (без изменений)  {rel}")
    print(f"\nИТОГО изменено задач: {total}")


if __name__ == "__main__":
    main()
