# -*- coding: utf-8 -*-
"""
PRIMENENIE REKALIBRATSII 6 KLASSA
- MOVE_GRADE: 68 zadach -> 5/7/8/9 klass (quality >= 0.5)
- RECALIB_DIFF: VSE audited zadachi 6 klassa (quality >= 0.5)
- FLAG: zadachi s quality < 0.5 -> needs_reclassification=1
- Vse v odnoy tranzaktsii

Zapuskat': python scripts/apply_grade6_recalibration.py
"""
import sqlite3, shutil, datetime, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'
BACKUP_DIR = 'backups'
MIN_QUALITY = 0.5
TARGET_CLASS = 6

def main():
    # SHAG 0: SVEZHY BEKAP
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'formyla_before_apply_recalib_grade6_{stamp}.db')
    shutil.copy2(DB_PATH, backup_path)
    backup_size = os.path.getsize(backup_path) / 1024 / 1024
    print(f"[BACKUP] {backup_path} ({backup_size:.1f} MB)")

    conn = sqlite3.connect(DB_PATH)

    # Proverka chto grade 7 ne budet tronuto
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7 AND llm_audited_at IS NOT NULL")
    grade7_before = cur.fetchone()[0]
    print(f"[CHECK] Grade 7 audited before: {grade7_before} (ne dolzhno menyat'sya)")

    try:
        conn.execute("BEGIN TRANSACTION")
        print("[TX] BEGIN TRANSACTION")

        # SHAG 1: Sokhranit' original_grade i original_difficulty
        # TOCHNO dlya class_level=6, original_grade IS NULL
        cur = conn.execute(f"""
            UPDATE adaptive_tasks
            SET original_grade = class_level,
                original_difficulty = difficulty_level
            WHERE class_level = {TARGET_CLASS}
              AND llm_audited_at IS NOT NULL
              AND original_grade IS NULL
        """)
        step1_count = cur.rowcount
        print(f"[SHAG 1] Sokhraneno original_grade/difficulty: {step1_count} zadach")

        # Proverka
        cur2 = conn.execute(f"SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade = {TARGET_CLASS}")
        orig_count = cur2.fetchone()[0]
        print(f"[CHECK]  original_grade={TARGET_CLASS}: {orig_count} zadach")

        # SHAG 2: MOVE_GRADE
        cur = conn.execute(f"""
            UPDATE adaptive_tasks
            SET class_level = llm_suggested_grade
            WHERE class_level = {TARGET_CLASS}
              AND llm_audited_at IS NOT NULL
              AND llm_suggested_grade != {TARGET_CLASS}
              AND llm_quality_score >= ?
        """, (MIN_QUALITY,))
        step2_count = cur.rowcount
        print(f"[SHAG 2] MOVE_GRADE: {step2_count} zadach pereneseno")

        # SHAG 3: RECALIB_DIFF (dlya VSEKH original_grade=6 s quality >= 0.5)
        cur = conn.execute(f"""
            UPDATE adaptive_tasks
            SET difficulty_level = llm_suggested_difficulty
            WHERE original_grade = {TARGET_CLASS}
              AND llm_audited_at IS NOT NULL
              AND llm_quality_score >= ?
        """, (MIN_QUALITY,))
        step3_count = cur.rowcount
        print(f"[SHAG 3] RECALIB_DIFF: {step3_count} zadach obnovleno")

        # SHAG 4: FLAG LOW_QUALITY
        cur = conn.execute(f"""
            UPDATE adaptive_tasks
            SET needs_reclassification = 1
            WHERE original_grade = {TARGET_CLASS}
              AND llm_audited_at IS NOT NULL
              AND llm_quality_score < ?
        """, (MIN_QUALITY,))
        step4_count = cur.rowcount
        print(f"[SHAG 4] FLAG LOW_QUALITY: {step4_count} zadach pomecheno")

        conn.execute("COMMIT")
        print("[TX] COMMIT")

        # SANITY CHECKS
        print("\n" + "=" * 60)
        print("SANITY CHECKS")
        print("=" * 60)

        # original_grade=6
        cur = conn.execute(f"SELECT COUNT(*) FROM adaptive_tasks WHERE original_grade={TARGET_CLASS}")
        c = cur.fetchone()[0]
        print(f"  original_grade={TARGET_CLASS}: {c} (dolzhno = {orig_count})")

        # Raspredelenie class_level posle
        print(f"\n  Raspredelenie class_level (original_grade={TARGET_CLASS}):")
        cur = conn.execute(f"""
            SELECT class_level, COUNT(*) as cnt
            FROM adaptive_tasks WHERE original_grade={TARGET_CLASS}
            GROUP BY class_level ORDER BY class_level
        """)
        for r in cur.fetchall():
            print(f"    class_level={r[0]}: {r[1]} zadach")

        # Difficulty dlya grade=6 posle
        print(f"\n  Raspredelenie difficulty_level (class_level={TARGET_CLASS} posle):")
        cur = conn.execute(f"""
            SELECT difficulty_level, COUNT(*) as cnt
            FROM adaptive_tasks WHERE class_level={TARGET_CLASS}
            GROUP BY difficulty_level ORDER BY difficulty_level
        """)
        for r in cur.fetchall():
            print(f"    difficulty={r[0]}: {r[1]} zadach")

        # Vsego zadach 6 klassa
        cur = conn.execute(f"SELECT COUNT(*) FROM adaptive_tasks WHERE class_level={TARGET_CLASS}")
        grade6_total = cur.fetchone()[0]
        print(f"\n  Vsego zadach {TARGET_CLASS} klassa posle: {grade6_total}")

        # PROVERKA: grade 7 ne tronuto
        cur = conn.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7 AND llm_audited_at IS NOT NULL")
        grade7_after = cur.fetchone()[0]
        print(f"\n  Grade 7 audited posle: {grade7_after} (dolzhno = {grade7_before})")
        if grade7_after != grade7_before:
            print("  PROBLEMA: grade 7 byl izmenen!")
        else:
            print("  OK: grade 7 ne tronuto")

        # SQL dlya otkata
        rollback_sql = f"""-- ROLLBACK: Otkat rekalibratsii {TARGET_CLASS} klassa
-- Sozdan: {datetime.datetime.now().isoformat()}
-- Bekap: {backup_path}

BEGIN TRANSACTION;

UPDATE adaptive_tasks
SET class_level = original_grade
WHERE original_grade = {TARGET_CLASS} AND original_grade IS NOT NULL;

UPDATE adaptive_tasks
SET difficulty_level = original_difficulty
WHERE original_grade = {TARGET_CLASS} AND original_difficulty IS NOT NULL;

UPDATE adaptive_tasks
SET needs_reclassification = 0
WHERE original_grade = {TARGET_CLASS} AND needs_reclassification = 1;

COMMIT;
"""
        rollback_path = f'scripts/rollback_grade{TARGET_CLASS}_recalibration.sql'
        with open(rollback_path, 'w', encoding='utf-8') as f:
            f.write(rollback_sql)
        print(f"\n  SQL dlya otkata: {rollback_path}")

        print("\n" + "=" * 60)
        print(f"PRIMENENIE GRADE {TARGET_CLASS} ZAVERSHENO USPESHNO")
        print(f"  Bekap: {backup_path}")
        print("=" * 60)

    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"\n[ERROR] {e}")
        print("[TX] ROLLBACK")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
