#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Полная диагностика регенерации: на что ушли деньги, где узкое горло.
Безопасно: только SELECT, ничего не пишет в БД.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DB = Path("instance/formyla.db")
PROGRESS = Path("logs/regen_progress.json")


def section(title: str) -> None:
    print(f"\n{'═' * 90}")
    print(f"  {title}")
    print("═" * 90)


def main() -> int:
    if not DB.exists():
        print("❌ formyla.db not found")
        return 1
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()

    # ─── 1. ПРОГРЕСС ──────────────────────────────────────────────────────
    section("1. ПРОГРЕСС ИЗ regen_progress.json")
    if PROGRESS.exists():
        prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
        cells = prog.get("cells", {})
        print(f"  started_at:   {prog.get('started_at')}")
        print(f"  global_cost:  ${prog.get('global_cost', 0):.4f}")
        print(f"  cells done:   {len(cells)}")
        for k, v in cells.items():
            print(f"    {k:<30} success={v.get('success',0):>2} review={v.get('review',0):>2} "
                  f"err={v.get('errors',0):>2} cost=${v.get('cost',0):.4f} "
                  f"avg_iter={v.get('avg_iter',0):.2f} "
                  f"{'⚠ PROBLEMATIC' if v.get('problematic') else ''}")
    else:
        print("  (нет progress.json)")

    # ─── 2. РАСХОДЫ ПО СТАДИЯМ И МОДЕЛЯМ ──────────────────────────────────
    section("2. РАСХОДЫ ПО СТАДИЯМ × МОДЕЛЯМ (cost_log)")
    rows = cur.execute("""
        SELECT stage, model, COUNT(*) calls,
               SUM(input_tokens) tin, SUM(output_tokens) tout,
               SUM(cost_usd) cost, AVG(latency_s) avg_lat
        FROM cost_log
        GROUP BY stage, model
        ORDER BY cost DESC
    """).fetchall()
    total_cost = sum(r[5] or 0 for r in rows)
    print(f"  {'stage':<12} {'model':<35} {'calls':>6} {'$cost':>10} {'%':>6} {'avg_lat':>8}")
    print(f"  {'-'*12} {'-'*35} {'-'*6} {'-'*10} {'-'*6} {'-'*8}")
    for stage, model, calls, tin, tout, cost, avg_lat in rows:
        pct = (cost / total_cost * 100) if total_cost else 0
        print(f"  {stage:<12} {model:<35} {calls:>6} ${cost or 0:>9.4f} {pct:>5.1f}% {avg_lat or 0:>7.2f}s")
    print(f"  {'TOTAL':<55}        ${total_cost:>9.4f}")

    # ─── 3. РАСПРЕДЕЛЕНИЕ ИТЕРАЦИЙ ────────────────────────────────────────
    section("3. РАСПРЕДЕЛЕНИЕ ИТЕРАЦИЙ (task_generation_log)")
    rows = cur.execute("""
        SELECT iterations_used, success,
               COUNT(*) n, AVG(total_cost_usd) avg_cost
        FROM task_generation_log
        GROUP BY iterations_used, success
        ORDER BY iterations_used, success
    """).fetchall()
    print(f"  {'iters':>5} {'result':<10} {'count':>6} {'$avg':>10}")
    for it, suc, n, avg in rows:
        result = "SUCCESS" if suc else "FAIL"
        print(f"  {it:>5} {result:<10} {n:>6} ${avg or 0:>9.4f}")

    # Среднее и медиана итераций
    cur.execute("SELECT iterations_used FROM task_generation_log ORDER BY iterations_used")
    iters = [r[0] for r in cur.fetchall()]
    if iters:
        avg = sum(iters) / len(iters)
        med = iters[len(iters) // 2]
        print(f"\n  Среднее итераций: {avg:.2f}")
        print(f"  Медиана:          {med}")
        print(f"  Всего попыток:    {len(iters)}")

    # ─── 4. КОЛ-ВО FAIL ОТ КАЖДОГО АГЕНТА ─────────────────────────────────
    section("4. КТО ЧАЩЕ FAIL'ит — Validator или Calibrator?")
    # Парсим iterations_detail_json: считаем сколько раз verdict=FAIL у каждого
    rows = cur.execute(
        "SELECT iterations_detail_json FROM task_generation_log "
        "WHERE iterations_detail_json IS NOT NULL"
    ).fetchall()
    val_fail = cal_fail = val_pass = cal_pass = gen_err = 0
    for (raw,) in rows:
        try:
            arr = json.loads(raw)
            for item in arr:
                stage = item.get("stage")
                verdict = item.get("verdict")
                if stage == "validator":
                    if verdict == "FAIL": val_fail += 1
                    elif verdict == "PASS": val_pass += 1
                elif stage == "calibrator":
                    if verdict == "FAIL": cal_fail += 1
                    elif verdict == "PASS": cal_pass += 1
                elif stage == "generator" and verdict == "ERROR":
                    gen_err += 1
        except Exception:
            pass
    print(f"  Validator:  PASS={val_pass}  FAIL={val_fail}  ({val_fail/(val_fail+val_pass)*100 if val_fail+val_pass else 0:.1f}% FAIL)")
    print(f"  Calibrator: PASS={cal_pass}  FAIL={cal_fail}  ({cal_fail/(cal_fail+cal_pass)*100 if cal_fail+cal_pass else 0:.1f}% FAIL)")
    print(f"  Generator ERROR (bad JSON): {gen_err}")

    # ─── 5. ID 8881 / 8885 ────────────────────────────────────────────────
    section("5. ИНЦИДЕНТ id 8881 / 8885 (дубль?)")
    for tid in (8881, 8885):
        row = cur.execute(
            "SELECT id, class_level, difficulty_level, topic, "
            "substr(task_text, 1, 350), correct_answer "
            "FROM adaptive_tasks WHERE id=?", (tid,)
        ).fetchone()
        if row:
            print(f"\n  id={row[0]}  class={row[1]}  level={row[2]}  topic={row[3]}")
            print(f"  text: {row[4]}")
            print(f"  answer: {row[5]}")
        else:
            print(f"  id={tid} НЕ НАЙДЕНО в adaptive_tasks")

    # ─── 6. ВСЕ ID СОЗДАННЫЕ ЗА ПОСЛЕДНИЕ 24 ЧАСА ─────────────────────────
    section("6. ВСЕ ЗАДАЧИ СОЗДАННЫЕ ЗА ПОСЛЕДНИЕ 24 ЧАСА")
    cols = [c[1] for c in cur.execute("PRAGMA table_info(adaptive_tasks)").fetchall()]
    has_source = "source" in cols
    src_col = "source" if has_source else "'-' AS source"
    rows = cur.execute(f"""
        SELECT id, class_level, difficulty_level, topic, {src_col},
               substr(task_text, 1, 80)
        FROM adaptive_tasks
        WHERE created_at >= datetime('now', '-24 hours')
        ORDER BY id
    """).fetchall()
    print(f"  Всего: {len(rows)}")
    for r in rows:
        src = r[4] or "-"
        topic_short = (r[3] or "")[:20]
        print(f"  id={r[0]:<5} g={r[1]} L={r[2]}  src={src:<22}  {topic_short:<20}  {r[5][:80]}")

    # ─── 7. ОЧЕРЕДЬ РЕВЬЮ ─────────────────────────────────────────────────
    section("7. manual_review_queue — по причинам")
    rows = cur.execute(
        "SELECT reason, COUNT(*) FROM manual_review_queue "
        "WHERE status='pending' GROUP BY reason ORDER BY COUNT(*) DESC"
    ).fetchall()
    for reason, cnt in rows:
        print(f"  {cnt:>4}  {reason or '(no reason)'}")
    total_q = sum(r[1] for r in rows)
    print(f"  total pending: {total_q}")

    # ─── 8. 5 СЛУЧАЙНЫХ ЗАДАЧ ─────────────────────────────────────────────
    section("8. 5 СЛУЧАЙНЫХ ЗАДАЧ — ОЦЕНИ ВРУЧНУЮ")
    rows = cur.execute("""
        SELECT id, class_level, difficulty_level, topic, task_text, correct_answer
        FROM adaptive_tasks
        WHERE created_at >= datetime('now', '-24 hours')
        ORDER BY RANDOM() LIMIT 5
    """).fetchall()
    for r in rows:
        print(f"\n  ── id={r[0]}  class={r[1]}  level={r[2]}  topic={r[3]} ──")
        print(f"  {r[4]}")
        print(f"  Ответ: {r[5]}")

    # ─── 9. ВРЕМЯ ──────────────────────────────────────────────────────────
    section("9. ВРЕМЕННЫЕ МЕТРИКИ (latency)")
    rows = cur.execute("""
        SELECT stage, model, MIN(latency_s), AVG(latency_s), MAX(latency_s)
        FROM cost_log
        GROUP BY stage, model
    """).fetchall()
    print(f"  {'stage':<12} {'model':<35} {'min':>7} {'avg':>7} {'max':>7}")
    for stage, model, mn, av, mx in rows:
        print(f"  {stage:<12} {model:<35} {mn or 0:>6.2f}s {av or 0:>6.2f}s {mx or 0:>6.2f}s")

    conn.close()
    print("\n" + "═" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
