# -*- coding: utf-8 -*-
"""
scripts/import_daily_bank.py — заливка банка «Задачи дня» (daily_task_bank).

Формат входного файла (JSONL), одна строка = одна задача:

    {
      "subtopic": "quadratic_equations",   # slug подтемы (как в monthly_plan)
      "section": "algebra",                # algebra | geometry | combinatorics | logic | number_theory
      "level": 2,                          # 1..4 (4-уровневая шкала)
      "statement": "Реши уравнение ...",
      "answer": "x = 5",
      "solution": "Перенесём ...",          # опционально
      "svg_path": "",                       # опционально (путь к готовому чертежу)
      "svg_aux_path": "",                   # опционально
      "needs_figure": false,                # нужен ли чертёж
      "source_model": "deepseek",           # deepseek | sonnet | manual
      "position": 1                         # 1..35 — порядковый номер внутри (subtopic, level)
    }

Запуск:
    python scripts/import_daily_bank.py путь/к/файлу.jsonl [--apply]

Без --apply — dry-run (проверка и отчёт), ничего не пишет.
С --apply — пишет в таблицу daily_task_bank (идемпотентно по (subtopic, level, position)).
"""

import argparse
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

VALID_SECTIONS = {"algebra", "geometry", "combinatorics", "logic", "number_theory"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filepath")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.filepath):
        print(f"Файл не найден: {args.filepath}")
        return 2

    rows = []
    errors = []
    with open(args.filepath, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append((lineno, f"JSON: {e}"))
                continue

            subtopic = (obj.get("subtopic") or "").strip()
            section = (obj.get("section") or "").strip().lower()
            level = obj.get("level")
            statement = (obj.get("statement") or "").strip()

            if not subtopic:
                errors.append((lineno, "пустой subtopic"))
                continue
            if section not in VALID_SECTIONS:
                errors.append((lineno, f"невалидный section: {section!r}"))
                continue
            try:
                level = int(level)
            except (TypeError, ValueError):
                errors.append((lineno, f"невалидный level: {level!r}"))
                continue
            if level < 1 or level > 4:
                errors.append((lineno, f"level вне диапазона 1..4: {level}"))
                continue
            if not statement:
                errors.append((lineno, "пустой statement"))
                continue

            position = obj.get("position")
            try:
                position = int(position) if position is not None else None
            except (TypeError, ValueError):
                position = None

            rows.append({
                "subtopic": subtopic,
                "section": section,
                "level": level,
                "statement": statement,
                "answer": obj.get("answer") or "",
                "solution": obj.get("solution") or "",
                "svg_path": obj.get("svg_path") or "",
                "svg_aux_path": obj.get("svg_aux_path") or "",
                "needs_figure": bool(obj.get("needs_figure", False)),
                "source_model": obj.get("source_model") or "manual",
                "position": position,
            })

    if errors:
        print(f"[ОШИБКИ] {len(errors)} строк отбраковано:")
        for lineno, msg in errors[:30]:
            print(f"  строка {lineno}: {msg}")
        if len(errors) > 30:
            print(f"  ... и ещё {len(errors) - 30}")

    # распределение
    c = Counter((r["subtopic"], r["level"]) for r in rows)
    print(f"\n[СВОДКА] валидных задач: {len(rows)}, пар (subtopic, level): {len(c)}")
    by_level = Counter(r["level"] for r in rows)
    print("  по уровням:", dict(sorted(by_level.items())))

    if not args.apply:
        print("\n[dry-run] Для записи добавь --apply.")
        return 0 if not errors else 1

    from models import db, DailyTaskBank
    from app import app

    with app.app_context():
        existing = {(t.subtopic, t.level, t.position) for t in DailyTaskBank.query.all()}
        created = updated = 0
        for r in rows:
            key = (r["subtopic"], r["level"], r["position"])
            if key in existing:
                updated += 1
                continue
            db.session.add(DailyTaskBank(**r))
            created += 1
        db.session.commit()

    print(f"\n[APPLY] создано: {created}, пропущено (уже есть): {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
