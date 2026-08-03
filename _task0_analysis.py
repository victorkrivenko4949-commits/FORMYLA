"""Deep analysis: bank levels before/after migration, matching with adaptive_tasks."""
import sqlite3, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB = 'formyla.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

def header(s):
    print(f"\n{'='*60}\n{s}\n{'='*60}")

# =========================================================
# 1. grade_tasks vs adaptive_tasks linkage via source_id
# =========================================================
header("1. Linkage: grade_tasks.source_id <-> adaptive_tasks.source_id")

# Count matches
rows = conn.execute("""
    SELECT count(*) as cnt
    FROM grade_tasks g
    JOIN adaptive_tasks a ON g.source_id = a.source_id
""").fetchone()
print(f"grade_tasks matched to adaptive_tasks via source_id: {rows['cnt']}")

rows = conn.execute("""
    SELECT count(*) as cnt
    FROM grade_tasks
    WHERE source_id NOT IN (SELECT source_id FROM adaptive_tasks WHERE source_id IS NOT NULL)
""").fetchone()
print(f"grade_tasks NOT matched to adaptive_tasks: {rows['cnt']}")

# =========================================================
# 2. grade_tasks source_id patterns - what levels exist in source_id?
# =========================================================
header("2. grade_tasks source_id patterns and level distribution")

rows = conn.execute("""
    SELECT level, grade, count(*) cnt
    FROM grade_tasks
    GROUP BY level, grade
    ORDER BY level, grade
""").fetchall()
print("grade_tasks: level × grade distribution:")
for r in rows:
    print(f"  level={r['level']} grade={r['grade']} cnt={r['cnt']}")

# source_id format
rows = conn.execute("""
    SELECT source_id, level, grade, substr(statement,1,80) stmt
    FROM grade_tasks
    ORDER BY level, grade
    LIMIT 3
""").fetchall()
print("\nsample source_ids:")
for r in rows:
    print(f"  source_id={r['source_id']} level={r['level']} grade={r['grade']} stmt={r['stmt']}")

# =========================================================
# 3. How are bank tasks actually served? Look at task_solutions linkage
# =========================================================
header("3. task_solutions: what task_id references")

rows = conn.execute("""
    SELECT count(*), count(DISTINCT task_id)
    FROM task_solutions
""").fetchone()
print(f"task_solutions: {rows[0]} rows, {rows[1]} distinct task_ids")

# Check if task_id in task_solutions matches adaptive_tasks.id or grade_tasks.id
rows = conn.execute("""
    SELECT count(*) cnt FROM task_solutions s
    JOIN adaptive_tasks a ON s.task_id = a.id
""").fetchone()
print(f"task_solutions.task_id matches adaptive_tasks.id: {rows['cnt']}")

rows = conn.execute("""
    SELECT count(*) cnt FROM task_solutions s
    JOIN grade_tasks g ON s.task_id = g.id
""").fetchone()
print(f"task_solutions.task_id matches grade_tasks.id: {rows['cnt']}")

# =========================================================
# 4. grade_tasks: what WAS the original bank structure?
# Check if there are any clues in the data about levels 6,7
# =========================================================
header("4. Checking for traces of old levels 6,7 in grade_tasks")

# Check status field
rows = conn.execute("""
    SELECT status, count(*) cnt FROM grade_tasks GROUP BY status
""").fetchall()
print("grade_tasks by status:")
for r in rows:
    print(f"  status={r['status']} cnt={r['cnt']}")

# Check source_id for level info embedded
rows = conn.execute("""
    SELECT source_id, level, grade, status
    FROM grade_tasks
    WHERE source_id LIKE '%L6%' OR source_id LIKE '%L7%' OR source_id LIKE '%level6%' OR source_id LIKE '%level7%'
    LIMIT 10
""").fetchall()
print(f"\ngrade_tasks with L6/L7 in source_id: {len(rows)}")
for r in rows:
    print(f"  {r['source_id']} level={r['level']} grade={r['grade']} status={r['status']}")

# Also check if any grade_tasks have level>5
rows = conn.execute("SELECT count(*) FROM grade_tasks WHERE level > 5").fetchone()
print(f"\ngrade_tasks with level > 5: {rows[0]}")

# =========================================================
# 5. Adaptive tasks: analyze what the src levels mean
# =========================================================
header("5. adaptive_tasks: avg solution length by src level")

rows = conn.execute("""
    SELECT difficulty_level_src src,
           count(*) cnt,
           avg(length(solution)) avg_sol,
           avg(length(task_text)) avg_text,
           avg(length(correct_answer)) avg_ans,
           avg(class_level) avg_class
    FROM adaptive_tasks
    WHERE solution IS NOT NULL
    GROUP BY src
    ORDER BY src
""").fetchall()
print("By src (original) level:")
for r in rows:
    print(f"  src={r['src']} cnt={r['cnt']} avg_sol={r['avg_sol']:.0f} avg_text={r['avg_text']:.0f} avg_ans={r['avg_ans']:.0f} avg_class={r['avg_class']:.1f}")

# =========================================================
# 6. For grade_tasks, join with adaptive_tasks and compare levels
# =========================================================
header("6. grade_tasks joined to adaptive_tasks: level comparison")

rows = conn.execute("""
    SELECT g.level as bank_level,
           a.difficulty_level as adapt_level,
           a.difficulty_level_src as adapt_src,
           count(*) cnt,
           avg(length(g.solution)) avg_bank_sol,
           avg(length(a.solution)) avg_adapt_sol
    FROM grade_tasks g
    JOIN adaptive_tasks a ON g.source_id = a.source_id
    WHERE g.solution IS NOT NULL AND a.solution IS NOT NULL
    GROUP BY g.level, a.difficulty_level, a.difficulty_level_src
    ORDER BY g.level, a.difficulty_level
""").fetchall()
print("Bank level -> Adaptive level mapping (via source_id):")
for r in rows:
    print(f"  bank_lvl={r['bank_level']} -> adapt_lvl={r['adapt_level']} (src={r['adapt_src']}) cnt={r['cnt']} avg_bank_sol={r['avg_bank_sol']:.0f} avg_adapt_sol={r['avg_adapt_sol']:.0f}")

# =========================================================
# 7. Distribution of adaptive_tasks by (difficulty_level, class_level)  
# =========================================================
header("7. adaptive_tasks: difficulty_level × class_level distribution")

rows = conn.execute("""
    SELECT difficulty_level, class_level, count(*) cnt
    FROM adaptive_tasks
    GROUP BY difficulty_level, class_level
    ORDER BY difficulty_level, class_level
""").fetchall()
print("adaptive_tasks: level × class:")
for r in rows:
    print(f"  lvl={r['difficulty_level']} class={r['class_level']} cnt={r['cnt']}")

# =========================================================
# 8. What tasks are actually served? Look at adaptive_test_problems
# =========================================================
header("8. adaptive_test_problems: what tasks are served to students?")

cols = conn.execute("PRAGMA table_info(adaptive_test_problems)").fetchall()
print("adaptive_test_problems structure:")
for c in cols:
    print(f"  {c[1]:30s} {c[2]}")

rows = conn.execute("SELECT count(*) FROM adaptive_test_problems").fetchone()
print(f"total rows: {rows[0]}")

# Check what task_ids are in adaptive_test_problems
rows = conn.execute("""
    SELECT count(DISTINCT task_id) FROM adaptive_test_problems
""").fetchone()
print(f"distinct task_ids: {rows[0]}")

# Join to understand level distribution of served tasks
rows = conn.execute("""
    SELECT a.difficulty_level, a.class_level, count(*) cnt
    FROM adaptive_test_problems p
    JOIN adaptive_tasks a ON p.task_id = a.id
    GROUP BY a.difficulty_level, a.class_level
    ORDER BY a.difficulty_level, a.class_level
""").fetchall()
print("\nServed tasks by difficulty_level × class_level:")
if rows:
    for r in rows:
        print(f"  lvl={r['difficulty_level']} class={r['class_level']} cnt={r['cnt']}")
else:
    print("  (no data)")

# =========================================================
# 9. How grade_tasks are used in adaptive_test_problems
# =========================================================
header("9. grade_tasks reach to students: how?")

# Check if prep_plans or prep_days link to grade_tasks
for tbl in ['prep_plans','prep_days','user_progress','adaptive_test_results','test_results_detail']:
    cols = conn.execute(f"PRAGMA table_info({tbl})").fetchall()
    has_task = any('task' in (c[1] or '').lower() or 'problem' in (c[1] or '').lower() for c in cols)
    cnt = conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
    print(f"{tbl}: {cnt} rows, task-related columns: {has_task}")
    if has_task:
        for c in cols:
            print(f"  {c[1]:30s} {c[2]}")

# =========================================================
# 10. Check actual_solve_rate to understand task difficulty
# =========================================================
header("10. adaptive_tasks: actual_solve_rate by difficulty_level")

rows = conn.execute("""
    SELECT difficulty_level,
           count(*) cnt,
           avg(actual_solve_rate) avg_rate,
           avg(attempts_count) avg_attempts,
           avg(solves_count) avg_solves
    FROM adaptive_tasks
    WHERE actual_solve_rate IS NOT NULL
    GROUP BY difficulty_level
    ORDER BY difficulty_level
""").fetchall()
print("Solve rates by current level:")
for r in rows:
    print(f"  lvl={r['difficulty_level']} cnt={r['cnt']} avg_solve_rate={r['avg_rate']:.3f} avg_attempts={r['avg_attempts']:.1f} avg_solves={r['avg_solves']:.1f}")

# Same by src level
rows = conn.execute("""
    SELECT difficulty_level_src src,
           count(*) cnt,
           avg(actual_solve_rate) avg_rate,
           avg(attempts_count) avg_attempts,
           avg(solves_count) avg_solves
    FROM adaptive_tasks
    WHERE actual_solve_rate IS NOT NULL
    GROUP BY src
    ORDER BY src
""").fetchall()
print("\nSolve rates by src (original) level:")
for r in rows:
    print(f"  src={r['src']} cnt={r['cnt']} avg_solve_rate={r['avg_rate']:.3f} avg_attempts={r['avg_attempts']:.1f} avg_solves={r['avg_solves']:.1f}")

conn.close()
print("\nDone.")
