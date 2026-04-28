# -*- coding: utf-8 -*-
"""
Otkat izmeneniy rekalibratsii 7 klassa
Vosstanalivat original_grade i original_difficulty

Zapuskat': python scripts/rollback_grade7_recalibration.py
"""
import sqlite3
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Proverka skol'ko zadach mozhno otkati
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks
        WHERE original_grade IS NOT NULL AND original_grade = 7
    """)
    can_rollback = cur.fetchone()[0]
    print(f"Zadach s original_grade=7: {can_rollback}")
    
    if can_rollback == 0:
        print("Necheho otkatyvat'.")
        conn.close()
        return
    
    print(f"\nBudet otkacheno: {can_rollback} zadach")
    print("Eto vosstanovit original'nye class_level i difficulty_level.")
    
    ans = input("\nProdolzhat'? (yes/no): ")
    if ans.lower() != 'yes':
        print("Otmena.")
        conn.close()
        return
    
    # Otkat grade
    cur.execute("""
        UPDATE adaptive_tasks
        SET class_level = original_grade
        WHERE original_grade IS NOT NULL AND original_grade = 7
    """)
    grade_rolled = cur.rowcount
    print(f"Otkacheno class_level: {grade_rolled}")
    
    # Otkat difficulty
    cur.execute("""
        UPDATE adaptive_tasks
        SET difficulty_level = original_difficulty
        WHERE original_grade = 7 AND original_difficulty IS NOT NULL
    """)
    diff_rolled = cur.rowcount
    print(f"Otkacheno difficulty_level: {diff_rolled}")
    
    # Sbrasyvaem flagi
    cur.execute("""
        UPDATE adaptive_tasks
        SET is_flagged = 0, flagged_reason = NULL
        WHERE original_grade = 7 
          AND flagged_reason LIKE 'LLM audit:%'
    """)
    flags_cleared = cur.rowcount
    print(f"Sbrosheno flagov: {flags_cleared}")
    
    conn.commit()
    conn.close()
    print("\n[DONE] Otkat zavershen.")


if __name__ == '__main__':
    main()
