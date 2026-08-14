# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime

db = sqlite3.connect('instance/formyla.db')

j = db.execute('SELECT id, started_at, finished_at FROM daily_generation_jobs ORDER BY id DESC LIMIT 1').fetchone()
start = datetime.fromisoformat(j[1])
end = datetime.fromisoformat(j[2])
delta = end - start
secs = int(delta.total_seconds())

items = db.execute('''
    SELECT dti.position, dti.status, dti.task_text, dti.correct_answer, dti.difficulty_level
    FROM daily_task_items dti
    JOIN daily_task_sets dts ON dti.daily_set_id = dts.id
    WHERE dts.id = (SELECT daily_set_id FROM daily_generation_jobs WHERE id=?)
    ORDER BY dti.position
''', (j[0],)).fetchall()

print(f'=== Задачи дня (Job #{j[0]}) ===')
print(f'Начало: {j[1]}')
print(f'Конец:  {j[2]}')
print(f'Время генерации: {secs} сек ({secs//60} мин {secs%60} сек)')
print()

for pos, st, txt, ans, lvl in items:
    print(f'--- Задача {pos} (уровень L{lvl}, статус: {st}) ---')
    if txt:
        print(txt)
    print(f'Ответ: {ans}')
    print()

db.close()
