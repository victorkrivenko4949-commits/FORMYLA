#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика LaTeX в production БД на Render.
Запускать в Render Shell: python scripts/render_diagnose_latex.py
"""
import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# На Render БД может быть в другом месте
import os
for path in ['instance/formyla.db', '/var/data/formyla.db', 'formyla.db']:
    if os.path.exists(path):
        DB_PATH = path
        print(f"БД найдена: {path}")
        break
else:
    print("ОШИБКА: БД не найдена!")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("\n=== ДИАГНОСТИКА LaTeX В PRODUCTION БД ===\n")

# 1. Тип 1: ' rac{' (пробел+rac)
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '% rac{%'")
t1 = cur.fetchone()[0]
print(f"Тип 1 ' rac{{': {t1} задач")

# 2. Тип 2: form-feed + rac
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE ?", ('%\x0crac%',))
t2 = cur.fetchone()[0]
print(f"Тип 2 '\\x0crac': {t2} задач")

# 3. Правильный \frac (одинарный backslash в БД)
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%' || char(92) || 'frac%'")
t3 = cur.fetchone()[0]
print(f"Правильный '\\frac': {t3} задач")

# 4. Примеры битых задач
print("\nПримеры задач с ' rac{':")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE '% rac{%' LIMIT 5")
for row in cur.fetchall():
    idx = row[1].find(' rac{')
    snippet = row[1][max(0,idx-10):idx+20]
    print(f"  ID={row[0]}: {repr(snippet)}")

# 5. Примеры задач с form-feed
if t2 > 0:
    print("\nПримеры задач с form-feed:")
    cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE ? LIMIT 5", ('%\x0crac%',))
    for row in cur.fetchall():
        idx = row[1].find('\x0c')
        snippet = row[1][max(0,idx-5):idx+15]
        print(f"  ID={row[0]}: {repr(snippet)}")

# 6. Первая задача с frac — RAW
print("\nПервая задача с 'frac' — RAW bytes:")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE '%frac%' LIMIT 1")
row = cur.fetchone()
if row:
    idx = row[1].find('frac')
    snippet = row[1][max(0,idx-5):idx+15]
    print(f"  ID={row[0]}: {repr(snippet)}")
    print(f"  bytes: {snippet.encode('utf-8')}")

print("\n=== ИТОГ ===")
print(f"Нужно починить: {t1 + t2} задач")
print("Запусти: python scripts/fix_broken_rac.py --apply")

conn.close()
