# -*- coding: utf-8 -*-
"""Task 1 diagnosis: allowed_difficulty() anatomy and exhaustion analysis."""
import os, sys, json
os.chdir(r'c:\Users\Redmi\Desktop\Новая папка (2)')
sys.path.insert(0, '.')

from app import app, db
from models import AdaptiveTask
from collections import Counter

with app.app_context():
    # ===================================================================
    # PART A: Show the function source with line numbers
    # ===================================================================
    print("=" * 70)
    print("A. allowed_difficulty() — SOURCE CODE (services/level_engine.py)")
    print("=" * 70)
    with open('services/level_engine.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i in range(250, 274):
        print(f"{i+1:4d}: {lines[i].rstrip()}")

    print()
    print("=" * 70)
    print("B. FIVE_POINT_MAP (services/level_engine.py:38-44)")
    print("=" * 70)
    # It maps 1->[1], 2->[2], 3->[3], 4->[4], 5->[5]
    from services.level_engine import FIVE_POINT_MAP
    for k, v in sorted(FIVE_POINT_MAP.items()):
        print(f"  {k} -> {v}")

    # ===================================================================
    # PART C: Table: which levels are available for mu from 1.0 to 5.0
    #         and sigma 1.5, 1.0, 0.5, 0.35
    #
    # NOTE: allowed_difficulty() does NOT use sigma — it only uses
    # round(mu) to pick a single level_5, then maps via FIVE_POINT_MAP.
    # Sigma has zero influence on band selection.
    # ===================================================================
    print()
    print("=" * 70)
    print("C. TABLE: allowed_difficulty(round(mu), 'formyla_L1_L5_TOP5')")
    print("    Sigma is NOT consulted — band is PURELY round(mu) -> single level")
    print("=" * 70)
    print(f"{'mu':>6}  {'round':>6}  {'allowed_levels':>20}")
    print("-" * 45)
    from services.level_engine import allowed_difficulty
    for mu in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
        rounded = max(1, min(5, round(mu)))
        allowed = allowed_difficulty(rounded, 'formyla_L1_L5_TOP5')
        print(f"{mu:6.1f}  {rounded:6d}  {str(allowed):>20}")

    # Answer the direct question
    print()
    print("=" * 70)
    print("D. DIRECT ANSWER: start mu=3.0, sigma=1.5 -> how many levels?")
    print("=" * 70)
    rounded = max(1, min(5, round(3.0)))
    allowed = allowed_difficulty(rounded, 'formyla_L1_L5_TOP5')
    print(f"  round(3.0) = {rounded}")
    print(f"  allowed_difficulty({rounded}, ...) = {allowed}")
    print(f"  ==> EXACTLY {len(allowed)} LEVEL(S) available: {allowed}")
    print(f"  Sigma=1.5 is IRRELEVANT to band selection.")

    # ===================================================================
    # PART E: How many tasks physically exist in this band for grade 9?
    # ===================================================================
    print()
    print("=" * 70)
    print("E. GRADE 9 TASK COUNTS by difficulty_level (formyla_L1_L5_TOP5)")
    print("=" * 70)
    # Total in pool
    total_pool = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 9,
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
        AdaptiveTask.task_text.isnot(None),
        AdaptiveTask.task_text != '',
    ).count()
    print(f"  Total valid grade-9 tasks: {total_pool}")

    # Per level
    for lvl in range(1, 6):
        cnt = AdaptiveTask.query.filter(
            AdaptiveTask.class_level == 9,
            AdaptiveTask.difficulty_level == lvl,
            AdaptiveTask.correct_answer.isnot(None),
            AdaptiveTask.correct_answer != '',
            AdaptiveTask.task_text.isnot(None),
            AdaptiveTask.task_text != '',
        ).count()
        print(f"    Level {lvl}: {cnt} tasks")

    # Also check non-formyla sources
    from sqlalchemy import or_
    non_formyla = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 9,
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
        AdaptiveTask.task_text.isnot(None),
        AdaptiveTask.task_text != '',
        or_(AdaptiveTask.source == None, AdaptiveTask.source != 'formyla_anchors'),
    ).count()
    print(f"  Total non-anchor grade-9 tasks: {non_formyla}")

    # ===================================================================
    # PART F: Why exhaust after day 1?
    # Student starts at mu=3.0, sigma=1.5 -> round(mu)=3 -> allowed=[3]
    # Each day we want 5 (or 10) tasks.
    # With only level 3 available, how many unique tasks can we serve?
    # ===================================================================
    print()
    print("=" * 70)
    print("F. EXHAUSTION ANALYSIS for fictitious grade-9 student")
    print("   mu=3.0 sigma=1.5 -> round(mu)=3 -> allowed_levels=[3]")
    print("=" * 70)

    l3_tasks = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 9,
        AdaptiveTask.difficulty_level == 3,
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
        AdaptiveTask.task_text.isnot(None),
        AdaptiveTask.task_text != '',
    ).count()
    print(f"  Total grade-9 level-3 tasks: {l3_tasks}")

    # But also need to consider sections
    # How many tasks per section at level 3, grade 9?
    print()
    print("  Level-3 tasks by section (topic classification):")
    from services.daily_task_rotation import _classify_section, _normalize_section, CANONICAL_SECTIONS
    l3_all = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 9,
        AdaptiveTask.difficulty_level == 3,
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
        AdaptiveTask.task_text.isnot(None),
        AdaptiveTask.task_text != '',
    ).all()
    by_sec = Counter()
    for t in l3_all:
        sec = _classify_section(t)
        by_sec[sec] += 1
    for sec in CANONICAL_SECTIONS:
        print(f"    {sec}: {by_sec.get(sec, 0)}")

    # What about the LIMIT 500 in _pick_tasks_for_section?
    # The query has .limit(500), then filters by section and seen_ids.
    # If a section has few tasks and other sections eat the limit,
    # the section may get NOTHING.
    print()
    print("  CRITICAL INSIGHT:")
    print("  _pick_tasks_for_section() queries with .limit(500) then")
    print("  filters by _classify_section IN MEMORY. If the first 500")
    print("  rows are mostly algebra/geometry, logic/combinatorics/number_theory")
    print("  get ZERO candidates. The loop then removes the empty section")
    print("  and tries the next. If ALL sections become empty, we get nothing.")
    print()
    print(f"  Day 1: need {5} tasks from allowed_levels=[3].")
    print(f"  With only {l3_tasks} level-3 tasks total,")
    print(f"  and the 500-row limit per query,")
    print(f"  after exhausting visible tasks in the first query window,")
    print(f"  the remaining sections return empty -> exhaustion.")

    # Let's simulate: how many days can we serve with allowed_levels=[3]?
    print()
    daily_need = 5  # default
    total_l3 = l3_tasks
    max_days = total_l3 // daily_need
    print(f"  Theoretical max days with level-3 only: {max_days} days")
    print(f"  (ignoring section distribution and LIMIT 500)")
    print()
    print(f"  With LIMIT 500 per query, the engine sees at most 500 tasks")
    print(f"  per call. After section filtering, a section may get 0.")
    print(f"  Real exhaustion can happen in < 5 days even with {total_l3} tasks.")

    # Also check: what if we expand to levels [2,3,4]?
    print()
    print("=" * 70)
    print("G. WHAT IF we expand band to [2,3,4] for grade 9?")
    print("=" * 70)
    expanded = AdaptiveTask.query.filter(
        AdaptiveTask.class_level == 9,
        AdaptiveTask.difficulty_level.in_([2, 3, 4]),
        AdaptiveTask.correct_answer.isnot(None),
        AdaptiveTask.correct_answer != '',
        AdaptiveTask.task_text.isnot(None),
        AdaptiveTask.task_text != '',
    ).count()
    print(f"  Total grade-9 tasks levels 2-4: {expanded}")
    print(f"  That's {expanded // daily_need} days at {daily_need}/day")
    print()
    print("  CONCLUSION: FIVE_POINT_MAP 1->[1] mapping is the ROOT CAUSE.")
    print("  Each mu maps to exactly ONE difficulty_level.")
    print("  When that single level runs out in visible query results,")
    print("  the pipeline returns empty — even though adjacent levels have tasks.")

print()
print("=" * 70)
print("DIAGNOSIS COMPLETE")
print("=" * 70)
