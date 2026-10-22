# -*- coding: utf-8 -*-
"""scripts/bank_add_tasks.py — добавить ПРОВЕРЕННЫЕ задачи в FORMYLA_BANK.jsonl.

Зачем: банк 44 МБ нельзя править через GitHub API; дырки (например геометрия L3)
заполняются пачками задач, которые сначала проходят ручную проверку в
data/bank_additions/*.jsonl, и только потом попадают в банк этим скриптом.

Правила:
  * берутся только строки с review_status == "approved" (флаг --all снимает фильтр);
  * обязательные поля: grade (5..11), topic, level (1..4), task_text, correct_answer;
  * дубликаты по тексту (нормализованному) с банком и внутри пачки отбрасываются;
  * position назначается автоматически: max(position в ячейке банка) + 1, 2, ...;
  * служебные поля review_status / reviewer / review_note / source в банк не пишутся;
  * без --apply ничего не меняется (dry-run с отчётом).

Запуск:
    python scripts/bank_add_tasks.py data/bank_additions/G9_T16_L3.jsonl            # отчёт
    python scripts/bank_add_tasks.py data/bank_additions/G9_T16_L3.jsonl --apply    # запись
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "FORMYLA_BANK.jsonl")
REQUIRED = ("grade", "topic", "level", "task_text", "correct_answer")
SERVICE_FIELDS = ("review_status", "reviewer", "review_note", "source")


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def load_bank(path):
    texts, maxpos, count = set(), defaultdict(int), 0
    if not os.path.exists(path):
        return texts, maxpos, 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            count += 1
            texts.add(norm_text(d.get("task_text") or d.get("statement") or ""))
            try:
                key = (int(d["grade"]), (d.get("topic") or "").strip(), int(d["level"]))
                pos = int(d.get("position") or 0)
            except (KeyError, TypeError, ValueError):
                continue
            maxpos[key] = max(maxpos[key], pos)
    return texts, maxpos, count


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("additions")
    ap.add_argument("--bank", default=BANK)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--all", action="store_true", help="брать все строки, не только approved")
    args = ap.parse_args()

    if not os.path.exists(args.additions):
        print(f"Файл не найден: {args.additions}")
        return 2

    bank_texts, maxpos, bank_count = load_bank(args.bank)
    print(f"[банк] {bank_count} задач, {len(maxpos)} ячеек с position")

    accepted, rejected, seen_batch = [], [], set()
    with open(args.additions, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                rejected.append((lineno, f"JSON: {e}"))
                continue
            status = (d.get("review_status") or "").strip().lower()
            if not args.all and status != "approved":
                rejected.append((lineno, f"review_status={status or 'пусто'} (нужно approved)"))
                continue
            missing = [k for k in REQUIRED if not str(d.get(k) or "").strip()]
            if missing:
                rejected.append((lineno, f"нет полей: {', '.join(missing)}"))
                continue
            try:
                grade, level = int(d["grade"]), int(d["level"])
            except (TypeError, ValueError):
                rejected.append((lineno, "grade/level не числа"))
                continue
            if not (5 <= grade <= 11) or not (1 <= level <= 4):
                rejected.append((lineno, f"grade={grade} или level={level} вне диапазона"))
                continue
            nt = norm_text(d["task_text"])
            if nt in bank_texts:
                rejected.append((lineno, "дубликат: такой текст уже есть в банке"))
                continue
            if nt in seen_batch:
                rejected.append((lineno, "дубликат внутри пачки"))
                continue
            seen_batch.add(nt)
            clean = {k: v for k, v in d.items() if k not in SERVICE_FIELDS}
            clean["grade"], clean["level"], clean["topic"] = grade, level, d["topic"].strip()
            key = (grade, clean["topic"], level)
            maxpos[key] += 1
            clean["position"] = maxpos[key]
            clean.setdefault("solution", "")
            accepted.append(clean)

    cells = defaultdict(int)
    for r in accepted:
        cells[(r["grade"], r["topic"], r["level"])] += 1
    print(f"[пачка] принято {len(accepted)}, отклонено {len(rejected)}")
    for (g, t, lv), n in sorted(cells.items()):
        print(f"  класс {g}, «{t}», L{lv}: +{n} (position до {maxpos[(g, t, lv)]})")
    for lineno, msg in rejected[:30]:
        print(f"  строка {lineno}: {msg}")

    if not args.apply:
        print("\n[dry-run] Банк не изменён. Для записи добавьте --apply.")
        return 0 if not rejected or accepted else 1
    if not accepted:
        print("\n[apply] Нечего добавлять.")
        return 1

    with open(args.bank, "a", encoding="utf-8") as f:
        for r in accepted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n[apply] В {os.path.basename(args.bank)} добавлено {len(accepted)} задач.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
