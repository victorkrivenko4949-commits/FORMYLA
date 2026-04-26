#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Починка битого LaTeX в БД:
- '$ rac{' → '$\\frac{' (пробел+rac → backslash+frac)
- Также проверяем solution и correct_answer

ТОЛЬКО ЧИТАЕТ — не меняет БД до подтверждения.
Запусти с аргументом --apply для применения.
"""
import sys
import io
import sqlite3
import shutil
import os
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

APPLY = '--apply' in sys.argv
DB_PATH = "instance/formyla.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print(f"ПОЧИНКА БИТОГО LaTeX {'(DRY RUN)' if not APPLY else '(ПРИМЕНЯЕМ)'}")
print("=" * 70)

# Ищем все варианты битого LaTeX
# Паттерн: пробел перед rac{ (без backslash)
broken_patterns = [
    (' rac{', '\\frac{'),   # $ rac{ → $\frac{
    (' rac ', '\\frac '),   # $ rac  → $\frac (без скобки)
]

# Находим все задачи с битым LaTeX
cur.execute("SELECT id, task_text, solution FROM adaptive_tasks WHERE task_text LIKE '% rac%' OR solution LIKE '% rac%'")
rows = cur.fetchall()

print(f"\nНайдено задач с ' rac': {len(rows)}")
print()

fixes = []
for row in rows:
    task_id = row['id']
    task_text = row['task_text'] or ''
    solution = row['solution'] or ''
    
    new_task_text = task_text
    new_solution = solution
    
    for broken, fixed in broken_patterns:
        new_task_text = new_task_text.replace(broken, fixed)
        new_solution = new_solution.replace(broken, fixed)
    
    if new_task_text != task_text or new_solution != solution:
        fixes.append((task_id, new_task_text, new_solution, task_text, solution))
        print(f"ID={task_id}:")
        if new_task_text != task_text:
            # Показываем что изменилось
            idx = task_text.find(' rac')
            if idx >= 0:
                old_snippet = task_text[max(0,idx-5):idx+15]
                new_snippet = new_task_text[max(0,idx-5):idx+15]
                print(f"  task_text: {repr(old_snippet)} → {repr(new_snippet)}")
        if new_solution != solution:
            idx = solution.find(' rac')
            if idx >= 0:
                old_snippet = solution[max(0,idx-5):idx+15]
                new_snippet = new_solution[max(0,idx-5):idx+15]
                print(f"  solution:  {repr(old_snippet)} → {repr(new_snippet)}")

print(f"\nИтого задач для починки: {len(fixes)}")

if APPLY and fixes:
    # Backup
    BACKUP_DIR = "backups"
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{BACKUP_DIR}/formyla_before_fix_rac_{ts}.db"
    conn.close()
    shutil.copy2(DB_PATH, backup_path)
    print(f"\n✅ Backup: {backup_path}")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    for task_id, new_task_text, new_solution, _, _ in fixes:
        cur.execute("""
            UPDATE adaptive_tasks 
            SET task_text=?, solution=?
            WHERE id=?
        """, (new_task_text, new_solution, task_id))
    
    conn.commit()
    print(f"✅ Починено {len(fixes)} задач")
elif not APPLY:
    print("\nЗапусти с --apply для применения изменений")

conn.close()
print("=" * 70)
