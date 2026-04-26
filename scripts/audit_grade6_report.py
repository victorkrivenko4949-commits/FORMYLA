# -*- coding: utf-8 -*-
"""
Otchet po rezul'tatam LLM-audita zadach 6 klassa
Zapuskat': python scripts/audit_grade6_report.py
"""
import sqlite3, sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
TARGET_CLASS = 6
conn = sqlite3.connect(DB_PATH)

def run(sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    headers = [d[0] for d in cur.description]
    return rows, headers

def print_table(rows, headers, max_col=40):
    if not rows:
        print("  (net dannykh)")
        return
    widths = []
    for i, h in enumerate(headers):
        col_vals = [str(r[i]) if r[i] is not None else "NULL" for r in rows]
        widths.append(min(max_col, max(len(str(h)), max((len(v) for v in col_vals), default=0))))
    fmt = "  " + "  ".join("{{:<{}}}".format(w) for w in widths)
    print(fmt.format(*[str(h)[:max_col] for h in headers]))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(x)[:max_col] if x is not None else "NULL" for x in row]))

def sep(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

# Progress
sep(f"PROGRESS AUDITA (class_level={TARGET_CLASS})")
rows, _ = run(f"""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN llm_audited_at IS NOT NULL THEN 1 ELSE 0 END) as audited,
           SUM(CASE WHEN llm_audited_at IS NULL THEN 1 ELSE 0 END) as remaining
    FROM adaptive_tasks WHERE class_level={TARGET_CLASS}
""")
r = rows[0]
total, audited, remaining = r
pct = round(100.0 * audited / total, 1) if total > 0 else 0
print(f"  Vsego zadach {TARGET_CLASS} klassa: {total}")
print(f"  Audited: {audited} ({pct}%)")
print(f"  Ostalos': {remaining}")

if audited == 0:
    print(f"\n  [!] Audit eshche ne zapuskalsa.")
    conn.close()
    sys.exit(0)

# 1. Grade distribution
sep(f"1. RASPREDELENIE LLM_SUGGESTED_GRADE")
rows, hdrs = run(f"""
    SELECT llm_suggested_grade as grade, COUNT(*) as cnt,
           ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM adaptive_tasks WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL),1) as pct
    FROM adaptive_tasks WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL
    GROUP BY llm_suggested_grade ORDER BY llm_suggested_grade
""")
print_table(rows, hdrs)

rows6, _ = run(f"""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL AND llm_suggested_grade={TARGET_CLASS}
""")
print(f"\n  Real'no dlya {TARGET_CLASS} klassa: {rows6[0][0]} iz {audited} ({round(100.0*rows6[0][0]/audited,1)}%)")

# 2. Difficulty distribution
sep("2. RASPREDELENIE LLM_SUGGESTED_DIFFICULTY (novaya shkala 1-5)")
rows, hdrs = run(f"""
    SELECT llm_suggested_difficulty as diff, COUNT(*) as cnt,
           ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM adaptive_tasks WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL),1) as pct,
           ROUND(AVG(llm_quality_score),3) as avg_quality
    FROM adaptive_tasks WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL
    GROUP BY llm_suggested_difficulty ORDER BY llm_suggested_difficulty
""")
print_table(rows, hdrs)

# 3. Quality distribution
sep("3. RASPREDELENIE QUALITY_SCORE")
rows, hdrs = run(f"""
    SELECT CASE
        WHEN llm_quality_score >= 0.8 THEN '0.8-1.0 (otlichnye)'
        WHEN llm_quality_score >= 0.6 THEN '0.6-0.8 (khoroshie)'
        WHEN llm_quality_score >= 0.4 THEN '0.4-0.6 (srednie)'
        WHEN llm_quality_score >= 0.2 THEN '0.2-0.4 (plokhie)'
        ELSE '0.0-0.2 (bitye)'
    END as quality_range,
    COUNT(*) as cnt,
    ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM adaptive_tasks WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL),1) as pct
    FROM adaptive_tasks WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL
    GROUP BY quality_range ORDER BY quality_range DESC
""")
print_table(rows, hdrs)

# 4. Low quality candidates
sep("4. TOP-20 ZADACH S QUALITY_SCORE < 0.5 (kandidaty na proverku)")
rows, hdrs = run(f"""
    SELECT id, topic, difficulty_level as orig_diff,
           llm_suggested_grade as llm_grade, llm_suggested_difficulty as llm_diff,
           ROUND(llm_quality_score,2) as quality,
           SUBSTR(llm_rationale,1,60) as rationale,
           SUBSTR(task_text,1,60) as preview
    FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL AND llm_quality_score < 0.5
    ORDER BY llm_quality_score ASC LIMIT 20
""")
print_table(rows, hdrs)

# 5. Tasks not for grade 6
sep(f"5. ZADACHI NE DLYA {TARGET_CLASS} KLASSA PO MNENIYU LLM")
rows, hdrs = run(f"""
    SELECT llm_suggested_grade as llm_grade, COUNT(*) as cnt,
           SUBSTR(GROUP_CONCAT(DISTINCT topic),1,60) as topics
    FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL AND llm_suggested_grade != {TARGET_CLASS}
    GROUP BY llm_suggested_grade ORDER BY llm_suggested_grade
""")
print_table(rows, hdrs)

# 6. Summary
sep("6. ITOG: REKOMENDATSII")
rows_keep, _ = run(f"""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade={TARGET_CLASS} AND llm_quality_score >= 0.5
""")
rows_move, _ = run(f"""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL AND llm_suggested_grade != {TARGET_CLASS}
""")
rows_low_q, _ = run(f"""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL AND llm_quality_score < 0.5
""")
rows_recalib, _ = run(f"""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level={TARGET_CLASS} AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade={TARGET_CLASS} AND llm_quality_score >= 0.5
      AND ABS(difficulty_level - llm_suggested_difficulty) >= 2
""")

print(f"  KEEP (ostavit' kak est'):             {rows_keep[0][0]}")
print(f"  MOVE_GRADE (perenit' v drugoy klass): {rows_move[0][0]}")
print(f"  LOW_QUALITY (quality < 0.5):          {rows_low_q[0][0]}")
print(f"  RECALIBRATE (diff raznitsa >= 2):     {rows_recalib[0][0]}")

# Grade 7 check
rows_g7, _ = run("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7 AND llm_audited_at IS NOT NULL")
print(f"\n  PROVERKA: Grade 7 audited = {rows_g7[0][0]} (dolzhno byt' 390, ne menyalos')")

conn.close()
print("\n" + "=" * 70)
print("OTCHET ZAVERSHEN")
print("=" * 70)
