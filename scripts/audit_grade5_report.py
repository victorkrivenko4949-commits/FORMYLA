#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Отчёт по LLM-аудиту задач 5 класса.
Запускать ПОСЛЕ завершения audit_grade5_llm.py
"""

import sys
import io
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = "instance/formyla.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print("ОТЧЁТ: LLM-АУДИТ ЗАДАЧ 5 КЛАССА")
print("=" * 70)

# 1. Общая статистика
cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5")
total = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5 AND llm_audited_at IS NOT NULL")
audited = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=5 AND llm_audited_at IS NULL")
not_audited = cur.fetchone()[0]

print(f"\n[1] ОБЩАЯ СТАТИСТИКА")
print(f"    Всего задач в 5 классе: {total}")
print(f"    Проверено LLM:          {audited} ({audited*100//total if total else 0}%)")
print(f"    Не проверено:           {not_audited}")

# 2. Распределение по рекомендованному классу
print(f"\n[2] РАСПРЕДЕЛЕНИЕ ПО РЕКОМЕНДОВАННОМУ КЛАССУ (llm_suggested_grade)")
cur.execute("""
    SELECT llm_suggested_grade, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL
    GROUP BY llm_suggested_grade
    ORDER BY llm_suggested_grade
""")
rows = cur.fetchall()
total_audited = audited
for row in rows:
    grade = row['llm_suggested_grade']
    cnt = row['cnt']
    pct = cnt * 100 // total_audited if total_audited else 0
    marker = " ✅ ОСТАЮТСЯ" if grade == 5 else f" ⬆️  → ПЕРЕМЕСТИТЬ в {grade} кл."
    print(f"    Класс {grade}: {cnt:4d} задач ({pct:3d}%){marker}")

# 3. Задачи которые ОСТАЮТСЯ в 5 классе
cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL AND llm_suggested_grade=5
""")
keep_count = cur.fetchone()[0]

# 4. Задачи которые нужно ПЕРЕМЕСТИТЬ
cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL
    AND llm_suggested_grade != 5
    AND (llm_quality_score IS NULL OR llm_quality_score >= 0.5)
""")
move_count = cur.fetchone()[0]

# 5. Низкое качество
cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL
    AND llm_quality_score < 0.5
""")
low_quality_count = cur.fetchone()[0]

print(f"\n[3] ПЛАН ДЕЙСТВИЙ")
print(f"    KEEP (остаются в 5 кл.):     {keep_count} задач")
print(f"    MOVE_GRADE (переместить):    {move_count} задач")
print(f"    LOW_QUALITY (флаг):          {low_quality_count} задач")

# 6. Распределение сложности (текущая vs рекомендованная)
print(f"\n[4] ТЕКУЩАЯ СЛОЖНОСТЬ (difficulty_level) — 5 класс")
cur.execute("""
    SELECT difficulty_level, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level=5
    GROUP BY difficulty_level
    ORDER BY difficulty_level
""")
for row in cur.fetchall():
    print(f"    Сложность {row['difficulty_level']}: {row['cnt']} задач")

print(f"\n[5] РЕКОМЕНДОВАННАЯ СЛОЖНОСТЬ (llm_suggested_difficulty) — только задачи для 5 кл.")
cur.execute("""
    SELECT llm_suggested_difficulty, COUNT(*) as cnt
    FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL AND llm_suggested_grade=5
    GROUP BY llm_suggested_difficulty
    ORDER BY llm_suggested_difficulty
""")
for row in cur.fetchall():
    print(f"    Сложность {row['llm_suggested_difficulty']}: {row['cnt']} задач")

# 7. Аномалии сложности (>5)
cur.execute("""
    SELECT COUNT(*) FROM adaptive_tasks
    WHERE class_level=5 AND difficulty_level > 5
""")
anomaly_count = cur.fetchone()[0]
print(f"\n[6] АНОМАЛИИ: задачи с difficulty_level > 5: {anomaly_count}")
if anomaly_count > 0:
    cur.execute("""
        SELECT id, difficulty_level, llm_suggested_difficulty, llm_suggested_grade
        FROM adaptive_tasks
        WHERE class_level=5 AND difficulty_level > 5
        LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"    ID={row['id']} diff={row['difficulty_level']} → llm_diff={row['llm_suggested_difficulty']} llm_grade={row['llm_suggested_grade']}")

# 8. Качество
print(f"\n[7] РАСПРЕДЕЛЕНИЕ КАЧЕСТВА (llm_quality_score)")
cur.execute("""
    SELECT
        SUM(CASE WHEN llm_quality_score >= 0.8 THEN 1 ELSE 0 END) as high,
        SUM(CASE WHEN llm_quality_score >= 0.5 AND llm_quality_score < 0.8 THEN 1 ELSE 0 END) as mid,
        SUM(CASE WHEN llm_quality_score < 0.5 THEN 1 ELSE 0 END) as low,
        AVG(llm_quality_score) as avg_q
    FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL
""")
row = cur.fetchone()
print(f"    Высокое (>=0.8):  {row['high']} задач")
print(f"    Среднее (0.5-0.8): {row['mid']} задач")
print(f"    Низкое (<0.5):    {row['low']} задач")
print(f"    Среднее качество: {row['avg_q']:.3f}")

# 9. Примеры задач для перемещения
print(f"\n[8] ПРИМЕРЫ ЗАДАЧ ДЛЯ ПЕРЕМЕЩЕНИЯ (первые 5)")
cur.execute("""
    SELECT id, difficulty_level, llm_suggested_grade, llm_suggested_difficulty,
           llm_quality_score, llm_rationale,
           SUBSTR(task_text, 1, 100) as preview
    FROM adaptive_tasks
    WHERE class_level=5 AND llm_audited_at IS NOT NULL
    AND llm_suggested_grade != 5
    AND (llm_quality_score IS NULL OR llm_quality_score >= 0.5)
    ORDER BY llm_suggested_grade DESC, llm_quality_score DESC
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"\n    ID={row['id']} | diff={row['difficulty_level']} → {row['llm_suggested_grade']} кл. diff={row['llm_suggested_difficulty']} | q={row['llm_quality_score']:.2f}")
    print(f"    Текст: {row['preview']}...")
    if row['llm_rationale']:
        print(f"    Причина: {row['llm_rationale'][:120]}...")

# 10. Итоговая рекомендация
print(f"\n{'='*70}")
print(f"ИТОГ: Рекомендуется применить рекалибровку 5 класса:")
print(f"  1. MOVE_GRADE: {move_count} задач → переместить в правильные классы")
print(f"  2. RECALIB_DIFF: все задачи → пересчитать сложность на шкалу 1-5")
print(f"  3. FLAG LOW_QUALITY: {low_quality_count} задач → пометить needs_reclassification=1")
print(f"  4. В 5 классе останется: ~{keep_count} задач")
print(f"{'='*70}")

conn.close()
