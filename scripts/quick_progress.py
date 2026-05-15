#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Быстрая сводка по progress.json — для контроля во время прогона."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

P = Path("logs/regen_progress.json")
if not P.exists():
    print("no progress yet"); sys.exit(0)

prog = json.loads(P.read_text(encoding="utf-8"))
cells = prog.get("cells", {})

# Делим на категории
skipped = [k for k, v in cells.items() if v.get("skipped_reason")]
processed = [k for k, v in cells.items() if not v.get("skipped_reason")]
problematic = [k for k, v in cells.items() if v.get("problematic")]

total_success = sum(v.get("success", 0) for v in cells.values())
total_review = sum(v.get("review", 0) for v in cells.values())
total_dup = sum(v.get("duplicates", 0) for v in cells.values())
total_cost = float(prog.get("global_cost", 0))

started = prog.get("started_at")
elapsed_sec = 0
if started:
    try:
        elapsed_sec = (datetime.now() - datetime.fromisoformat(started)).total_seconds()
    except Exception:
        pass

# Скорость
processed_count = len(processed)
sec_per_cell = elapsed_sec / processed_count if processed_count else 0
remaining = 7 * 7 * 6 - len(cells)  # 6 subjects * 7 grades * 7 levels = 294, минус что есть
eta_sec = sec_per_cell * remaining

print("=" * 70)
print(f"PROGRESS @ {datetime.now().strftime('%H:%M:%S')}")
print("=" * 70)
print(f"  Cells in progress.json:  {len(cells)} / 294")
print(f"    skipped (unrealistic): {len(skipped)}")
print(f"    processed:             {len(processed)}")
print(f"    problematic:           {len(problematic)}")
print(f"  Tasks saved in DB:       {total_success}")
print(f"  Tasks in review:         {total_review}")
print(f"  Duplicates filtered:     {total_dup}")
print(f"  Total cost:              ${total_cost:.4f}")
print(f"  Elapsed:                 {elapsed_sec/60:.1f} min")
if sec_per_cell:
    print(f"  Sec/cell (parallel):     {sec_per_cell:.0f}")
    print(f"  ETA remaining:           {eta_sec/3600:.1f}h")
print()
print("─── LAST 10 PROCESSED CELLS ───")
sorted_cells = sorted(
    [(k, v) for k, v in cells.items() if v.get("finished_at") and not v.get("skipped_reason")],
    key=lambda kv: kv[1].get("finished_at", ""),
    reverse=True,
)[:10]
for k, v in sorted_cells:
    flag = "⚠" if v.get("problematic") else " "
    fin = v.get("finished_at", "")[-8:]
    print(f"  {flag} {fin}  {k:<32}  s={v.get('success',0):>2} r={v.get('review',0):>2} dup={v.get('duplicates',0):>2} ${v.get('cost',0):.4f}  iters={v.get('avg_iter',0):.2f}")

if problematic:
    print()
    print(f"─── PROBLEMATIC ({len(problematic)}) ───")
    for k in problematic:
        v = cells[k]
        print(f"  {k}: review={v.get('review',0)}/{25} ({v.get('review_pct',0):.0f}%)")
