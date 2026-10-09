import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import sqlite3
conn = sqlite3.connect('instance/formyla.db')
c = conn.cursor()
for grade in [8, 10, 11]:
    print(f'=== GRADE {grade} ===')
    rows = c.execute('''SELECT v.method_code, (SELECT COUNT(*) FROM method_tasks WHERE method_tasks.method_code = v.method_code AND method_tasks.grade = v.grade) as cnt FROM vsosh_course_entries v WHERE grade=? ORDER BY v.method_code''', (grade,)).fetchall()
    total = len(rows)
    done = sum(1 for r in rows if r[1] >= 25)
    for r in rows:
        m = 'OK' if r[1] >= 25 else '..'
        print(f'  {m} {r[0]} G{grade}: {r[1]}/25')
    print(f'  -> {done}/{total} combos complete')
    print()
conn.close()
