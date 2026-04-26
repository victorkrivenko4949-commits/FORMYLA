#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ФАЗА 0: Матрица (тема × difficulty) для классов 5, 6, 7.
Цель: 25 задач на каждую комбинацию (grade, topic, difficulty).
Только чтение — БД не меняется.
Сохраняет: reports/matrix_5_7_grades.csv
"""

import sys
import io
import sqlite3
import csv
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"
REPORTS_DIR = "reports"
CSV_PATH = f"{REPORTS_DIR}/matrix_5_7_grades.csv"
TARGET = 25  # целевое количество задач на ячейку

os.makedirs(REPORTS_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print("МАТРИЦА (тема × difficulty) для классов 5, 6, 7")
print(f"Цель: {TARGET} задач на каждую ячейку")
print("=" * 70)

# ─── Собираем данные ──────────────────────────────────────────────────────────
rows_csv = []
all_data = {}  # (grade, topic) -> {d1..d5, total}

for grade in [5, 6, 7]:
    cur.execute("""
        SELECT
            topic,
            SUM(CASE WHEN difficulty_level=1 THEN 1 ELSE 0 END) AS d1,
            SUM(CASE WHEN difficulty_level=2 THEN 1 ELSE 0 END) AS d2,
            SUM(CASE WHEN difficulty_level=3 THEN 1 ELSE 0 END) AS d3,
            SUM(CASE WHEN difficulty_level=4 THEN 1 ELSE 0 END) AS d4,
            SUM(CASE WHEN difficulty_level=5 THEN 1 ELSE 0 END) AS d5,
            COUNT(*) AS total
        FROM adaptive_tasks
        WHERE class_level = ?
        GROUP BY topic
        ORDER BY topic
    """, (grade,))
    rows = cur.fetchall()

    print(f"\n{'─'*70}")
    print(f"КЛАСС {grade}")
    print(f"{'─'*70}")
    print(f"{'Тема':<30} {'D1':>5} {'D2':>5} {'D3':>5} {'D4':>5} {'D5':>5} {'ИТОГО':>7}")
    print(f"{'─'*70}")

    for row in rows:
        topic = row['topic'] or '(NULL)'
        d1, d2, d3, d4, d5 = row['d1'], row['d2'], row['d3'], row['d4'], row['d5']
        total = row['total']

        # Дефициты
        def_d1 = max(0, TARGET - d1)
        def_d2 = max(0, TARGET - d2)
        def_d3 = max(0, TARGET - d3)
        def_d4 = max(0, TARGET - d4)
        def_d5 = max(0, TARGET - d5)
        total_deficit = def_d1 + def_d2 + def_d3 + def_d4 + def_d5

        print(f"{topic:<30} {d1:>5} {d2:>5} {d3:>5} {d4:>5} {d5:>5} {total:>7}")

        rows_csv.append({
            'grade': grade,
            'topic': topic,
            'd1': d1, 'd2': d2, 'd3': d3, 'd4': d4, 'd5': d5,
            'total': total,
            'deficit_d1': def_d1, 'deficit_d2': def_d2,
            'deficit_d3': def_d3, 'deficit_d4': def_d4,
            'deficit_d5': def_d5,
            'total_deficit': total_deficit
        })
        all_data[(grade, topic)] = {
            'd1': d1, 'd2': d2, 'd3': d3, 'd4': d4, 'd5': d5, 'total': total
        }

# ─── Сохраняем CSV ────────────────────────────────────────────────────────────
with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
    fieldnames = ['grade', 'topic', 'd1', 'd2', 'd3', 'd4', 'd5', 'total',
                  'deficit_d1', 'deficit_d2', 'deficit_d3', 'deficit_d4', 'deficit_d5',
                  'total_deficit']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows_csv)
print(f"\n✅ CSV сохранён: {CSV_PATH}")

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

# Все ячейки (grade, topic, difficulty)
cells_under = []   # < 25
cells_zero = []    # == 0
cells_over = []    # > 50

for row in rows_csv:
    grade = row['grade']
    topic = row['topic']
    for d in range(1, 6):
        count = row[f'd{d}']
        if count == 0:
            cells_zero.append((grade, topic, d, count))
        elif count < TARGET:
            cells_under.append((grade, topic, d, count))
        if count > 50:
            cells_over.append((grade, topic, d, count))

total_cells = len(rows_csv) * 5
print(f"\nВсего ячеек (grade × topic × difficulty): {total_cells}")
print(f"Ячеек с <{TARGET} задач (дефицит):        {len(cells_under) + len(cells_zero)}")
print(f"  из них с 0 задач (полные дыры):          {len(cells_zero)}")
print(f"Ячеек с >50 задач (переполнение):          {len(cells_over)}")

# Топ-10 дефицитов
print(f"\nТОП-10 САМЫХ БОЛЬШИХ ДЕФИЦИТОВ (нужно добавить больше всего):")
deficits = []
for row in rows_csv:
    grade = row['grade']
    topic = row['topic']
    for d in range(1, 6):
        count = row[f'd{d}']
        deficit = max(0, TARGET - count)
        if deficit > 0:
            deficits.append((deficit, grade, topic, d, count))

deficits.sort(reverse=True)
print(f"{'Дефицит':>8} {'Класс':>6} {'Тема':<30} {'D':>3} {'Есть':>6}")
print(f"{'─'*60}")
for deficit, grade, topic, d, count in deficits[:10]:
    print(f"{deficit:>8} {grade:>6} {topic:<30} {d:>3} {count:>6}")

# Топ-10 переполненных
print(f"\nТОП-10 ПЕРЕПОЛНЕННЫХ ЯЧЕЕК (>50 задач):")
cells_over.sort(key=lambda x: -x[3])
if cells_over:
    print(f"{'Класс':>6} {'Тема':<30} {'D':>3} {'Кол-во':>8}")
    print(f"{'─'*50}")
    for grade, topic, d, count in cells_over[:10]:
        print(f"{grade:>6} {topic:<30} {d:>3} {count:>8}")
else:
    print("  Переполненных ячеек нет")

# Итоговый дефицит по классам
print(f"\nОБЩИЙ ДЕФИЦИТ ПО КЛАССАМ (сколько задач нужно сгенерировать):")
for grade in [5, 6, 7]:
    grade_rows = [r for r in rows_csv if r['grade'] == grade]
    total_def = sum(r['total_deficit'] for r in grade_rows)
    zero_cells = sum(1 for r in grade_rows for d in range(1,6) if r[f'd{d}'] == 0)
    print(f"  Класс {grade}: дефицит {total_def} задач, полных дыр: {zero_cells}")

print("\n" + "=" * 70)
conn.close()
