#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диагностика ТОЛЬКО последнего прогона (по run_id ячеек из progress.json)."""
from __future__ import annotations
import json, os, sqlite3, sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROG = Path("logs/regen_progress.json")
DB = Path("instance/formyla.db")

prog = json.loads(PROG.read_text(encoding="utf-8"))
cells = prog["cells"]

# Берём run_id'ы только из ячеек последнего прогона
target_subjects = {c["subject"] for c in cells.values()}
target_grades = {c["grade"] for c in cells.values()}
target_levels = {c["level"] for c in cells.values()}

print(f"Anlyzing cells: {list(cells.keys())}")
print()

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# Берём ТОЛЬКО задачи последнего часа (run был с 08:31 до 09:30 = 1 час)
rows = cur.execute(
    "SELECT iterations_detail_json FROM task_generation_log "
    "WHERE created_at >= datetime('now', '-90 minutes') "
    "  AND subject IN ({}) AND grade IN ({}) AND level IN ({})".format(
        ",".join(f"'{s}'" for s in target_subjects),
        ",".join(str(g) for g in target_grades),
        ",".join(str(l) for l in target_levels),
    )
).fetchall()

print(f"Найдено попыток: {len(rows)}")

vf = vp = cf = cp = 0
gen_err = 0
total_iters = 0
iter_counts = {}
for (raw,) in rows:
    try:
        arr = json.loads(raw)
        max_iter = 0
        for it in arr:
            stage = it.get("stage"); v = it.get("verdict")
            if stage == "validator":
                if v == "FAIL": vf += 1
                elif v == "PASS": vp += 1
            elif stage == "calibrator":
                if v == "FAIL": cf += 1
                elif v == "PASS": cp += 1
            elif stage == "generator" and v == "ERROR":
                gen_err += 1
            max_iter = max(max_iter, it.get("iteration", 0))
        iter_counts[max_iter] = iter_counts.get(max_iter, 0) + 1
        total_iters += max_iter
    except Exception:
        pass

print(f"\n— Validator (последний прогон):  PASS={vp}  FAIL={vf}  ({vf/(vf+vp)*100 if vf+vp else 0:.1f}% FAIL)")
print(f"— Calibrator (последний прогон): PASS={cp}  FAIL={cf}  ({cf/(cf+cp)*100 if cf+cp else 0:.1f}% FAIL)")
print(f"— Generator ERROR: {gen_err}")
print(f"\nРаспределение по итерациям (max в попытке):")
for k in sorted(iter_counts):
    print(f"  iter={k}: {iter_counts[k]} попыток")
if rows:
    print(f"\nСреднее итераций на попытку: {total_iters/len(rows):.2f}")

# Cost только за последние 90 минут
rows = cur.execute(
    "SELECT stage, model, COUNT(*), SUM(cost_usd) "
    "FROM cost_log "
    "WHERE created_at >= datetime('now', '-90 minutes') "
    "GROUP BY stage, model ORDER BY SUM(cost_usd) DESC"
).fetchall()
print(f"\n— Расходы за последний прогон:")
total = sum(r[3] or 0 for r in rows)
for stage, model, cnt, cost in rows:
    pct = (cost or 0) / total * 100 if total else 0
    print(f"  {stage:<12} {model:<35} {cnt:>5} calls  ${cost or 0:.4f}  ({pct:.1f}%)")
print(f"  TOTAL: ${total:.4f}")
