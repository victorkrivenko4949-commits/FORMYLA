# -*- coding: utf-8 -*-
"""
Dry run analiz pered primeneniem izmeneniy
python scripts/dry_run_analysis.py
"""
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
MIN_QUALITY = 0.5  # Filtr kachestva

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

def run(sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()

def sep(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

# ============================================================
# 1. TOCHNYY PLAN
# ============================================================
sep("1. TOCHNYY PLAN IZMENENIY")

# 1a. Skol'ko UPDATE budet vypolneno
rows = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade != 7
      AND llm_quality_score >= ?
""", (MIN_QUALITY,))
move_grade_count = rows[0][0]

rows = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade = 7
      AND ABS(difficulty_level - llm_suggested_difficulty) >= 1
      AND llm_quality_score >= ?
""", (MIN_QUALITY,))
recalib_diff_count = rows[0][0]

rows = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_quality_score < ?
""", (MIN_QUALITY,))
low_quality_count = rows[0][0]

rows = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade = 7
      AND llm_quality_score >= ?
""", (MIN_QUALITY,))
keep_count = rows[0][0]

print(f"\n  Filtr kachestva: llm_quality_score >= {MIN_QUALITY}")
print(f"\n  MOVE_GRADE (UPDATE class_level):     {move_grade_count} zadach")
print(f"  RECALIB_DIFF (UPDATE difficulty):    {recalib_diff_count} zadach")
print(f"  LOW_QUALITY (tol'ko flag, ne menyaem): {low_quality_count} zadach")
print(f"  KEEP (bez izmeneniy):                {keep_count} zadach")
print(f"  VSEGO audited:                       {move_grade_count + recalib_diff_count + low_quality_count + keep_count}")

# 1b. Raspredelenie MOVE_GRADE po klassam
print("\n  Raspredelenie MOVE_GRADE po novym klassam:")
rows = run("""
    SELECT llm_suggested_grade, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade != 7
      AND llm_quality_score >= ?
    GROUP BY llm_suggested_grade ORDER BY llm_suggested_grade
""", (MIN_QUALITY,))
for r in rows:
    print(f"    -> Grade {r[0]}: {r[1]} zadach")

# 1c. Pervye 20 SQL statements
print("\n  Pervye 20 SQL statements (MOVE_GRADE):")
rows = run("""
    SELECT id, class_level, llm_suggested_grade, difficulty_level, llm_suggested_difficulty,
           ROUND(llm_quality_score, 2) as q, SUBSTR(topic, 1, 30) as topic
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade != 7
      AND llm_quality_score >= ?
    ORDER BY llm_suggested_grade, id
    LIMIT 20
""", (MIN_QUALITY,))
for i, r in enumerate(rows, 1):
    print(f"    {i:2d}. UPDATE adaptive_tasks SET class_level={r['llm_suggested_grade']}, "
          f"original_grade=7 WHERE id={r['id']};  -- {r['topic']} q={r['q']}")

# ============================================================
# 2. BACKUP INFO
# ============================================================
sep("2. BACKUP I ORIGINAL_* KOLONKI")

import os
backup_dir = 'backups'
backups = [f for f in os.listdir(backup_dir) if 'g7' in f or 'recalib' in f]
print(f"\n  Sushchestvuyushchie bekapi:")
for b in sorted(backups):
    size = os.path.getsize(os.path.join(backup_dir, b)) / 1024 / 1024
    print(f"    {b} ({size:.1f} MB)")

rows = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND original_grade IS NOT NULL
""")
print(f"\n  Zadach s uzhe zapolnennym original_grade: {rows[0][0]}")
print(f"  Novyy bekap budet sozdan pered primeneniem.")
print(f"  original_grade = 7 (tekushchiy class_level)")
print(f"  original_difficulty = tekushchiy difficulty_level")

# ============================================================
# 3. SAMYE RISKOVANNYE PERENOSY
# ============================================================
sep("3a. TOP-10 ZADACH GDE RAZNITSA KLASSA >= 3")
rows = run("""
    SELECT id, class_level, llm_suggested_grade,
           (llm_suggested_grade - class_level) as grade_delta,
           difficulty_level, llm_suggested_difficulty,
           ROUND(llm_quality_score, 2) as q,
           SUBSTR(llm_rationale, 1, 80) as rationale,
           SUBSTR(task_text, 1, 100) as preview
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND ABS(llm_suggested_grade - class_level) >= 3
      AND llm_quality_score >= ?
    ORDER BY ABS(llm_suggested_grade - class_level) DESC
    LIMIT 10
""", (MIN_QUALITY,))
for r in rows:
    print(f"\n  ID={r['id']} | {r['class_level']} -> {r['llm_suggested_grade']} (delta={r['grade_delta']:+d}) | q={r['q']}")
    print(f"  Rationale: {r['rationale']}")
    print(f"  Task: {r['preview']}")

sep("3b. TOP-10 POGRANICHNYKH ZADACH (quality 0.5-0.7)")
rows = run("""
    SELECT id, class_level, llm_suggested_grade, difficulty_level, llm_suggested_difficulty,
           ROUND(llm_quality_score, 2) as q,
           SUBSTR(llm_rationale, 1, 80) as rationale,
           SUBSTR(task_text, 1, 100) as preview
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_quality_score >= 0.5 AND llm_quality_score < 0.7
    ORDER BY llm_quality_score ASC
    LIMIT 10
""")
for r in rows:
    action = f"MOVE to {r['llm_suggested_grade']}" if r['llm_suggested_grade'] != 7 else "KEEP grade=7"
    print(f"\n  ID={r['id']} | q={r['q']} | {action} | diff {r['difficulty_level']}->{r['llm_suggested_difficulty']}")
    print(f"  Rationale: {r['rationale']}")
    print(f"  Task: {r['preview']}")

# ============================================================
# 4. FILTRY PRIMENENIYA
# ============================================================
sep("4. FILTRY PRIMENENIYA")
print(f"""
  PRAVILO 1: llm_quality_score >= {MIN_QUALITY}
    -> Primenenie MOVE_GRADE i RECALIB_DIFF
    -> Zadach pod eto pravilo: {move_grade_count + recalib_diff_count}

  PRAVILO 2: llm_quality_score < {MIN_QUALITY}
    -> Tol'ko flag needs_manual_review = 1
    -> class_level i difficulty_level NE menyaetsya
    -> Zadach pod eto pravilo: {low_quality_count}

  Eto pravilo UCHTENО v skripte apply_grade7_recalibration.py:
    MIN_QUALITY_FOR_APPLY = {MIN_QUALITY}  # uzhe ustanovleno
""")

# ============================================================
# 5. CHTO BUDET SDELANO POMIMO MOVE_GRADE
# ============================================================
sep("5. POLNYY PLAN DEYSTVIY")

rows_diff_grade7 = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade = 7
      AND ABS(difficulty_level - llm_suggested_difficulty) >= 1
      AND llm_quality_score >= ?
""", (MIN_QUALITY,))

rows_diff_all = run("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND ABS(difficulty_level - llm_suggested_difficulty) >= 1
      AND llm_quality_score >= ?
""", (MIN_QUALITY,))

print(f"""
  SHAG 1: Sokhranit' original_grade i original_difficulty
    -> Dlya vsekh 993 audited zadach
    -> Tol'ko esli original_grade IS NULL (ne perezapisyvat')

  SHAG 2: MOVE_GRADE (UPDATE class_level)
    -> Tol'ko zadachi gde llm_suggested_grade != 7
    -> Tol'ko esli llm_quality_score >= {MIN_QUALITY}
    -> Kolichestvo: {move_grade_count} zadach

  SHAG 3: RECALIB_DIFF (UPDATE difficulty_level)
    -> VARIANT A: Tol'ko dlya zadach kotorye OSTALIS' v grade=7
      Kolichestvo: {rows_diff_grade7[0][0]} zadach
    -> VARIANT B: Dlya VSEKH zadach (vklyuchaya perenesennye)
      Kolichestvo: {rows_diff_all[0][0]} zadach
    -> REKOMENDATSIYA: Variant A (ne menyaem difficulty u perenesennykh)

  SHAG 4: FLAG LOW_QUALITY
    -> SET needs_reclassification = 1 (uzhe est' v skheme)
    -> Dlya zadach s quality < {MIN_QUALITY}
    -> Kolichestvo: {low_quality_count} zadach

  SHAG 5: Bekap pered primeneniem
    -> backups/formyla_before_apply_recalib_TIMESTAMP.db

  ITOG POSLE PRIMENENIYA:
    Zadach 7 klassa: ~{keep_count} (vmesto 995)
    Zadach 8 klassa: +{rows[0][1] if rows else 0} (iz 7 klassa)
    Zadach 9 klassa: +{rows[1][1] if len(rows) > 1 else 0} (iz 7 klassa)
    Zadach 10 klassa: +{rows[2][1] if len(rows) > 2 else 0} (iz 7 klassa)
""")

# Raspredelenie po klassam dlya MOVE_GRADE
rows_dist = run("""
    SELECT llm_suggested_grade, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level=7 AND llm_audited_at IS NOT NULL
      AND llm_suggested_grade != 7
      AND llm_quality_score >= ?
    GROUP BY llm_suggested_grade ORDER BY llm_suggested_grade
""", (MIN_QUALITY,))
print("  Raspredelenie MOVE_GRADE:")
for r in rows_dist:
    print(f"    Grade {r[0]}: +{r[1]} zadach")

conn.close()
print("\n" + "=" * 70)
print("DRY RUN ZAVERSHEN. Zhdu resheniya: go / no-go / utochneniya.")
print("=" * 70)
