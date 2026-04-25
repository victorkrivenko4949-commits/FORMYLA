# -*- coding: utf-8 -*-
"""
Otchet po rezul'tatam LLM-audita zadach 7 klassa
Zapuskat': python scripts/audit_grade7_report.py
"""
import sqlite3
import sys
import io
import json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
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
sep("PROGRESS AUDITA")
rows, _ = run("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN llm_audited_at IS NOT NULL THEN 1 ELSE 0 END) as audited,
        SUM(CASE WHEN llm_audited_at IS NULL THEN 1 ELSE 0 END) as remaining
    FROM adaptive_tasks WHERE class_level=7
""")
r = rows[0]
total, audited, remaining = r
pct = round(100.0 * audited / total, 1) if total > 0 else 0
print(f"  Vsego zadach 7 klassa: {total}")
print(f"  Audited: {audited} ({pct}%)")
print(f"  Ostalos': {remaining}")

if audited == 0:
    print("\n  [!] Audit eshche ne zapuskalsa. Zapustite audit_grade7_llm.py")
    conn.close()
    sys.exit(0)

# 1. Raspredelenie llm_suggested_grade
sep("1. RASPREDELENIE LLM_SUGGESTED_GRADE (kuda zadacha real'no podkhodit)")
rows, hdrs = run("""
    SELECT 
        llm_suggested_grade as grade,
        COUNT(*) as cnt,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM adaptive_tasks 
              WHERE class_level=7 AND llm_audited_at IS NOT NULL), 1) as pct
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
    GROUP BY llm_suggested_grade
    ORDER BY llm_suggested_grade
""")
print_table(rows, hdrs)

# Skol'ko real'no dlya 7 klassa
rows7, _ = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_suggested_grade=7
""")
print(f"\n  Real'no dlya 7 klassa: {rows7[0][0]} iz {audited} ({round(100.0*rows7[0][0]/audited,1)}%)")

# 2. Raspredelenie llm_suggested_difficulty
sep("2. RASPREDELENIE LLM_SUGGESTED_DIFFICULTY (novaya shkala 1-5)")
rows, hdrs = run("""
    SELECT 
        llm_suggested_difficulty as diff,
        COUNT(*) as cnt,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM adaptive_tasks 
              WHERE class_level=7 AND llm_audited_at IS NOT NULL), 1) as pct,
        ROUND(AVG(llm_quality_score), 3) as avg_quality
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
    GROUP BY llm_suggested_difficulty
    ORDER BY llm_suggested_difficulty
""")
print_table(rows, hdrs)

# 3. Raspredelenie quality_score
sep("3. RASPREDELENIE QUALITY_SCORE")
rows, hdrs = run("""
    SELECT 
        CASE 
            WHEN llm_quality_score >= 0.8 THEN '0.8-1.0 (otlichnye)'
            WHEN llm_quality_score >= 0.6 THEN '0.6-0.8 (khoroshie)'
            WHEN llm_quality_score >= 0.4 THEN '0.4-0.6 (srednie)'
            WHEN llm_quality_score >= 0.2 THEN '0.2-0.4 (plokhie)'
            ELSE '0.0-0.2 (bitye)'
        END as quality_range,
        COUNT(*) as cnt,
        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM adaptive_tasks 
              WHERE class_level=7 AND llm_audited_at IS NOT NULL), 1) as pct
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
    GROUP BY quality_range
    ORDER BY quality_range DESC
""")
print_table(rows, hdrs)

# 4. Top-20 zadach s quality_score < 0.3 (kandidaty na udalenie)
sep("4. TOP-20 ZADACH S QUALITY_SCORE < 0.3 (kandidaty na udalenie)")
rows, hdrs = run("""
    SELECT 
        id, topic, difficulty_level as orig_diff,
        llm_suggested_grade as llm_grade,
        llm_suggested_difficulty as llm_diff,
        ROUND(llm_quality_score, 2) as quality,
        SUBSTR(llm_rationale, 1, 60) as rationale,
        SUBSTR(task_text, 1, 70) as preview
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_quality_score < 0.3
    ORDER BY llm_quality_score ASC
    LIMIT 20
""")
print_table(rows, hdrs)

# 5. Primery gde LLM sil'no ne soglasen s tekushchim reyting
sep("5. SIL'NAYA RASKHOZHDENIE: orig_diff vs llm_diff (raznitsa >= 2)")
rows, hdrs = run("""
    SELECT 
        id, topic,
        difficulty_level as orig_diff,
        llm_suggested_grade as llm_grade,
        llm_suggested_difficulty as llm_diff,
        (difficulty_level - llm_suggested_difficulty) as diff_delta,
        ROUND(llm_quality_score, 2) as quality,
        SUBSTR(llm_rationale, 1, 80) as rationale
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND ABS(difficulty_level - llm_suggested_difficulty) >= 2
    ORDER BY ABS(difficulty_level - llm_suggested_difficulty) DESC
    LIMIT 20
""")
print_table(rows, hdrs)

# 6. Zadachi ne dlya 7 klassa (llm_suggested_grade != 7)
sep("6. ZADACHI NE DLYA 7 KLASSA PO MNENIYU LLM")
rows, hdrs = run("""
    SELECT 
        llm_suggested_grade as llm_grade,
        COUNT(*) as cnt,
        GROUP_CONCAT(DISTINCT topic) as topics
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_suggested_grade != 7
    GROUP BY llm_suggested_grade
    ORDER BY llm_suggested_grade
""")
print_table(rows, hdrs)

# 7. Primery zadach ne dlya 7 klassa
sep("7. PRIMERY ZADACH NE DLYA 7 KLASSA (po 3 na kazhdyy grade)")
for grade in [5, 6, 8, 9, 10, 11]:
    rows, _ = run("""
        SELECT id, topic, difficulty_level as orig_diff, llm_suggested_grade as llm_grade,
               llm_suggested_difficulty as llm_diff, ROUND(llm_quality_score,2) as q,
               SUBSTR(llm_rationale, 1, 80) as rationale,
               SUBSTR(task_text, 1, 80) as preview
        FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_suggested_grade=?
        ORDER BY RANDOM() LIMIT 3
    """, (grade,))
    if rows:
        print(f"\n  --- LLM schitaet eto {grade} klass ---")
        for r in rows:
            print(f"    ID={r[0]} | {r[1]} | orig_diff={r[2]} | llm_diff={r[4]} | q={r[5]}")
            print(f"    Rationale: {r[6]}")
            print(f"    Task: {r[7]}")

# 8. Itog: rekomendatsii
sep("8. ITOG: REKOMENDATSII")
rows_keep, _ = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL 
      AND llm_suggested_grade=7 AND llm_quality_score >= 0.5
""")
rows_move, _ = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_suggested_grade != 7
""")
rows_low_q, _ = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_quality_score < 0.3
""")
rows_recalib, _ = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL 
      AND llm_suggested_grade=7 AND llm_quality_score >= 0.5
      AND ABS(difficulty_level - llm_suggested_difficulty) >= 2
""")

print(f"  KEEP (ostavit' kak est'):          {rows_keep[0][0]}")
print(f"  MOVE_GRADE (perenit' v drugoy klass): {rows_move[0][0]}")
print(f"  LOW_QUALITY (kandidaty na udalenie):  {rows_low_q[0][0]}")
print(f"  RECALIBRATE (pomenyt' difficulty):    {rows_recalib[0][0]}")

conn.close()
print("\n" + "=" * 70)
print("OTCHET ZAVERSHEN")
print("=" * 70)
