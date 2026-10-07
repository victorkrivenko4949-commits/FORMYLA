"""Исследование структуры банка задач и уровней."""
import sqlite3, json, sys, io

DB = 'formyla.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
OUT = sys.stdout

def header(s):
    OUT.write(f"\n{'='*60}\n{s}\n{'='*60}\n")

# 1. Распределение difficulty_level в adaptive_tasks
header("adaptive_tasks: difficulty_level distribution")
rows = conn.execute("""
    SELECT difficulty_level, difficulty_level_src, count(*) cnt
    FROM adaptive_tasks
    GROUP BY difficulty_level, difficulty_level_src
    ORDER BY difficulty_level, difficulty_level_src
""").fetchall()
for r in rows:
    OUT.write(f"  level={r['difficulty_level']} src={r['difficulty_level_src']} count={r['cnt']}\n")

# 2. class_level distribution
header("adaptive_tasks: class_level distribution")
rows = conn.execute("""
    SELECT class_level, count(*) cnt
    FROM adaptive_tasks GROUP BY class_level ORDER BY class_level
""").fetchall()
for r in rows:
    OUT.write(f"  class={r['class_level']} count={r['cnt']}\n")

# 3. grade_tasks distribution
header("grade_tasks: grade + level distribution")
rows = conn.execute("""
    SELECT grade, level, count(*) cnt
    FROM grade_tasks GROUP BY grade, level ORDER BY grade, level
""").fetchall()
for r in rows:
    OUT.write(f"  grade={r['grade']} level={r['level']} count={r['cnt']}\n")

# 4. task_solutions structure
header("task_solutions structure")
cols = conn.execute("PRAGMA table_info(task_solutions)").fetchall()
for c in cols:
    OUT.write(f"  {c[1]:30s} {c[2]}\n")
rows = conn.execute("SELECT count(*) FROM task_solutions").fetchone()
OUT.write(f"  total rows: {rows[0]}\n")

# 5. method_tasks structure
header("method_tasks structure")
cols = conn.execute("PRAGMA table_info(method_tasks)").fetchall()
for c in cols:
    OUT.write(f"  {c[1]:30s} {c[2]}\n")

# 6. Check for solution length / steps data
header("adaptive_tasks: solution length stats by difficulty_level")
rows = conn.execute("""
    SELECT difficulty_level,
           count(*) cnt,
           avg(length(solution)) avg_sol_len,
           avg(length(task_text)) avg_text_len,
           avg(length(correct_answer)) avg_ans_len
    FROM adaptive_tasks
    WHERE solution IS NOT NULL AND solution != ''
    GROUP BY difficulty_level
    ORDER BY difficulty_level
""").fetchall()
for r in rows:
    OUT.write(f"  level={r['difficulty_level']} cnt={r['cnt']} avg_sol_len={r['avg_sol_len']:.0f} avg_text_len={r['avg_text_len']:.0f} avg_ans_len={r['avg_ans_len']:.0f}\n")

# 7. grade_tasks: solution length by level
header("grade_tasks: solution length stats by level")
rows = conn.execute("""
    SELECT level,
           count(*) cnt,
           avg(length(solution)) avg_sol_len,
           avg(length(statement)) avg_stmt_len
    FROM grade_tasks
    WHERE solution IS NOT NULL AND solution != ''
    GROUP BY level
    ORDER BY level
""").fetchall()
for r in rows:
    OUT.write(f"  level={r['level']} cnt={r['cnt']} avg_sol_len={r['avg_sol_len']:.0f} avg_stmt_len={r['avg_stmt_len']:.0f}\n")

# 8. Look at migration files
header("Searching for migration/level-shift patterns in adaptive_tasks")
# Check if there's a v8 migration - look at difficulty_level_src vs difficulty_level
rows = conn.execute("""
    SELECT difficulty_level, difficulty_level_src, count(*) cnt
    FROM adaptive_tasks
    WHERE difficulty_level != difficulty_level_src
    GROUP BY difficulty_level, difficulty_level_src
    ORDER BY difficulty_level
""").fetchall()
OUT.write("Rows where difficulty_level != difficulty_level_src:\n")
if rows:
    for r in rows:
        OUT.write(f"  cur={r['difficulty_level']} src={r['difficulty_level_src']} cnt={r['cnt']}\n")
else:
    OUT.write("  (none)\n")

# 9. Look at the actual content for each level - 5 examples
header("5 examples from each difficulty_level in adaptive_tasks")
for lvl in range(1, 9):
    rows = conn.execute("""
        SELECT id, class_level, difficulty_level, difficulty_level_src,
               substr(task_text, 1, 120) as task_preview,
               length(solution) sol_len, length(task_text) text_len,
               topic, subtopic
        FROM adaptive_tasks
        WHERE difficulty_level = ?
        ORDER BY id
        LIMIT 5
    """, [lvl]).fetchall()
    OUT.write(f"\n--- Level {lvl} ---\n")
    if not rows:
        OUT.write("  (no tasks)\n")
    for r in rows:
        OUT.write(f"  id={r['id']} class={r['class_level']} src_lvl={r['difficulty_level_src']} "
                  f"topic={r['topic']} subtopic={r['subtopic']} "
                  f"sol_len={r['sol_len']} text_len={r['text_len']}\n")
        OUT.write(f"    text: {r['task_preview']}\n")

# 10. grade_tasks samples
header("5 examples from each level in grade_tasks")
for lvl in range(1, 8):
    rows = conn.execute("""
        SELECT id, grade, level, substr(statement, 1, 120) stmt_preview,
               length(solution) sol_len, length(statement) stmt_len, topic
        FROM grade_tasks
        WHERE level = ?
        ORDER BY id
        LIMIT 5
    """, [lvl]).fetchall()
    OUT.write(f"\n--- Level {lvl} ---\n")
    if not rows:
        OUT.write("  (no tasks)\n")
    for r in rows:
        OUT.write(f"  id={r['id']} grade={r['grade']} topic={r['topic']} "
                  f"sol_len={r['sol_len']} stmt_len={r['stmt_len']}\n")
        OUT.write(f"    stmt: {r['stmt_preview']}\n")

conn.close()
OUT.write("\nDone.\n")
