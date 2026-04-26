# -*- coding: utf-8 -*-
import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('instance/formyla.db')

# Ispravit' anomalii difficulty > 5 dlya original_grade=6
conn.execute('BEGIN')
cur = conn.execute('UPDATE adaptive_tasks SET difficulty_level=5 WHERE original_grade=6 AND difficulty_level > 5')
fixed = cur.rowcount
conn.execute('COMMIT')
print(f"Ispravleno anomaliy difficulty > 5: {fixed}")

# Final check
cur = conn.cursor()
cur.execute('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks WHERE class_level=6 GROUP BY difficulty_level ORDER BY difficulty_level')
print('\nDifficulty grade=6 posle ispravleniya:')
total = 0
for r in cur.fetchall():
    print(f'  diff={r[0]}: {r[1]}')
    total += r[1]
print(f'  TOTAL: {total}')

cur.execute('SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=6')
print(f'Vsego grade=6: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade=6')
print(f'original_grade=6: {cur.fetchone()[0]}')

cur.execute('SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade=7')
print(f'original_grade=7: {cur.fetchone()[0]} (dolzhno byt 993)')

conn.close()
print('DONE')
