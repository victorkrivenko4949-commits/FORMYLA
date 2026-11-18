# -*- coding: utf-8 -*-
"""
scripts/import_daily_bank.py — заливка банка «Задачи дня» (daily_task_bank).

Шаг 8 (вариант Б): ключ темы — theme_id вида G9_T16 (см. services/daily_bank_keys.py).
Класс зашит в ключ, поэтому задачи одного класса не могут попасть другому.

Формат входного файла (JSONL), одна строка = одна задача:

    {
      "subtopic": "G9_T16",                # theme_id: G<класс>_T<номер>, как в data/theme_to_section.json
      "section": "geometry",               # можно опустить — возьмётся из справочника; если указан, должен совпадать
      "level": 2,                          # 1..4
      "statement": "...",                  # условие (обязательно)
      "answer": "...",                     # ответ (обязательно)
      "solution": "...",                   # опционально
      "svg_path": "", "svg_aux_path": "",  # опционально
      "needs_figure": false,
      "source_model": "manual",            # deepseek | sonnet | manual
      "position": 1                        # 1..35, обязательно и уникально внутри (subtopic, level)
    }

Запуск:
    python scripts/import_daily_bank.py путь/к/файлу.jsonl [--apply]

Без --apply — dry-run (проверка и отчёт), ничего не пишет.
С --apply — пишет в таблицу daily_task_bank (идемпотентно по (subtopic, level, position)).
Строки с ошибками не пишутся никогда; при любой ошибке в файле --apply отказывается писать
(флаг --partial разрешает записать только валидные строки).
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.daily_bank_keys import (  # noqa: E402
    CANONICAL_SECTIONS, parse_theme_id, section_of_theme, is_known_theme,
)

MAX_POSITION = 35


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filepath")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--partial", action="store_true",
                    help="с --apply: записать валидные строки, даже если в файле есть ошибки")
    args = ap.parse_args()

    if not os.path.exists(args.filepath):
        print(f"Файл не найден: {args.filepath}")
        return 2

    rows, errors = [], []
    seen_keys, seen_texts = set(), set()
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
            parsed = parse_theme_id(subtopic)
            if parsed is None:
                errors.append((lineno, f"subtopic {subtopic!r} не theme_id вида G9_T16 (регистр важен)"))
                continue
            if not is_known_theme(subtopic):
                errors.append((lineno, f"тема {subtopic} отсутствует в data/theme_to_section.json"))
                continue

            reg_section = section_of_theme(subtopic)
            section = (obj.get("section") or "").strip().lower()
            if not section:
                section = reg_section
            if section not in CANONICAL_SECTIONS:
                errors.append((lineno, f"невалидный section: {section!r}"))
                continue
            if reg_section and section != reg_section:
                errors.append((lineno, f"section {section!r} не совпадает со справочником ({reg_section}) для {subtopic}"))
                continue

            try:
                level = int(obj.get("level"))
            except (TypeError, ValueError):
                errors.append((lineno, f"невалидный level: {obj.get('level')!r}"))
                continue
            if not (1 <= level <= 4):
                errors.append((lineno, f"level вне диапазона 1..4: {level}"))
                continue

            statement = (obj.get("statement") or "").strip()
            answer = (obj.get("answer") or "").strip()
            if not statement:
                errors.append((lineno, "пустой statement"))
                continue
            if not answer:
                errors.append((lineno, "пустой answer — задача без ответа не проверяется"))
                continue

            try:
                position = int(obj.get("position"))
            except (TypeError, ValueError):
                errors.append((lineno, f"position обязателен (1..{MAX_POSITION}), получено {obj.get('position')!r}"))
                continue
            if not (1 <= position <= MAX_POSITION):
                errors.append((lineno, f"position вне диапазона 1..{MAX_POSITION}: {position}"))
                continue

            key = (subtopic, level, position)
            if key in seen_keys:
                errors.append((lineno, f"дубликат ключа {key} внутри файла"))
                continue
            nt = _norm(statement)
            if nt in seen_texts:
                errors.append((lineno, "дубликат условия внутри файла"))
                continue
            seen_keys.add(key)
            seen_texts.add(nt)

            rows.append({
                "subtopic": subtopic,
                "section": section,
                "level": level,
                "statement": statement,
                "answer": answer,
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

    c = Counter((r["subtopic"], r["level"]) for r in rows)
    print(f"\n[СВОДКА] валидных задач: {len(rows)}, пар (subtopic, level): {len(c)}")
    by_grade = Counter(parse_theme_id(r["subtopic"])[0] for r in rows)
    print("  по классам:", dict(sorted(by_grade.items())))
    print("  по уровням:", dict(sorted(Counter(r["level"] for r in rows).items())))

    if not args.apply:
        print("\n[dry-run] Для записи добавь --apply.")
        return 0 if not errors else 1
    if errors and not args.partial:
        print("\n[apply] В файле есть ошибки — запись отменена. Исправь их или добавь --partial.")
        return 1
    if not rows:
        print("\n[apply] Нечего записывать.")
        return 1

    from models import db, DailyTaskBank
    from app import app

    with app.app_context():
        existing = {(t.subtopic, t.level, t.position) for t in DailyTaskBank.query.all()}
        existing_texts = {_norm(t.statement) for t in DailyTaskBank.query.all()}
        created = skipped = 0
        for r in rows:
            key = (r["subtopic"], r["level"], r["position"])
            if key in existing or _norm(r["statement"]) in existing_texts:
                skipped += 1
                continue
            db.session.add(DailyTaskBank(**r))
            created += 1
        db.session.commit()

    print(f"\n[APPLY] создано: {created}, пропущено (уже есть): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
