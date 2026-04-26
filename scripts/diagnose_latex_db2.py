#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Детальная диагностика битого LaTeX в задачах 1051, 1054
"""
import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 70)
print("ДЕТАЛЬНАЯ ДИАГНОСТИКА БИТОГО LaTeX")
print("=" * 70)

# Проверяем задачу 1051 побайтово
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE id IN (1050, 1051, 1054)")
rows = cur.fetchall()
for row in rows:
    task_id, text = row
    print(f"\n--- ID={task_id} ---")
    # Найти первое вхождение 'rac' или 'frac'
    for keyword in ['frac', ' rac', '\x0crac']:
        idx = text.find(keyword)
        if idx >= 0:
            snippet = text[max(0,idx-5):idx+15]
            print(f"  Найдено '{keyword}' на позиции {idx}")
            print(f"  Контекст: {repr(snippet)}")
            print(f"  Байты:    {snippet.encode('utf-8')}")
            break

# Считаем разные типы битого LaTeX
print("\n" + "=" * 70)
print("ПОДСЧЁТ ТИПОВ БИТОГО LaTeX")
print("=" * 70)

# Тип 1: ' rac{' (пробел + rac, без backslash)
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '% rac{%'")
type1 = cur.fetchone()[0]
print(f"\nТип 1: ' rac{{' (пробел+rac, нет backslash): {type1} задач")

# Тип 2: '\x0crac{' (form-feed + rac)  
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE ?", ('%\x0crac{%',))
type2 = cur.fetchone()[0]
print(f"Тип 2: '\\x0crac{{' (form-feed+rac): {type2} задач")

# Тип 3: правильный \\frac (двойной слэш в Python = один \ в строке)
# В SQLite LIKE '%\frac%' ищет буквально \frac
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%\\frac%'")
type3_single = cur.fetchone()[0]
print(f"Тип 3: '\\frac' (одинарный backslash в БД): {type3_single} задач")

# Проверяем через Python: ищем задачи где есть \frac как Python-строка (один слэш)
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%' || char(92) || 'frac%'")
type3_char = cur.fetchone()[0]
print(f"Тип 3b: char(92)+'frac' (backslash через char): {type3_char} задач")

# Тип 4: '\\\\frac' (двойной слэш в БД = экранированный)
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE task_text LIKE '%\\\\frac%'")
type4 = cur.fetchone()[0]
print(f"Тип 4: '\\\\\\\\frac' (двойной backslash в БД): {type4} задач")

# Проверяем через Python bytes
print("\n--- Проверка через Python bytes ---")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE '% rac{%' LIMIT 3")
for row in cur.fetchall():
    task_id, text = row
    idx = text.find(' rac{')
    if idx >= 0:
        snippet = text[max(0,idx-3):idx+10]
        print(f"  ID={task_id}: {repr(snippet)} | bytes: {snippet.encode('utf-8')}")

# Проверяем задачи с одинарным backslash перед frac
print("\n--- Задачи с одинарным \\ перед frac ---")
cur.execute("SELECT id, task_text FROM adaptive_tasks WHERE task_text LIKE '%' || char(92) || 'frac%' LIMIT 5")
for row in cur.fetchall():
    task_id, text = row
    # Найти позицию
    bs = chr(92)  # backslash
    idx = text.find(bs + 'frac')
    if idx >= 0:
        snippet = text[max(0,idx-3):idx+10]
        print(f"  ID={task_id}: {repr(snippet)} | bytes: {snippet.encode('utf-8')}")

# Итог: что нужно починить
print("\n" + "=" * 70)
print("ИТОГ: ЧТО НУЖНО ПОЧИНИТЬ")
print("=" * 70)
print(f"  ' rac{{' → '\\\\frac{{': {type1} задач")
print(f"  '\\x0crac{{' → '\\\\frac{{': {type2} задач")
print(f"  Правильных '\\\\frac': {type3_char} задач")

conn.close()
