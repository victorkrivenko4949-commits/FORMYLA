# -*- coding: utf-8 -*-
"""CH19 Step 1: потоковая инвентаризация FORMYLA_geometry_7_11_chertezh_v13.jsonl.

Читает файл построчно (не загружая целиком в память) и печатает отчёт.
Никаких внешних зависимостей.  Не трогает конвейер/движок/промпты.
"""
import json
import os
import statistics
import sys
from collections import Counter, defaultdict

INPUT = "FORMYLA_geometry_7_11_chertezh_v13.jsonl"

# Термины для «упоминаний» (простые подстроки по стемам, без стеммера).
TERMS = {
    "окружность": ("окружност", "окружность"),
    "высота": ("высот",),
    "медиана": ("медиан",),
    "биссектриса": ("биссектрис",),
    "вписанная окружность": ("вписанн", "вписанная окружность"),
    "описанная окружность": ("описанн", "описанная окружность"),
    "ортоцентр": ("ортоцентр",),
    "площадь": ("площад",),
}


def term_hit(text, stems):
    t = (text or "").lower()
    return any(s in t for s in stems)


def main():
    if not os.path.exists(INPUT):
        print(f"Файл {INPUT} не найден")
        sys.exit(1)

    total = 0
    grade = Counter()
    level = Counter()
    theme = Counter()
    approve = 0
    nonempty_solution = 0
    stmt_lens = []
    sol_lens = []
    term_counts = Counter()
    broken = 0

    with open(INPUT, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                broken += 1
                continue
            total += 1
            grade[str(rec.get("grade"))] += 1
            level[str(rec.get("level"))] += 1
            theme[str(rec.get("theme_id"))] += 1

            if rec.get("quality_status") == "APPROVE":
                approve += 1

            solution = rec.get("solution") or ""
            if solution.strip():
                nonempty_solution += 1
            sol_lens.append(len(solution))

            statement = rec.get("statement") or ""
            stmt_lens.append(len(statement))

            blob = (statement + "\n" + solution).lower()
            for name, stems in TERMS.items():
                if any(s in blob for s in stems):
                    term_counts[name] += 1

    def pct(n):
        return f"{100.0 * n / total:.2f}%" if total else "0%"

    def med(nums):
        return round(statistics.median(nums), 1) if nums else 0

    def p90(nums):
        if not nums:
            return 0
        s = sorted(nums)
        return round(s[int(0.90 * (len(s) - 1))], 1)

    print("=" * 70)
    print("CH19 INVENTORY:", INPUT)
    print("=" * 70)
    print(f"Всего записей: {total}")
    print(f"Битых строк (JSON parse error): {broken}")
    print(f"quality_status=APPROVE: {approve} ({pct(approve)})")
    print(f"Непустое solution: {nonempty_solution} ({pct(nonempty_solution)})")
    print()
    print("Распределение по grade:")
    for g in sorted(grade, key=lambda x: (int(x) if x.isdigit() else 999, x)):
        print(f"  grade {g}: {grade[g]} ({pct(grade[g])})")
    print()
    print("Распределение по level:")
    for lv in sorted(level, key=lambda x: (int(x) if x.isdigit() else 999, x)):
        print(f"  level {lv}: {level[lv]} ({pct(level[lv])})")
    print()
    print("Топ-20 theme_id:")
    for tid, cnt in theme.most_common(20):
        print(f"  {tid}: {cnt} ({pct(cnt)})")
    print()
    print("Длины statement (медиана / p90 / max):",
          f"{med(stmt_lens)} / {p90(stmt_lens)} / {max(stmt_lens) if stmt_lens else 0}")
    print("Длины solution  (медиана / p90 / max):",
          f"{med(sol_lens)} / {p90(sol_lens)} / {max(sol_lens) if sol_lens else 0}")
    print()
    print("Упоминания терминов:")
    for name, _ in TERMS.items():
        print(f"  {name}: {term_counts[name]} ({pct(term_counts[name])})")
    print("=" * 70)


if __name__ == "__main__":
    main()
