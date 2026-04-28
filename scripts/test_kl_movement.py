# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

tests = [
    (7, ['логика и инварианты', 'комбинаторика'], 'kl_movement grade=7'),
    (6, ['инвариант', 'четность', 'логика', 'рыцари', 'лжец', 'разрезани', 'граф'], 'kl_movement grade=6'),
    (5, ['текстовые задачи', 'совместная работа', 'логика', 'рыцари', 'инвариант', 'четность'], 'kl_movement grade=5'),
    (7, ['алгебраические тождества', 'преобразовани', 'линейные уравнения', 'системы', 'функции', 'графики'], 'algebra grade=7'),
    (7, ['начала геометрии', 'треугольник', 'геометрические доказательства'], 'geometry grade=7'),
    (7, ['теория чисел', 'неравенства'], 'number_theory grade=7'),
]

for grade, keywords, label in tests:
    cur.execute('SELECT id, topic, difficulty_level FROM adaptive_tasks WHERE class_level=? AND is_flagged=0', (grade,))
    filtered = []
    for row in cur.fetchall():
        topic_lower = row[1].lower()
        if any(kw.lower() in topic_lower for kw in keywords):
            filtered.append(row)
    status = 'OK' if len(filtered) >= 10 else f'FAIL (only {len(filtered)})'
    print(f'{label}: {len(filtered)} tasks [{status}]')
    if filtered:
        print(f'  Sample: [{filtered[0][1]}]')

conn.close()
print('DONE')
