#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика LaTeX в БД: ищем битые \frac → rac
"""
import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 70)
print("ДИАГНОСТИКА LaTeX В БД")
print("=" * 70)

# 1. Найти задачу с '30 учеников'
print("\n[1] Задача с '30 учеников' и 'математическ':")
cur.execute("""SELECT id, task_text FROM adaptive_tasks 
WHERE task_text LIKE '%30 учеников%' AND task_text LIKE '%математическ%' LIMIT 3""")
rows = cur.fetchall()
if rows:
    for row in rows:
        print(f"  ID={row[0]}")
        print(f"  repr(task_text[:300]):")
        print(f"  {repr(row[1][:300])}")
        print()
else:
    print("  Задача не найдена. Ищем по 'rac' без frac...")
    cur.execute("""SELECT id, task_text FROM adaptive_tasks 
    WHERE task_text LIKE '%rac{%' LIMIT 3""")
    rows2 = cur.fetchall()
    for row in rows2:
        print(f"  ID={row[0]}")
        print(f"  repr: {repr(row[1][:300])}")
        print()

# 2. Проверяем form-feed символ \x0c (это \f в Python)
print("\n[2] Задачи с form-feed символом (\\x0c = \\f):")
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE ?", ('%\x0c%',))
ff_count = cur.fetchone()[0]
print(f"  Задач с \\x0c: {ff_count}")

if ff_count > 0:
    cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE ? LIMIT 3", ('%\x0c%',))
    for row in cur.fetchall():
        print(f"  ID={row[0]}: {repr(row[1][:200])}")

# 3. Задачи где есть 'rac{' но нет '\frac' (битый LaTeX)
print("\n[3] Задачи с 'rac{' (потенциально битый \\frac):")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE '%rac{%' LIMIT 5")
rows = cur.fetchall()
print(f"  Найдено (первые 5):")
for row in rows:
    idx = row[1].find('rac{')
    snippet = row[1][max(0,idx-5):idx+20]
    print(f"  ID={row[0]}: ...{repr(snippet)}...")

# 4. Считаем задачи с \frac (правильный LaTeX)
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%\\\\frac%'")
frac_ok = cur.fetchone()[0]
print(f"\n[4] Задачи с правильным \\\\frac: {frac_ok}")

# 5. Проверяем конкретно: что хранится в БД
print("\n[5] Первые 3 задачи с 'frac' в тексте — RAW repr:")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE '%frac%' LIMIT 3")
for row in cur.fetchall():
    idx = row[1].find('frac')
    snippet = row[1][max(0,idx-10):idx+30]
    print(f"  ID={row[0]}: {repr(snippet)}")

# 6. Проверяем solution тоже
print("\n[6] Задачи с form-feed в solution:")
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE solution LIKE ?", ('%\x0c%',))
sol_ff = cur.fetchone()[0]
print(f"  solution с \\x0c: {sol_ff}")

# 7. Итог
print("\n[7] ИТОГ — что в БД:")
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%\\frac%'")
single_slash = cur.fetchone()[0]
print(f"  '\\frac' (одинарный слэш, Python \\f+rac): {single_slash}")

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%\\\\frac%'")
double_slash = cur.fetchone()[0]
print(f"  '\\\\frac' (двойной слэш, правильный LaTeX): {double_slash}")

# Проверяем через Python bytes
cur.execute("SELECT task_text FROM adaptive_tasks WHERE task_text LIKE '%frac%' LIMIT 1")
row = cur.fetchone()
if row:
    text = row[0]
    idx = text.find('frac')
    if idx >= 0:
        snippet = text[max(0,idx-5):idx+10]
        print(f"\n  Пример вокруг 'frac': {repr(snippet)}")
        print(f"  Байты: {snippet.encode('utf-8')}")

conn.close()
print("\n" + "=" * 70)
