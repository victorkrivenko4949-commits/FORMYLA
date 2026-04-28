# -*- coding: utf-8 -*-
# Проверка конкретных задач для уточнения паттернов
import sqlite3

con = sqlite3.connect('instance/formyla.db')

# Проверяем задачи с BARE_SQRT_FRAC и DOUBLE_DOLLAR_BROKEN
for task_id in [110, 113, 114, 591, 1]:
    row = con.execute("SELECT id, task_text FROM adaptive_tasks WHERE id=?", (task_id,)).fetchone()
    if row:
        text = row[1] or ''
        print(f"\n{'='*60}")
        print(f"ID: {task_id}")
        print(f"Длина: {len(text)}")
        print(f"Содержит \\\\n (литерал): {'YES' if '\\\\n' in repr(text) else 'NO'}")
        print(f"repr первые 500 символов:")
        print(repr(text[:500]))
        print(f"\nТекст первые 500 символов:")
        print(text[:500])

con.close()
