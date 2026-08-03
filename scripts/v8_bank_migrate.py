# -*- coding: utf-8 -*-
"""Миграция JSON-банка: уровни 4..8 -> 1..5 (level - 3).

Правило: тот же маппинг, что уже применялся при переходе на пятибалльную шкалу.
Было: bank_level = canonical_level + 3, clamped [4, 8].
Стало: bank_level = bank_level - 3 -> [1..5].

Делает копию базы formyla.db перед SQL-миграцией grade_tasks.
"""
import json
import os
import shutil
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
BANK_DIR = BASE / "daily_tasks" / "data" / "task_bank"
DB_PATH = BASE / "formyla.db"

GRADE_FILES = {
    5: "formyla_grade5.json",
    6: "formyla_grade6.json",
    7: "formyla_grade7.json",
    8: "formyla_grade8.json",
    9: "formyla_grade9.json",
    10: "formyla_grade10.json",
    11: "formyla_grade11.json",
}


def backup_db():
    """Создать копию базы перед миграцией."""
    backup_path = DB_PATH.with_suffix(".db.bak_v8bank")
    print(f"[DB] Копия базы: {DB_PATH} -> {backup_path}")
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def migrate_json_bank():
    """Перенести уровни в JSON-файлах банка: 4->1, 5->2, 6->3, 7->4, 8->5."""
    print("=" * 60)
    print("JSON-БАНК: уровни 4..8 -> 1..5")
    print("=" * 60)
    for grade, fname in sorted(GRADE_FILES.items()):
        path = BANK_DIR / fname
        if not path.exists():
            print(f"  grade {grade}: файл не найден, пропускаю")
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        probes = data.get("probes", [])
        before = {}
        for p in probes:
            lvl = p.get("level")
            before[lvl] = before.get(lvl, 0) + 1

        for p in probes:
            old = p.get("level")
            if old is not None and 4 <= old <= 8:
                p["level"] = old - 3

        after = {}
        for p in probes:
            lvl = p.get("level")
            after[lvl] = after.get(lvl, 0) + 1

        # Сохраняем
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"  grade {grade} ({fname}): {len(probes)} пробников")
        print(f"    до:   {dict(sorted(before.items()))}")
        print(f"    после: {dict(sorted(after.items()))}")


def migrate_grade_tasks():
    """SQL-миграция grade_tasks: уровни 6->3, 7->4 (level - 3)."""
    print()
    print("=" * 60)
    print("GRADE_TASKS SQL: уровни 6->3, 7->4")
    print("=" * 60)
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Распределение до
    print("  До:")
    cur.execute("SELECT level, COUNT(*) FROM grade_tasks GROUP BY level ORDER BY level")
    for r in cur.fetchall():
        print(f"    level {r[0]}: {r[1]}")

    # Миграция
    cur.execute("UPDATE grade_tasks SET level = level - 3 WHERE level IN (6, 7)")
    print(f"  Обновлено строк: {cur.rowcount}")

    # Распределение после
    print("  После:")
    cur.execute("SELECT level, COUNT(*) FROM grade_tasks GROUP BY level ORDER BY level")
    for r in cur.fetchall():
        print(f"    level {r[0]}: {r[1]}")

    cur.execute("SELECT MIN(level), MAX(level) FROM grade_tasks")
    min_lvl, max_lvl = cur.fetchone()
    print(f"  min={min_lvl}, max={max_lvl}")

    conn.commit()
    conn.close()


def main():
    os.chdir(BASE)
    backup_db()
    migrate_json_bank()
    migrate_grade_tasks()
    print()
    print("ГОТОВО. JSON-банк: уровни 1..5. grade_tasks: уровни 1..5.")


if __name__ == "__main__":
    main()
