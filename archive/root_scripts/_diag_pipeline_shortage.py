#!/usr/bin/env python3
"""Diagnose the pipeline shortage cell (class 8, L3) and reserve candidates."""
import json
import sys
import os

RUN_DIR = r"../../Downloads/FORMYLA_CONDITION_COURT/runs/selection_1080_20260718_175442"

# ── 1. Load shortage report ──
print("=" * 70)
print("STEP 1: SHORTAGE REPORT")
print("=" * 70)
with open(os.path.join(RUN_DIR, "shortage_report.json"), "r", encoding="utf-8") as f:
    shortage = json.load(f)
print(json.dumps(shortage, indent=2, ensure_ascii=False))

# ── 2. Load curated bank -> find class 8 L3 tasks ──
print("\n" + "=" * 70)
print("STEP 1b: SELECTED TASKS IN SHORTAGE CELL (class=8, target_level=L3)")
print("=" * 70)
with open(os.path.join(RUN_DIR, "curated_bank_L1_L5.json"), "r", encoding="utf-8") as f:
    curated = json.load(f)

cell_tasks = []
for t in curated:
    cl = t.get("classlevel")
    tl = t.get("target_level")
    if cl == 8 and tl == "L3":
        cell_tasks.append(t)

print(f"Found {len(cell_tasks)} tasks in class 8 L3 (quota=21, actual={len(cell_tasks)}, shortage={21-len(cell_tasks)})")
print()
for i, t in enumerate(cell_tasks, 1):
    oid = t.get("original_id", "?")
    src = t.get("source_index", "?")
    topic = t.get("topic", "?")
    subtopic = t.get("subtopic", "?")
    score = t.get("ranking_rationale", {}).get("final_score", "?")
    rank = t.get("ranking_rationale", {}).get("rank_in_cell", "?")
    decision = t.get("decision", "?")
    print(f"  [{i:2d}] ID={oid} source={src} rank={rank} score={score} decision={decision}")
    print(f"        topic={topic} subtopic={subtopic}")

# ── 3. Load reserve -> find class 8 L3 candidates ──
print("\n" + "=" * 70)
print("STEP 2: RESERVE CANDIDATES IN SHORTAGE CELL (class=8, target_level=L3)")
print("=" * 70)
with open(os.path.join(RUN_DIR, "reserve.json"), "r", encoding="utf-8") as f:
    reserve = json.load(f)

reserve_cell = []
for t in reserve:
    cl = t.get("classlevel")
    tl = t.get("target_level")
    if cl == 8 and tl == "L3":
        reserve_cell.append(t)

print(f"Found {len(reserve_cell)} reserve candidates in class 8 L3")
print()
if reserve_cell:
    for i, t in enumerate(reserve_cell, 1):
        oid = t.get("original_id", "?")
        src = t.get("source_index", "?")
        topic = t.get("topic", "?")
        subtopic = t.get("subtopic", "?")
        decision = t.get("decision", "?")
        score = t.get("score", "?")
        rank = t.get("rank_in_cell", "?")
        orig_diff = t.get("original_difficultylevel", "?")
        print(f"  [{i:2d}] ID={oid} source={src} orig_diff={orig_diff} rank={rank} score={score} decision={decision}")
        print(f"        topic={topic} subtopic={subtopic}")
        # Print first 300 chars of tasktext
        tt = t.get("tasktext", "")[:300]
        print(f"        tasktext: {tt}...")
else:
    print("  *** NO reserve candidates in class 8 L3 ***")
    print("  This means the pool for cell (8, L3) had <21 APPROVE candidates total.")

# ── 4. Check if any OTHER classes/levels have L3 reserve candidates ──
print("\n" + "=" * 70)
print("STEP 2b: ALL L3 RESERVE CANDIDATES (any class)")
print("=" * 70)
l3_reserve = [t for t in reserve if t.get("target_level") == "L3"]
print(f"Total L3 reserve candidates: {len(l3_reserve)}")
by_class = {}
for t in l3_reserve:
    cl = t.get("classlevel")
    by_class.setdefault(cl, []).append(t)
for cl in sorted(by_class.keys()):
    print(f"  class {cl}: {len(by_class[cl])} candidates")

# ── 5. Load recheck queue ──
print("\n" + "=" * 70)
print("STEP 3: RECHECK TASKS")
print("=" * 70)
with open(os.path.join(RUN_DIR, "recheck_queue.json"), "r", encoding="utf-8") as f:
    recheck = json.load(f)
print(json.dumps(recheck, indent=2, ensure_ascii=False)[:3000])
print(f"\nTotal recheck tasks: {len(recheck)}")

# ── 6. Identify a recheck task that may be convertible to class 8 L3 ──
print("\n" + "=" * 70)
print("STEP 3b: Could any RECHECK task fill the shortage?")
print("=" * 70)
for t in recheck:
    cl = t.get("classlevel")
    tl = t.get("target_level")
    oid = t.get("original_id", "?")
    issues = t.get("issues", [])
    print(f"  ID={oid} class={cl} target={tl} issues={issues}")
    if cl == 8 and tl == "L3":
        print(f"    *** THIS COULD DIRECTLY FILL THE SHORTAGE ***")
    elif tl != "L3":
        print(f"    -> target_level is {tl}, not L3. Changing level would violate pipeline integrity.")

# ── 7. Summary ──
print("\n" + "=" * 70)
print("DIAGNOSIS SUMMARY")
print("=" * 70)
print(f"Shortage cell: class=8, target_level=L3")
print(f"  Quota: {shortage['shortages'][0]['quota']}")
print(f"  Actual: {shortage['shortages'][0]['actual']}")
print(f"  Shortage: {shortage['shortages'][0]['shortage']}")
print(f"")
print(f"Reserve for cell: {len(reserve_cell)} candidates")
print(f"")
print(f"RECHECK tasks: {len(recheck)}")
recheck_l3 = [t for t in recheck if t.get("target_level") == "L3"]
print(f"RECHECK with L3 target: {len(recheck_l3)}")
print(f"")
if len(reserve_cell) == 0 and len(recheck_l3) == 0:
    print("CONCLUSION: No reserve or recheck candidates available to fill shortage.")
    print("Need to generate 1 new task via DeepSeek Reasoner (STEP 4).")
elif len(reserve_cell) > 0:
    print(f"CONCLUSION: {len(reserve_cell)} reserve candidate(s) available for cell (8, L3).")
    print("Proceed with 12-point validation (STEP 2).")
else:
    print("CONCLUSION: Need to evaluate options.")
