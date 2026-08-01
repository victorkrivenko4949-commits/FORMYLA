import sqlite3, os
from collections import defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(os.path.join(BASE, 'instance', 'formyla.db'))
cur = con.cursor()
CANONICAL = ('algebra','geometry','combinatorics','logic','number_theory')

cur.execute("""
    SELECT class_level, subject, difficulty_level, COUNT(*)
    FROM adaptive_tasks
    WHERE correct_answer IS NOT NULL AND correct_answer != ''
      AND task_text IS NOT NULL AND task_text != ''
      AND (source IS NULL OR source != 'formyla_anchors')
    GROUP BY class_level, subject, difficulty_level
    ORDER BY class_level, subject, difficulty_level
""")
rows = cur.fetchall()

cells = defaultdict(int)
for cls, subj, lvl, cnt in rows:
    sec = subj if subj in CANONICAL else 'other'
    lvl = lvl or 1
    cells[(cls, sec, lvl)] += cnt

classes = sorted(set(c[0] for c in cells))
print('Classes in pool:', classes)
print()

all_cells = []
for cls in classes:
    for sec in CANONICAL:
        for lvl in range(1, 6):
            n = cells.get((cls, sec, lvl), 0)
            all_cells.append((cls, sec, lvl, n))

all_cells.sort(key=lambda x: x[3])

print('TOP 15 MOST DEFICIT CELLS:')
for i, (cls, sec, lvl, n) in enumerate(all_cells[:15], 1):
    print(f'  {i:2d}. G{cls} {sec:15s} L{lvl} pool={n:4d}')

print()
print('SPOT CHECK G6 L4 and G10 L5:')
for cls, sec, lvl, n in all_cells:
    if (cls == 6 and lvl == 4) or (cls == 10 and lvl == 5):
        print(f'  G{cls} {sec} L{lvl} pool={n}')

print()
cur.execute('SELECT COUNT(*) FROM task_assignment_history')
print(f'History total: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(DISTINCT user_id), COUNT(DISTINCT task_id) FROM task_assignment_history')
r = cur.fetchone()
print(f'Distinct users: {r[0]}, Distinct tasks: {r[1]}')

con.close()
