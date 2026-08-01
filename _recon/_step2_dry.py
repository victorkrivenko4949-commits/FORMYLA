import sqlite3, sys, os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = sqlite3.connect(os.path.join(BASE, 'instance', 'formyla.db'))
cur = db.cursor()

print('=== CURRENT DISTRIBUTION (1..8) ===')
cur.execute('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level ORDER BY difficulty_level')
rows = cur.fetchall()
total = sum(r[1] for r in rows)
print(f'Total tasks: {total}')
for lvl, cnt in rows:
    pct = cnt / total * 100
    print(f'  Level {lvl}: {cnt:>6} ({pct:.1f}%)')

print()
print('=== AFTER REMAPPING (1->1, 2->1, 3->2, 4->3, 5->3, 6->4, 7->4, 8->5) ===')
mapping = {1:1, 2:1, 3:2, 4:3, 5:3, 6:4, 7:4, 8:5}
new_dist = {}
for lvl, cnt in rows:
    nl = mapping[lvl]
    new_dist[nl] = new_dist.get(nl, 0) + cnt

for nl in sorted(new_dist):
    cnt = new_dist[nl]
    pct = cnt / total * 100
    print(f'  Level {nl}: {cnt:>6} ({pct:.1f}%)')

print()
max_pct = max(new_dist.values()) / total * 100
min_pct = min(new_dist.values()) / total * 100
print(f'Max level share: {max_pct:.1f}%')
print(f'Min level share: {min_pct:.1f}%')
if max_pct > 45:
    print('STOP: max share > 45%!', file=sys.stderr)
elif min_pct < 5:
    print('WARNING: min share < 5%!', file=sys.stderr)
else:
    print('OK: distribution within bounds')

print()
print('=== AFTER REMAP: grade x level distribution ===')
cur.execute('SELECT class_level, difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level, difficulty_level ORDER BY class_level, difficulty_level')
rows2 = cur.fetchall()
after = {}
for grade, lvl, cnt in rows2:
    nl = mapping.get(lvl, lvl)
    key = (grade, nl)
    after[key] = after.get(key, 0) + cnt

for grade in sorted(set(k[0] for k in after)):
    parts = []
    for nl in range(1, 6):
        cnt = after.get((grade, nl), 0)
        parts.append(f'L{nl}={cnt}')
    print(f'  Grade {grade}: ' + ', '.join(parts))

# Empty cells
print()
print('=== EMPTY CELLS (grade x level) ===')
empty = []
for grade in range(5, 12):
    for nl in range(1, 6):
        if after.get((grade, nl), 0) == 0:
            empty.append(f'  G{grade} L{nl}')
if empty:
    print('\n'.join(empty))
else:
    print('  NONE')

# Count 6,7,8 tasks
cur.execute('SELECT COUNT(*) FROM adaptive_tasks WHERE difficulty_level > 5')
high = cur.fetchone()[0]
print(f'\nTasks with level > 5: {high} ({high/total*100:.1f}%)')

db.close()
