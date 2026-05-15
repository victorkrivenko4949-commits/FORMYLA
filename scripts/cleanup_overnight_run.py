#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Очистка после ночного прогона перед перезапуском с фиксами:

1. Помечает задачи id 8836-8909 как deprecated (is_flagged=True)
2. Удаляет 61 запись из manual_review_queue со status='pending'
3. Удаляет ячейки algebra/g7/l1..l5 из logs/regen_progress.json
   (чтобы они перепрогнались с новыми фиксами)
4. Создаёт бэкап progress.json перед очисткой
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB = Path("instance/formyla.db")
PROGRESS = Path("logs/regen_progress.json")

# Диапазон задач из вчерашнего/ночного прогона
TASK_ID_MIN = 8836
TASK_ID_MAX = 8909

# Ячейки на повторный прогон с новыми фиксами
CELLS_TO_RESET = [
    "algebra/g7/l1",
    "algebra/g7/l2",
    "algebra/g7/l3",
    "algebra/g7/l4",
    "algebra/g7/l5",
]


def main() -> int:
    # Бэкап progress.json
    if PROGRESS.exists():
        bak = PROGRESS.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        shutil.copy2(PROGRESS, bak)
        print(f"✓ backup: {bak}")

    # ─── DB ────────────────────────────────────────────────────────────────
    if not DB.exists():
        print(f"❌ {DB} not found")
        return 1

    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    # 1. Сколько задач затронем?
    cnt = cur.execute(
        "SELECT COUNT(*) FROM adaptive_tasks WHERE id BETWEEN ? AND ?",
        (TASK_ID_MIN, TASK_ID_MAX),
    ).fetchone()[0]
    already_flagged = cur.execute(
        "SELECT COUNT(*) FROM adaptive_tasks WHERE id BETWEEN ? AND ? AND is_flagged=1",
        (TASK_ID_MIN, TASK_ID_MAX),
    ).fetchone()[0]
    print(f"\n📦 adaptive_tasks id {TASK_ID_MIN}..{TASK_ID_MAX}: всего {cnt}, уже флаг {already_flagged}")

    # 2. Помечаем как deprecated
    cur.execute(
        """
        UPDATE adaptive_tasks
        SET is_flagged = 1,
            flagged_reason = 'deprecated_overnight_run_2026_05_14'
        WHERE id BETWEEN ? AND ? AND is_flagged = 0
        """,
        (TASK_ID_MIN, TASK_ID_MAX),
    )
    deprecated = cur.rowcount
    print(f"  → deprecated: {deprecated}")

    # 3. Очистка manual_review_queue
    pending = cur.execute(
        "SELECT COUNT(*) FROM manual_review_queue WHERE status='pending'"
    ).fetchone()[0]
    print(f"\n📋 manual_review_queue pending: {pending}")
    cur.execute("DELETE FROM manual_review_queue WHERE status='pending'")
    deleted_q = cur.rowcount
    print(f"  → deleted: {deleted_q}")

    conn.commit()
    conn.close()

    # ─── progress.json ─────────────────────────────────────────────────────
    if PROGRESS.exists():
        prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
        cells = prog.get("cells", {})
        removed = 0
        for k in list(cells.keys()):
            if k in CELLS_TO_RESET:
                del cells[k]
                removed += 1
        # Пересчитаем global_cost
        prog["global_cost"] = round(sum(c.get("cost", 0) for c in cells.values()), 4)
        PROGRESS.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📝 progress.json: removed {removed} cells, {len(cells)} remain, "
              f"new global_cost=${prog['global_cost']}")

    print("\n✅ Cleanup done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
