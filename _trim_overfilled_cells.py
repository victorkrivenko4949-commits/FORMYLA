#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Trim overfilled cells by evaluating task quality and removing the worst ones.

For each (level, grade, topic) cell that has more than TARGET (5) tasks:
  1. Score each task on quality criteria
  2. Sort by score (ascending — worst first)
  3. Remove the lowest-scoring tasks until count = TARGET
  4. Report which IDs were removed

Quality criteria (each 0-1, total 0-3):
  - STATEMENT_SCORE:   has statement, not empty/minimal
  - ANSWER_SCORE:      has answer, not empty
  - SOLUTION_SCORE:    has solution, length-based quality
  - SOLUTION_DEPTH:    solution has mathematical substance (longer + structured)

Usage:
  python _trim_overfilled_cells.py              # dry-run by default
  python _trim_overfilled_cells.py --apply      # actually remove tasks
  python _trim_overfilled_cells.py --target 5   # keep 5 per cell (default)
  python _trim_overfilled_cells.py --levels 1 2 # only L1, L2
"""

import json
import argparse
import sys
import os
from collections import defaultdict

DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
BACKUP_DIR = "backups"
TARGET = 5  # desired max tasks per cell


def get_fingerprint(text: str) -> str:
    """Normalize text for duplicate detection."""
    text = text.lower().strip()
    # Remove non-alphanumeric chars (keep spaces and common math symbols)
    import re
    text = re.sub(r'[^\w\sа-яё+\-*/^=<>()\[\]{}]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def score_task(task: dict) -> float:
    """
    Score a single task on quality criteria.
    Returns a float score where higher = better quality.
    """
    scores = []

    # 1. STATEMENT SCORE (0-1)
    stmt = (task.get('statement') or '').strip()
    if not stmt:
        scores.append(0.0)
    elif len(stmt) < 20:
        scores.append(0.2)  # too short, likely incomplete
    elif len(stmt) < 50:
        scores.append(0.5)
    elif len(stmt) < 100:
        scores.append(0.8)
    else:
        scores.append(1.0)

    # 2. ANSWER SCORE (0-1)
    ans = (task.get('answer') or '').strip()
    if not ans:
        scores.append(0.0)
    elif len(ans) < 5:
        scores.append(0.3)  # minimal answer
    elif len(ans) < 20:
        scores.append(0.6)
    else:
        scores.append(1.0)

    # 3. SOLUTION SCORE (0-1)
    sol = (task.get('solution') or '').strip()
    if not sol:
        scores.append(0.0)
    elif len(sol) < 30:
        scores.append(0.1)  # too short to be useful
    elif len(sol) < 100:
        scores.append(0.4)
    elif len(sol) < 300:
        scores.append(0.7)
    else:
        scores.append(1.0)

    # 4. SOLUTION DEPTH (0-1) — solution has mathematical substance
    if sol:
        # Check for LaTeX math expressions
        has_math = '\\\\(' in sol or '\\[' in sol or '$' in sol or \
                   any(cmd in sol for cmd in ['sqrt', 'frac', 'sum_', 'int_', 'lim_',
                                               'Rightarrow', 'rightarrow', 'geq', 'leq'])
        # Check for numbered steps
        has_steps = any(f'{i}.' in sol for i in range(1, 10)) or \
                    any(f'{i})' in sol for i in range(1, 10))
        # Check for reasoning indicators
        has_reasoning = any(word in sol.lower() for word in [
            'следовательно', 'поэтому', 'отсюда', 'тогда', 'если', 'значит',
            'получаем', 'найдем', 'рассмотрим', 'пусть', 'допустим',
            'since', 'therefore', 'hence', 'thus', 'then', 'consider',
            'let', 'suppose', 'assume', 'we have', 'we get', 'implies'
        ])

        depth_score = 0.0
        if has_math:
            depth_score += 0.4
        if has_steps:
            depth_score += 0.3
        if has_reasoning:
            depth_score += 0.3
        scores.append(min(depth_score, 1.0))
    else:
        scores.append(0.0)

    # Weighted average — statement and solution are most important
    weights = [0.25, 0.15, 0.35, 0.25]
    total = sum(s * w for s, w in zip(scores, weights))

    # Penalty for extremely low-quality (missing critical fields)
    if not stmt or not sol or not ans:
        total *= 0.5

    return round(total, 4)


def get_overfilled_cells(tasks, target=TARGET):
    """Group tasks by (level, grade, topic) and find cells with count > target."""
    by_cell = defaultdict(list)
    for t in tasks:
        level = t.get('level')
        grade = t.get('grade')
        topic = t.get('topic', '')
        cell_key = (level, grade, topic)
        by_cell[cell_key].append(t)

    overfilled = []
    for cell_key, cell_tasks in by_cell.items():
        n = len(cell_tasks)
        if n > target:
            excess = n - target
            overfilled.append({
                'cell_key': cell_key,
                'level': cell_key[0],
                'grade': cell_key[1],
                'topic': cell_key[2],
                'count': n,
                'target': target,
                'excess': excess,
                'tasks': cell_tasks,
            })
    overfilled.sort(key=lambda c: (-c['level'], -c['excess'], c['topic']))
    return overfilled


def score_and_rank_cell(cell: dict) -> list:
    """
    Score all tasks in a cell, return sorted list of (task, score) ascending.
    """
    scored = []
    for t in cell['tasks']:
        s = score_task(t)
        scored.append((s, t))
    scored.sort(key=lambda x: x[0])  # ascending = worst first
    return scored


def generate_removal_plan(cells, target=TARGET) -> list:
    """
    For each overfilled cell, determine which tasks to remove.
    Returns list of dicts with removal details.
    """
    plan = []
    for cell in cells:
        scored = score_and_rank_cell(cell)
        keep_count = target
        excess = cell['excess']

        to_keep = scored[-keep_count:] if keep_count > 0 else []
        to_remove = scored[:excess]

        # Sort removed tasks by task ID for readability
        to_remove.sort(key=lambda x: x[1].get('id', 0))

        plan.append({
            'cell_key': cell['cell_key'],
            'cell_label': f"L{cell['level']}|{cell['grade']}|{cell['topic']}",
            'count': cell['count'],
            'target': target,
            'excess': excess,
            'to_remove': [{'id': t.get('id'), 'score': s,
                           'stmt_len': len(t.get('statement','') or ''),
                           'sol_len': len(t.get('solution','') or ''),
                           'ans_len': len(t.get('answer','') or '')}
                          for s, t in to_remove],
            'to_keep_scores': [s for s, _ in to_keep],
            'min_keep_score': min(s for s, _ in to_keep) if to_keep else 0,
            'max_remove_score': max(s for s, _ in to_remove) if to_remove else 0,
        })

    return plan


def apply_removal_plan(db: list, plan: list) -> tuple:
    """
    Remove tasks from db according to plan.
    Returns (new_db, removed_count, removed_ids).
    """
    remove_ids = set()
    for entry in plan:
        for item in entry['to_remove']:
            remove_ids.add(item['id'])

    new_db = [t for t in db if t.get('id') not in remove_ids]
    removed_count = len(db) - len(new_db)
    return new_db, removed_count, sorted(remove_ids)


def print_report(plan, total_removed, removed_ids):
    """Print a detailed report of what was removed."""
    total_before = sum(c['count'] for c in plan)
    total_after = total_before - total_removed

    print("=" * 80)
    print("OVERFILL CELL TRIMMING REPORT")
    print("=" * 80)
    print(f"Total overfilled cells: {len(plan)}")
    print(f"Total tasks before:    {total_before}")
    print(f"Total tasks removed:   {total_removed}")
    print(f"Total tasks after:     {total_after}")
    print(f"Target per cell:       {plan[0]['target'] if plan else 'N/A'}")
    print("=" * 80)

    for entry in plan:
        print(f"\n[CELL] {entry['cell_label']}")
        print(f"   Count: {entry['count']} → {entry['target']} "
              f"(remove {entry['excess']})")
        print(f"   Min keep score: {entry['min_keep_score']:.4f} | "
              f"Max remove score: {entry['max_remove_score']:.4f}")

        if entry['to_remove']:
            print(f"   Removed IDs: {[x['id'] for x in entry['to_remove']]}")
            for item in entry['to_remove']:
                print(f"     ID={item['id']:<8} score={item['score']:.4f}  "
                      f"stmt={item['stmt_len']}ch  sol={item['sol_len']}ch  "
                      f"ans={item['ans_len']}ch")

    print(f"\n{'=' * 80}")
    print(f"TOTAL REMOVED IDs ({len(removed_ids)}): {removed_ids}")
    print(f"{'=' * 80}")


def main():
    parser = argparse.ArgumentParser(
        description="Trim overfilled cells by removing worst tasks"
    )
    parser.add_argument('--apply', action='store_true',
                        help='Actually remove tasks (default: dry-run)')
    parser.add_argument('--target', type=int, default=TARGET,
                        help=f'Max tasks per cell (default: {TARGET})')
    parser.add_argument('--levels', type=int, nargs='+', default=[1, 2, 3],
                        help='Levels to process (default: 1 2 3)')
    parser.add_argument('--backup', action='store_true', default=True,
                        help='Create backup before applying (default: True)')
    args = parser.parse_args()

    target = args.target
    levels = set(args.levels)

    # Load DB
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    print(f"Loading DB from {DB_PATH}...")
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        db = json.load(f)
    print(f"Loaded {len(db)} tasks total")

    # Filter by level
    filtered = [t for t in db if t.get('level') in levels]
    print(f"Filtered to levels {sorted(levels)}: {len(filtered)} tasks")

    # Find overfilled cells
    cells = get_overfilled_cells(filtered, target)
    print(f"Found {len(cells)} overfilled cells (count > {target})")

    if not cells:
        print("No overfilled cells to trim. Exiting.")
        # Also check if we have cells that EXACTLY match target
        exact = [c for c in get_overfilled_cells(filtered, target - 1)
                 if c['count'] == target]
        if exact:
            print(f"(Cells with exactly {target} tasks: {len(exact)} — they're fine.)")
        sys.exit(0)

    # Print summary of all overfilled cells
    print(f"\nOverfilled cells breakdown:")
    for c in cells:
        print(f"  L{c['level']}|{c['grade']}|{c['topic'][:50]} "
              f"= {c['count']} (excess {c['excess']})")

    # Build removal plan
    plan = generate_removal_plan(cells, target)

    # Calculate totals
    total_removed = sum(len(e['to_remove']) for e in plan)
    all_removed_ids = []
    for e in plan:
        all_removed_ids.extend(item['id'] for item in e['to_remove'])
    all_removed_ids.sort()

    # Print report
    print_report(plan, total_removed, all_removed_ids)

    # Apply or dry-run
    if args.apply:
        print(f"\n{'=' * 80}")
        print("APPLYING CHANGES...")

        # Create backup
        if args.backup:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(
                BACKUP_DIR,
                f"adaptive_full_before_trim_{ts}.json"
            )
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            print(f"Backup saved to {backup_path}")

        new_db, removed_count, removed_ids = apply_removal_plan(db, plan)
        print(f"Removed {removed_count} tasks. New total: {len(new_db)}")

        # Write updated DB
        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_db, f, ensure_ascii=False, indent=2)
        print(f"Updated DB written to {DB_PATH}")

        # Write removal log
        log_path = "trim_overfilled_log.json"
        log_entry = {
            'timestamp': __import__('datetime').datetime.now().isoformat(),
            'target_per_cell': target,
            'levels_processed': sorted(levels),
            'cells_trimmed': len(plan),
            'tasks_removed': removed_count,
            'removed_ids': removed_ids,
            'cells': [
                {
                    'cell': e['cell_label'],
                    'count_before': e['count'],
                    'count_after': e['target'],
                    'removed_ids': [x['id'] for x in e['to_remove']],
                }
                for e in plan
            ]
        }

        # Append to existing log if present
        existing_logs = []
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    existing_logs = json.load(f)
                    if not isinstance(existing_logs, list):
                        existing_logs = [existing_logs]
            except Exception:
                existing_logs = []
        existing_logs.append(log_entry)

        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(existing_logs, f, ensure_ascii=False, indent=2)
        print(f"Removal log saved to {log_path}")

        print("DONE.")
    else:
        print(f"\n{'=' * 80}")
        print("DRY-RUN MODE — no changes made.")
        print(f"Run with --apply to execute: python _trim_overfilled_cells.py --apply")
        print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
