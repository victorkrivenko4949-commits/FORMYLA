#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Применение рекалибровки задач 5 класса на основе LLM-аудита.

Фазы:
  1. BACKUP — резервная копия БД
  2. RECALIB_DIFF — пересчёт difficulty_level на шкалу 1-5 для ВСЕХ задач 5 кл.
  3. MOVE_GRADE — перемещение задач в правильные классы (llm_suggested_grade != 5)
  4. FLAG LOW_QUALITY — пометка задач с quality < 0.5
  5. FIX ANOMALIES — исправление оставшихся difficulty > 5

ЗАЩИТА: original_grade НЕ перезаписывается если уже заполнен.
"""

import sys
import io
import sqlite3
import shutil
import os
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"
BACKUP_DIR = "backups"

# ─── BACKUP ───────────────────────────────────────────────────────────────────
os.makedirs(BACKUP_DIR, exist_ok=True)
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{BACKUP_DIR}/formyla_before_apply_recalib_grade5_{ts}.db"
shutil.copy2(DB_PATH, backup_path)
print(f"✅ Backup: {backup_path}")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("\n" + "=" * 70)
print("РЕКАЛИБРОВКА 5 КЛАССА")
print("=" * 70)

# ─── СТАТИСТИКА ДО ────────────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5")
total_before = cur.fetchone()[0]
print(f"\n[ДО] Задач в 5 классе: {total_before}")

# ─── ФАЗА 1: RECALIB_DIFF ─────────────────────────────────────────────────────
print("\n[ФАЗА 1] RECALIB_DIFF — пересчёт difficulty_level на шкалу 1-5")
print("  Условие: llm_audited_at IS NOT NULL AND llm_quality_score >= 0.5")

cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5
    AND llm_audited_at IS NOT NULL
    AND llm_quality_score >= 0.5
    AND llm_suggested_difficulty IS NOT NULL
""")
recalib_count = cur.fetchone()[0]
print(f"  Будет обновлено: {recalib_count} задач")

# Сохраняем original_difficulty (только если ещё не сохранён)
cur.execute("""
    UPDATE adaptive_tasks
    SET original_difficulty = difficulty_level
    WHERE class_level=5
    AND original_difficulty IS NULL
""")
saved_orig_diff = cur.rowcount
print(f"  Сохранено original_difficulty: {saved_orig_diff} задач")

# Применяем новую сложность
cur.execute("""
    UPDATE adaptive_tasks
    SET difficulty_level = llm_suggested_difficulty
    WHERE class_level=5
    AND llm_audited_at IS NOT NULL
    AND llm_quality_score >= 0.5
    AND llm_suggested_difficulty IS NOT NULL
""")
updated_diff = cur.rowcount
print(f"  ✅ Обновлено difficulty_level: {updated_diff} задач")

conn.commit()

# ─── ФАЗА 2: MOVE_GRADE ───────────────────────────────────────────────────────
print("\n[ФАЗА 2] MOVE_GRADE — перемещение задач в правильные классы")
print("  Условие: llm_suggested_grade != 5 AND quality >= 0.5")

cur.execute("""
    SELECT llm_suggested_grade, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level=5
    AND llm_audited_at IS NOT NULL
    AND llm_suggested_grade != 5
    AND llm_quality_score >= 0.5
    GROUP BY llm_suggested_grade
    ORDER BY llm_suggested_grade
""")
move_preview = cur.fetchall()
for row in move_preview:
    print(f"  → {row['llm_suggested_grade']} класс: {row['cnt']} задач")

cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5
    AND llm_audited_at IS NOT NULL
    AND llm_suggested_grade != 5
    AND llm_quality_score >= 0.5
""")
move_total = cur.fetchone()[0]
print(f"  Итого для перемещения: {move_total} задач")

# Сохраняем original_grade (только если ещё не сохранён)
cur.execute("""
    UPDATE adaptive_tasks
    SET original_grade = class_level
    WHERE class_level=5
    AND original_grade IS NULL
    AND llm_audited_at IS NOT NULL
    AND llm_suggested_grade != 5
    AND llm_quality_score >= 0.5
""")
saved_orig = cur.rowcount
print(f"  Сохранено original_grade=5: {saved_orig} задач")

# Перемещаем
cur.execute("""
    UPDATE adaptive_tasks
    SET class_level = llm_suggested_grade
    WHERE class_level=5
    AND llm_audited_at IS NOT NULL
    AND llm_suggested_grade != 5
    AND llm_quality_score >= 0.5
""")
moved = cur.rowcount
print(f"  ✅ Перемещено: {moved} задач")

conn.commit()

# ─── ФАЗА 3: FLAG LOW_QUALITY ─────────────────────────────────────────────────
print("\n[ФАЗА 3] FLAG LOW_QUALITY — пометка задач с quality < 0.5")

cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE original_grade=5
    AND llm_quality_score < 0.5
""")
flag_count = cur.fetchone()[0]
print(f"  Будет помечено: {flag_count} задач")

cur.execute("""
    UPDATE adaptive_tasks
    SET needs_reclassification = 1
    WHERE original_grade=5
    AND llm_quality_score < 0.5
""")
flagged = cur.rowcount
print(f"  ✅ Помечено needs_reclassification=1: {flagged} задач")

conn.commit()

# ─── ФАЗА 4: FIX ANOMALIES ────────────────────────────────────────────────────
print("\n[ФАЗА 4] FIX ANOMALIES — исправление difficulty > 5 в 5 классе")

cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5 AND difficulty_level > 5
""")
anomaly_count = cur.fetchone()[0]
print(f"  Аномалий (diff > 5): {anomaly_count}")

if anomaly_count > 0:
    cur.execute("""
        UPDATE adaptive_tasks
        SET difficulty_level = 5
        WHERE class_level=5 AND difficulty_level > 5
    """)
    fixed = cur.rowcount
    print(f"  ✅ Исправлено → difficulty=5: {fixed} задач")
    conn.commit()
else:
    print("  ✅ Аномалий нет")

# ─── СТАТИСТИКА ПОСЛЕ ─────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("СТАТИСТИКА ПОСЛЕ РЕКАЛИБРОВКИ")
print("=" * 70)

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5")
total_after = cur.fetchone()[0]
print(f"\nЗадач в 5 классе: {total_after} (было {total_before}, убрано {total_before - total_after})")

print("\nРаспределение сложности в 5 классе:")
cur.execute("""
    SELECT difficulty_level, COUNT(*) as cnt
    FROM adaptive_tasks WHERE class_level=5
    GROUP BY difficulty_level ORDER BY difficulty_level
""")
for row in cur.fetchall():
    print(f"  Сложность {row['difficulty_level']}: {row['cnt']} задач")

print("\nКуда переместились задачи (original_grade=5):")
cur.execute("""
    SELECT class_level, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE original_grade=5 AND class_level != 5
    GROUP BY class_level ORDER BY class_level
""")
for row in cur.fetchall():
    print(f"  → {row['class_level']} класс: {row['cnt']} задач")

print("\n✅ Рекалибровка 5 класса завершена!")
print(f"   Backup: {backup_path}")
print("=" * 70)

conn.close()
