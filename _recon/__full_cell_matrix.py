"""Full cell matrix: grade 5..11 x section x level 1..5 with task counts."""
import sqlite3
import os

base = r"c:\Users\Redmi\Desktop\Новая папка (2)"
db_path = os.path.join(base, 'formyla.db')
CANONICAL = ('algebra','geometry','combinatorics','logic','number_theory')

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Get raw counts grouped by class_level, subject, difficulty_level
cur.execute("""
    SELECT class_level, subject, difficulty_level, COUNT(*)
    FROM adaptive_tasks
    WHERE correct_answer IS NOT NULL AND correct_answer != ''
      AND task_text IS NOT NULL AND task_text != ''
    GROUP BY class_level, subject, difficulty_level
    ORDER BY class_level, subject, difficulty_level
""")
rows = cur.fetchall()

# Build complete matrix
from collections import defaultdict
cells = defaultdict(int)
for cls, subj, lvl, cnt in rows:
    sec = subj if subj in CANONICAL else 'other'
    lvl = lvl or 1
    cells[(cls, sec, lvl)] += cnt

print("FULL CELL MATRIX: grade 5..11 x section x level 1..5")
print("=" * 90)
print(f"{'Grade':>5} | {'Section':<16} | {'L1':>5} | {'L2':>5} | {'L3':>5} | {'L4':>5} | {'L5':>5} | TOTAL")
print("-" * 90)

all_zero = []
for cls in range(5, 12):
    for sec in CANONICAL:
        nums = [cells.get((cls, sec, l), 0) for l in range(1, 6)]
        total = sum(nums)
        print(f"{cls:>5} | {sec:<16} | {nums[0]:>5} | {nums[1]:>5} | {nums[2]:>5} | {nums[3]:>5} | {nums[4]:>5} | {total:>5}")
        for l in range(1, 6):
            if cells.get((cls, sec, l), 0) == 0:
                all_zero.append((cls, sec, l))

print("\n" + "=" * 90)
print(f"ALL CELLS WITH ZERO TASKS ({len(all_zero)}):")
for cls, sec, lvl in sorted(all_zero):
    print(f"  G{cls} {sec} L{lvl}")

# Also check without the filter (all tasks, even empty answer/text)
cur.execute("""
    SELECT class_level, subject, difficulty_level, COUNT(*)
    FROM adaptive_tasks
    GROUP BY class_level, subject, difficulty_level
    ORDER BY class_level, subject, difficulty_level
""")
rows_all = cur.fetchall()
cells_all = defaultdict(int)
for cls, subj, lvl, cnt in rows_all:
    sec = subj if subj in CANONICAL else 'other'
    lvl = lvl or 1
    cells_all[(cls, sec, lvl)] += cnt

all_zero_all = []
for cls in range(5, 12):
    for sec in CANONICAL:
        for lvl in range(1, 6):
            if cells_all.get((cls, sec, lvl), 0) == 0:
                all_zero_all.append((cls, sec, lvl))

print(f"\nUNFILTERED ZERO CELLS ({len(all_zero_all)}):")
for cls, sec, lvl in sorted(all_zero_all):
    print(f"  G{cls} {sec} L{lvl}")

print(f"\nTotal tasks in DB: {cur.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()[0]}")

# Now check what filters were used in cell_report.py:
# Only WHERE: correct_answer IS NOT NULL AND correct_answer != '' AND task_text IS NOT NULL AND task_text != ''
# AND (source IS NULL OR source != 'formyla_anchors') 
# Let's replicate
cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE correct_answer IS NOT NULL AND correct_answer != ''
      AND task_text IS NOT NULL AND task_text != ''
      AND (source IS NULL OR source != 'formyla_anchors')
""")
n_filtered = cur.fetchone()[0]
print(f"Tasks matching cell_report.py filter: {n_filtered}")

conn.close()
