# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')
cur = conn.cursor()

# Naydti zadachi s difficulty > 5 sredi original_grade=7
cur.execute('SELECT id, topic, difficulty_level, llm_suggested_difficulty, llm_quality_score FROM adaptive_tasks WHERE original_grade=7 AND difficulty_level > 5')
rows = cur.fetchall()
print(f'Zadachi s difficulty > 5: {len(rows)}')
for r in rows:
    print(f'  ID={r[0]} | diff={r[2]} | llm_diff={r[3]} | q={r[4]} | {r[1]}')

# Ispravit'
if rows:
    conn.execute('BEGIN')
    conn.execute('UPDATE adaptive_tasks SET difficulty_level=5 WHERE original_grade=7 AND difficulty_level > 5')
    conn.execute('COMMIT')
    print('Ispravleno: difficulty > 5 -> 5')

# Final distribution grade=7
cur.execute('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks WHERE class_level=7 GROUP BY difficulty_level ORDER BY difficulty_level')
print('\nFinal difficulty (class_level=7):')
total = 0
for r in cur.fetchall():
    print(f'  diff={r[0]}: {r[1]}')
    total += r[1]
print(f'  TOTAL: {total}')

# Final distribution by class
cur.execute('SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE original_grade=7 GROUP BY class_level ORDER BY class_level')
print('\nFinal class distribution (original_grade=7):')
for r in cur.fetchall():
    print(f'  class={r[0]}: {r[1]}')

conn.close()
print('\nDONE')
