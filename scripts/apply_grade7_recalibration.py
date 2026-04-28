# -*- coding: utf-8 -*-
"""
Primenenie rezul'tatov LLM-audita k adaptive_tasks
ZAPUSKAT' TOL'KO POSLE ODOBRENIYA VIKTORA!

Chto delaet:
1. Sokhranit original_grade i original_difficulty
2. Obnovit class_level = llm_suggested_grade (dlya zadach ne 7 klassa)
3. Obnovit difficulty_level = llm_suggested_difficulty (dlya vsekh)
4. Pomechaet zadachi s quality < 0.3 flagom is_flagged=1

NICHEGO NE UDALYAET. Tol'ko UPDATE + flag.
Otkaty vozmozhny cherez original_* kolonki.

Zapuskat': python scripts/apply_grade7_recalibration.py
"""
import sqlite3
import shutil
import datetime
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
BACKUP_DIR = 'backups'

# ============================================================
# PARAMETRY (mozhno menyat' pered zapuskom)
# ============================================================
# Minimal'nyy quality_score dlya primeneniya izmeneniy
MIN_QUALITY_FOR_APPLY = 0.4

# Porog quality dlya flagirovaniya kak "bitaya"
FLAG_QUALITY_THRESHOLD = 0.3

# Primenenie izmeneniy po klassu (True = menyaem class_level)
APPLY_GRADE_CHANGES = True

# Primenenie izmeneniy po slozhnosti (True = menyaem difficulty_level)
APPLY_DIFFICULTY_CHANGES = True

# DRY RUN - esli True, tol'ko pokazyvaet chto budet sdelano, ne menyaet BD
DRY_RUN = True  # IZMENI NA False DLYA REAL'NOGO PRIMENENIYA!

# ============================================================

def main():
    if DRY_RUN:
        print("=" * 70)
        print("!!! DRY RUN MODE - BD NE MENYAETSYA !!!")
        print("Chtoby primenit' izmeneniya: ustanovi DRY_RUN = False")
        print("=" * 70)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Proverka chto audit zavershen
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7 AND llm_audited_at IS NULL")
    not_audited = cur.fetchone()[0]
    if not_audited > 0:
        print(f"[WARNING] {not_audited} zadach eshche ne audited!")
        print("Zapustite audit_grade7_llm.py do kontsa pered primeneniem.")
        if not DRY_RUN:
            ans = input("Prodolzhat' vse ravno? (yes/no): ")
            if ans.lower() != 'yes':
                conn.close()
                return
    
    # Statistika pered primeneniem
    print("\n[STATISTIKA PERED PRIMENENIEM]")
    
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN llm_suggested_grade != 7 THEN 1 ELSE 0 END) as move_grade,
            SUM(CASE WHEN llm_suggested_grade = 7 AND ABS(difficulty_level - llm_suggested_difficulty) >= 1 THEN 1 ELSE 0 END) as recalib_diff,
            SUM(CASE WHEN llm_quality_score < ? THEN 1 ELSE 0 END) as low_quality,
            SUM(CASE WHEN llm_quality_score < ? THEN 1 ELSE 0 END) as flag_quality
        FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL AND llm_quality_score >= ?
    """, (MIN_QUALITY_FOR_APPLY, FLAG_QUALITY_THRESHOLD, MIN_QUALITY_FOR_APPLY))
    # Pereschitatem pravilno
    
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL
    """)
    total_audited = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL 
          AND llm_suggested_grade != 7
          AND llm_quality_score >= ?
    """, (MIN_QUALITY_FOR_APPLY,))
    move_grade_cnt = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL 
          AND llm_suggested_grade = 7
          AND ABS(difficulty_level - llm_suggested_difficulty) >= 1
          AND llm_quality_score >= ?
    """, (MIN_QUALITY_FOR_APPLY,))
    recalib_diff_cnt = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL 
          AND llm_quality_score < ?
    """, (FLAG_QUALITY_THRESHOLD,))
    flag_cnt = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL 
          AND llm_suggested_grade = 7
          AND ABS(difficulty_level - llm_suggested_difficulty) = 0
          AND llm_quality_score >= ?
    """, (MIN_QUALITY_FOR_APPLY,))
    keep_cnt = cur.fetchone()[0]
    
    print(f"  Vsego audited:              {total_audited}")
    print(f"  MOVE_GRADE (-> drugoy klass): {move_grade_cnt}")
    print(f"  RECALIB_DIFF (menyaem diff):  {recalib_diff_cnt}")
    print(f"  FLAG_LOW_QUALITY (<{FLAG_QUALITY_THRESHOLD}):      {flag_cnt}")
    print(f"  KEEP (bez izmeneniy):         {keep_cnt}")
    
    # Raspredelenie po novym klassam
    print("\n  Kuda ukhodyat zadachi (MOVE_GRADE):")
    cur.execute("""
        SELECT llm_suggested_grade, COUNT(*) as cnt
        FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NOT NULL 
          AND llm_suggested_grade != 7
          AND llm_quality_score >= ?
        GROUP BY llm_suggested_grade ORDER BY llm_suggested_grade
    """, (MIN_QUALITY_FOR_APPLY,))
    for r in cur.fetchall():
        print(f"    -> Grade {r[0]}: {r[1]} zadach")
    
    if DRY_RUN:
        print("\n[DRY RUN] Izmeneniya ne primeneny.")
        print("Ustanovi DRY_RUN = False i zapusti snova dlya real'nogo primeneniya.")
        conn.close()
        return
    
    # REAL'NOE PRIMENENIE
    # Backup
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'formyla_before_apply_recalib_{stamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    print(f"\n[BACKUP] {backup_path}")
    
    # 1. Sokhranit originaly
    print("\n[STEP 1] Sokhranenie original_grade i original_difficulty...")
    cur.execute("""
        UPDATE adaptive_tasks 
        SET original_grade = class_level,
            original_difficulty = difficulty_level
        WHERE class_level=7 AND llm_audited_at IS NOT NULL
          AND original_grade IS NULL
    """)
    print(f"  Sokhraneno: {cur.rowcount} zadach")
    
    # 2. Primenenie grade changes
    if APPLY_GRADE_CHANGES:
        print("\n[STEP 2] Primenenie MOVE_GRADE...")
        cur.execute("""
            UPDATE adaptive_tasks
            SET class_level = llm_suggested_grade
            WHERE class_level=7 AND llm_audited_at IS NOT NULL
              AND llm_suggested_grade != 7
              AND llm_quality_score >= ?
        """, (MIN_QUALITY_FOR_APPLY,))
        print(f"  Pereneseno v drugoy klass: {cur.rowcount} zadach")
    
    # 3. Primenenie difficulty changes (tol'ko dlya zadach kotorye ostalis' v 7 klasse)
    if APPLY_DIFFICULTY_CHANGES:
        print("\n[STEP 3] Primenenie RECALIB_DIFF...")
        cur.execute("""
            UPDATE adaptive_tasks
            SET difficulty_level = llm_suggested_difficulty
            WHERE class_level=7 AND llm_audited_at IS NOT NULL
              AND llm_quality_score >= ?
        """, (MIN_QUALITY_FOR_APPLY,))
        print(f"  Perekalibrovano difficulty: {cur.rowcount} zadach")
    
    # 4. Flagirovanie nizkokachestvennykh
    print("\n[STEP 4] Flagirovanie LOW_QUALITY zadach...")
    cur.execute("""
        UPDATE adaptive_tasks
        SET is_flagged = 1,
            flagged_reason = 'LLM audit: low quality score ' || ROUND(llm_quality_score, 2)
        WHERE class_level=7 AND llm_audited_at IS NOT NULL
          AND llm_quality_score < ?
          AND is_flagged = 0
    """, (FLAG_QUALITY_THRESHOLD,))
    print(f"  Pomecheno flagom: {cur.rowcount} zadach")
    
    conn.commit()
    
    # Itog
    print("\n[ITOG]")
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7")
    new_total = cur.fetchone()[0]
    print(f"  Zadach 7 klassa posle primeneniya: {new_total}")
    
    cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks WHERE original_grade=7 GROUP BY class_level ORDER BY class_level")
    print("  Raspredelenie zadach (original grade=7) po novym klassam:")
    for r in cur.fetchall():
        print(f"    Class {r[0]}: {r[1]}")
    
    conn.close()
    print(f"\n[DONE] Primenenie zaversheno. Backup: {backup_path}")
    print("Dlya otkata: python scripts/rollback_grade7_recalibration.py")


if __name__ == '__main__':
    main()
