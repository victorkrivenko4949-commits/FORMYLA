#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утренний отчёт по ночной регенерации.

Источники:
    - logs/regen_progress.json — статистика по каждой ячейке
    - БД formyla.db (task_generation_log, manual_review_queue, adaptive_tasks, cost_log)

Печатает:
    1. Сводная таблица 6×7×7 (success/review/cost)
    2. Топ-10 проблемных ячеек по % review
    3. Итоговая стоимость и время
    4. 5 случайных задач для ручной проверки
    5. Список ячеек, помеченных как problematic_cell
    6. SQL-сводка по очереди ревью

Запуск:
    python scripts/morning_report.py
"""
from __future__ import annotations

import json
import os
import random
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROGRESS_FILE = Path("logs/regen_progress.json")
DB_PATH = Path("instance/formyla.db")


SUBJECTS = ["algebra", "geometry", "number_theory",
            "combinatorics", "logic", "set_theory"]
GRADES = [7, 8, 9, 10, 11, 12, 13]
LEVELS = [1, 2, 3, 4, 5, 6, 7]


def fmt_dur(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


def main() -> int:
    if not PROGRESS_FILE.exists():
        print(f"❌ Нет {PROGRESS_FILE}. Регенерация ещё не запускалась.")
        return 1

    progress = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    cells = progress.get("cells", {})

    if not cells:
        print("❌ В progress.json нет обработанных ячеек.")
        return 1

    # ─── 1. Сводная таблица ──────────────────────────────────────────────────
    print("\n" + "═" * 90)
    print("📊 СВОДНАЯ ТАБЛИЦА (success / review / $cost) — по предметам, классам и уровням")
    print("═" * 90)

    for subj in SUBJECTS:
        subj_cells = {k: v for k, v in cells.items() if v.get("subject") == subj}
        if not subj_cells:
            continue
        s_total = sum(c["success"] for c in subj_cells.values())
        r_total = sum(c["review"] for c in subj_cells.values())
        c_total = sum(c["cost"] for c in subj_cells.values())
        print(f"\n🔹 {subj.upper()}  (всего: success={s_total}, review={r_total}, ${c_total:.2f})")
        print(f"  {'level→':>6} " + " ".join(f"{l:>14}" for l in LEVELS))
        for grade in GRADES:
            row = [f"grade {grade}:"]
            for lvl in LEVELS:
                key = f"{subj}/g{grade}/l{lvl}"
                c = cells.get(key)
                if c is None:
                    row.append(f"{'-':>14}")
                else:
                    flag = "⚠" if c.get("problematic") else " "
                    row.append(f"{c['success']:>2}/{c['review']:<2}${c['cost']:5.2f}{flag}")
            print(f"  {row[0]:>6} " + " ".join(f"{r:>14}" for r in row[1:]))

    # ─── 3. Итоговая стоимость и время ───────────────────────────────────────
    total_cost = sum(c["cost"] for c in cells.values())
    total_success = sum(c["success"] for c in cells.values())
    total_review = sum(c["review"] for c in cells.values())
    total_errors = sum(c.get("errors", 0) for c in cells.values())
    expected_per_cell = 25  # default
    total_processed_cells = len(cells)

    started = progress.get("started_at")
    elapsed_str = "—"
    if started:
        try:
            t0 = datetime.fromisoformat(started)
            elapsed_str = fmt_dur((datetime.now() - t0).total_seconds())
        except Exception:
            pass

    print("\n" + "═" * 90)
    print("💰 ИТОГО")
    print("═" * 90)
    print(f"  Ячеек обработано:    {total_processed_cells} из {len(SUBJECTS)*len(GRADES)*len(LEVELS)}")
    print(f"  ✓ Задач сохранено:   {total_success}")
    print(f"  ⚠ В manual_review:   {total_review}")
    print(f"  ✗ Ошибок:            {total_errors}")
    print(f"  Стоимость:           ${total_cost:.4f}")
    print(f"  Время:               {elapsed_str}")

    # ─── 2. Топ-10 проблемных ячеек ──────────────────────────────────────────
    print("\n" + "═" * 90)
    print("🔥 ТОП-10 ПРОБЛЕМНЫХ ЯЧЕЕК (по % review)")
    print("═" * 90)
    ranked = sorted(
        cells.items(),
        key=lambda kv: (-kv[1].get("review_pct", 0), kv[0]),
    )[:10]
    print(f"  {'cell':<32} {'success':>8} {'review':>8} {'%review':>8} {'avg_it':>7} {'cost':>8}")
    for k, c in ranked:
        print(f"  {k:<32} {c['success']:>8} {c['review']:>8} {c.get('review_pct', 0):>7.1f}% "
              f"{c.get('avg_iter', 0):>7.2f} ${c['cost']:>7.4f}")

    # ─── 5. Problematic cells ────────────────────────────────────────────────
    print("\n" + "═" * 90)
    print("⚠ PROBLEMATIC CELLS (>40% review)")
    print("═" * 90)
    bad = [(k, v) for k, v in cells.items() if v.get("problematic")]
    if not bad:
        print("  (нет таких — все ячейки в норме)")
    else:
        for k, v in bad:
            print(f"  {k}: review={v['review']}/{expected_per_cell} ({v.get('review_pct', 0):.0f}%), cost=${v['cost']:.4f}")

    # ─── 4 + 6 + примеры из БД ───────────────────────────────────────────────
    if not DB_PATH.exists():
        print(f"\n⚠ {DB_PATH} not found — пропускаю DB-секции")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # Подсчёт по очереди ревью
    print("\n" + "═" * 90)
    print("📋 SQL: SELECT count(*), reason FROM manual_review_queue WHERE status='pending' GROUP BY reason")
    print("═" * 90)
    rows = cur.execute(
        "SELECT COUNT(*), reason FROM manual_review_queue "
        "WHERE status='pending' GROUP BY reason ORDER BY COUNT(*) DESC"
    ).fetchall()
    if rows:
        for cnt, reason in rows:
            print(f"  {cnt:>5}  {reason or '(no reason)'}")
    else:
        print("  (очередь пуста)")

    # 5 случайных задач из недавно сохранённых
    print("\n" + "═" * 90)
    print("📝 5 СЛУЧАЙНЫХ ЗАДАЧ ДЛЯ РУЧНОЙ ПРОВЕРКИ")
    print("═" * 90)
    all_ids: list[int] = []
    for c in cells.values():
        all_ids.extend(c.get("saved_ids", []))
    if all_ids:
        sample = random.sample(all_ids, min(5, len(all_ids)))
        for tid in sample:
            row = cur.execute(
                "SELECT id, class_level, difficulty_level, topic, "
                "substr(task_text, 1, 400), correct_answer "
                "FROM adaptive_tasks WHERE id=?", (tid,)
            ).fetchone()
            if row:
                print(f"\n  ──── id={row[0]}  class={row[1]}  level={row[2]}  topic={row[3]} ────")
                print(f"  {row[4]}")
                print(f"  Ответ: {row[5]}")
    else:
        print("  (saved_ids пуст в progress.json)")

    # Доп. SQL: сводка по cost_log
    print("\n" + "═" * 90)
    print("💸 РАСХОДЫ ПО МОДЕЛЯМ (cost_log)")
    print("═" * 90)
    rows = cur.execute(
        "SELECT stage, model, COUNT(*) cnt, SUM(input_tokens), SUM(output_tokens), "
        "SUM(cost_usd) FROM cost_log GROUP BY stage, model ORDER BY SUM(cost_usd) DESC"
    ).fetchall()
    print(f"  {'stage':<12} {'model':<35} {'calls':>6} {'in tok':>10} {'out tok':>10} {'$total':>10}")
    for stage, model, cnt, tin, tout, cost in rows:
        print(f"  {stage:<12} {model:<35} {cnt:>6} {tin or 0:>10} {tout or 0:>10} ${cost or 0:>9.4f}")

    conn.close()
    print("\n" + "═" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
