# -*- coding: utf-8 -*-
"""
PRIMENENIE REKALIBRATSII 7 KLASSA — VARIANT B
- MOVE_GRADE: 603 zadachi -> 8/9/10 klass (quality >= 0.5)
- RECALIB_DIFF: 631 zadach (VSE audited, quality >= 0.5)
- FLAG: 2 zadachi s quality < 0.5 -> needs_reclassification=1
- Vse v odnoy tranzaktsii (BEGIN -> COMMIT ili ROLLBACK)

Zapuskat': python scripts/apply_grade7_recalibration_v2.py
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
MIN_QUALITY = 0.5

def main():
    # ============================================================
    # SHAG 0: SVEZHY BEKAP
    # ============================================================
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'formyla_before_apply_recalib_{stamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    backup_size = os.path.getsize(backup_path) / 1024 / 1024
    print(f"[BACKUP] {backup_path} ({backup_size:.1f} MB)")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Nachalo tranzaktsii
        conn.execute("BEGIN TRANSACTION")
        print("[TX] BEGIN TRANSACTION")

        # ============================================================
        # SHAG 1: Sokhranit' original_grade i original_difficulty
        # dlya VSEKH 993 audited zadach (esli eshche ne zapolneno)
        # ============================================================
        cur = conn.execute("""
            UPDATE adaptive_tasks
            SET original_grade = class_level,
                original_difficulty = difficulty_level
            WHERE class_level = 7
              AND llm_audited_at IS NOT NULL
              AND original_grade IS NULL
        """)
        step1_count = cur.rowcount
        print(f"[SHAG 1] Sokhraneno original_grade/difficulty: {step1_count} zadach")

        # Proverka
        cur2 = conn.execute("""
            SELECT COUNT(*) FROM adaptive_tasks
            WHERE original_grade = 7
        """)
        orig_count = cur2.fetchone()[0]
        print(f"[CHECK]  original_grade=7: {orig_count} zadach")

        # ============================================================
        # SHAG 2: MOVE_GRADE
        # UPDATE class_level = llm_suggested_grade
        # dlya zadach gde llm_suggested_grade != 7 i quality >= 0.5
        # ============================================================
        cur = conn.execute("""
            UPDATE adaptive_tasks
            SET class_level = llm_suggested_grade
            WHERE class_level = 7
              AND llm_audited_at IS NOT NULL
              AND llm_suggested_grade != 7
              AND llm_quality_score >= ?
        """, (MIN_QUALITY,))
        step2_count = cur.rowcount
        print(f"[SHAG 2] MOVE_GRADE: {step2_count} zadach pereneseno")

        # ============================================================
        # SHAG 3: RECALIB_DIFF — VARIANT B
        # UPDATE difficulty_level = llm_suggested_difficulty
        # dlya VSEKH audited zadach (original_grade=7) s quality >= 0.5
        # ============================================================
        cur = conn.execute("""
            UPDATE adaptive_tasks
            SET difficulty_level = llm_suggested_difficulty
            WHERE original_grade = 7
              AND llm_audited_at IS NOT NULL
              AND llm_quality_score >= ?
        """, (MIN_QUALITY,))
        step3_count = cur.rowcount
        print(f"[SHAG 3] RECALIB_DIFF (Variant B): {step3_count} zadach obnovleno")

        # ============================================================
        # SHAG 4: FLAG LOW_QUALITY
        # needs_reclassification = 1 dlya zadach s quality < 0.5
        # ============================================================
        cur = conn.execute("""
            UPDATE adaptive_tasks
            SET needs_reclassification = 1
            WHERE original_grade = 7
              AND llm_audited_at IS NOT NULL
              AND llm_quality_score < ?
        """, (MIN_QUALITY,))
        step4_count = cur.rowcount
        print(f"[SHAG 4] FLAG LOW_QUALITY: {step4_count} zadach pomecheno")

        # ============================================================
        # COMMIT
        # ============================================================
        conn.execute("COMMIT")
        print("[TX] COMMIT — vse izmeneniya primeneny")

        # ============================================================
        # SANITY CHECKS
        # ============================================================
        print("\n" + "=" * 60)
        print("SANITY CHECKS")
        print("=" * 60)

        # Check 1: original_grade=7
        cur = conn.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade=7")
        c = cur.fetchone()[0]
        status = "OK" if c == orig_count else f"PROBLEM! Ozhidali {orig_count}"
        print(f"  original_grade=7: {c} ({status})")

        # Check 2: Raspredelenie class_level posle
        print("\n  Raspredelenie class_level (original_grade=7):")
        cur = conn.execute("""
            SELECT class_level, COUNT(*) as cnt
            FROM adaptive_tasks WHERE original_grade=7
            GROUP BY class_level ORDER BY class_level
        """)
        for r in cur.fetchall():
            print(f"    class_level={r[0]}: {r[1]} zadach")

        # Check 3: Raspredelenie difficulty dlya grade=7
        print("\n  Raspredelenie difficulty_level (class_level=7 posle):")
        cur = conn.execute("""
            SELECT difficulty_level, COUNT(*) as cnt
            FROM adaptive_tasks WHERE class_level=7
            GROUP BY difficulty_level ORDER BY difficulty_level
        """)
        for r in cur.fetchall():
            print(f"    difficulty={r[0]}: {r[1]} zadach")

        # Check 4: Obshchee kolichestvo zadach 7 klassa
        cur = conn.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7")
        grade7_total = cur.fetchone()[0]
        print(f"\n  Vsego zadach 7 klassa posle: {grade7_total}")

        # ============================================================
        # SOZDAEM SQL DLYA OTKATA
        # ============================================================
        rollback_sql = f"""-- ROLLBACK: Otkat rekalibratsii 7 klassa
-- Sozdan: {datetime.datetime.now().isoformat()}
-- Bekap: {backup_path}

BEGIN TRANSACTION;

-- Vosstanovit' class_level iz original_grade
UPDATE adaptive_tasks
SET class_level = original_grade
WHERE original_grade = 7
  AND original_grade IS NOT NULL;

-- Vosstanovit' difficulty_level iz original_difficulty
UPDATE adaptive_tasks
SET difficulty_level = original_difficulty
WHERE original_grade = 7
  AND original_difficulty IS NOT NULL;

-- Snyat' flag needs_reclassification
UPDATE adaptive_tasks
SET needs_reclassification = 0
WHERE original_grade = 7
  AND needs_reclassification = 1;

-- Proverka
SELECT class_level, COUNT(*) FROM adaptive_tasks
WHERE original_grade = 7
GROUP BY class_level;

COMMIT;

-- Posle otkata: SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7;
-- Dolzhno byt' ~993 (vse original grade=7 zadachi)
"""
        rollback_path = 'scripts/rollback_grade7_recalibration.sql'
        with open(rollback_path, 'w', encoding='utf-8') as f:
            f.write(rollback_sql)
        print(f"\n  SQL dlya otkata: {rollback_path}")

        print("\n" + "=" * 60)
        print("PRIMENENIE ZAVERSHENO USPESHNO")
        print(f"  Bekap: {backup_path}")
        print(f"  Otkat: python -c \"import sqlite3; conn=sqlite3.connect('instance/formyla.db'); conn.executescript(open('scripts/rollback_grade7_recalibration.sql').read())\"")
        print("=" * 60)

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n[ERROR] {e}")
        print("[TX] ROLLBACK — vse izmeneniya otmeneny")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
