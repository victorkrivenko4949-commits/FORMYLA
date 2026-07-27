#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Trim overfilled grade|level|subtopic cells in curated_bank_L1_L5_fixed.json
to exactly 5 tasks per cell (L1-L3 only).

A "cell" = 5 tasks for a specific G{grade}|{level}|{subtopic} combination.
(Fixed: previously grouped by grade|level only — ignoring subtopic,
 which destroyed 14 subtopic cells.)

Strategy:
  1. Group L1-L3 tasks by (grade, level, subtopic) via source_index mapping
  2. For each overfilled cell (>5 tasks):
     - Sort by quality_score DESC, then rank_in_cell ASC (lower = better)
     - Keep top 5
     - Remove excess tasks from the bank
  3. Update total_in_cell_pool for remaining tasks
  4. Create backup before applying

Writes full report to _trim_curated_cells_report.txt (UTF-8).

Usage:
  python _trim_curated_cells.py              # dry-run
  python _trim_curated_cells.py --apply      # actually remove
"""

import json
import argparse
import sys
import os
from collections import defaultdict
from datetime import datetime
import shutil

BANK_PATH = "curated_bank_L1_L5_fixed.json"
SOURCE_PATH = r"C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json"
BACKUP_DIR = "backups"
TARGET = 5
REPORT_PATH = "_trim_curated_cells_report.txt"

# Load source dataset once for subtopic lookup (same pattern as _count_subtopic_cells.py)
_source = None
def _get_source():
    global _source
    if _source is None:
        with open(SOURCE_PATH, 'r', encoding='utf-8') as f:
            _source = json.load(f)
    return _source


def is_l1_l3_task(t: dict) -> bool:
    """Check if task belongs to L1-L3 scope."""
    target_level = t.get('target_level', '')
    level = t.get('level')
    grade = t.get('grade')
    if grade is None:
        return False
    if level not in (1, 2, 3):
        return False
    if target_level not in ('L1', 'L2', 'L3'):
        return False
    return True


def get_cell_key(t: dict) -> str:
    """Get cell key as 'G{grade}|{level}|{subtopic}' via source_index mapping."""
    si = t.get('source_index')
    grade = t.get('grade')
    level = t.get('level')
    subtopic = '__NO_SOURCE__'
    if si is not None:
        source = _get_source()
        if 0 <= si < len(source):
            src = source[si]
            if grade is None and src.get('grade') is not None:
                grade = src['grade']
            subtopic = (src.get('subtopic') or '').strip()
    if not subtopic:
        subtopic = '__NO_SUBTOPIC__'
    return f"G{grade}|{level}|{subtopic}"


def analyze_cells(tasks: list) -> dict:
    """Group L1-L3 tasks by (grade, level, subtopic) cell key."""
    cells = defaultdict(list)
    for t in tasks:
        if is_l1_l3_task(t):
            key = get_cell_key(t)
            cells[key].append(t)
    return dict(cells)


def sort_key(task: dict) -> tuple:
    """Sort key: higher quality_score first, then lower rank_in_cell first."""
    qs = task.get('quality_score')
    if qs is None:
        qs = 0
    rank = task.get('rank_in_cell', 999)
    if rank is None:
        rank = 999
    return (-qs, rank)


def generate_trim_plan(cells: dict, target: int = TARGET) -> tuple:
    """
    Generate a plan for trimming overfilled cells.
    Returns (plan_list, total_overfilled_count).
    """
    plan = []
    total_overfilled = 0

    for cell_key in sorted(cells.keys()):
        tasks = cells[cell_key]
        n = len(tasks)
        if n <= target:
            continue

        excess = n - target
        total_overfilled += 1

        sorted_tasks = sorted(tasks, key=sort_key)
        keep = sorted_tasks[:target]
        remove = sorted_tasks[target:]

        plan.append({
            'cell_key': cell_key,
            'count': n,
            'target': target,
            'excess': excess,
            'keep_ids': [t.get('original_id') for t in keep],
            'remove_ids': [t.get('original_id') for t in remove],
            'remove_details': [
                {
                    'id': t.get('original_id'),
                    'quality_score': t.get('quality_score'),
                    'rank_in_cell': t.get('rank_in_cell'),
                    'topic': t.get('topic', ''),
                    'statement_len': len((t.get('statement') or '').strip()),
                }
                for t in remove
            ],
            'keep_details': [
                {
                    'id': t.get('original_id'),
                    'quality_score': t.get('quality_score'),
                    'rank_in_cell': t.get('rank_in_cell'),
                    'topic': t.get('topic', ''),
                }
                for t in keep
            ],
        })

    return plan, total_overfilled


def apply_trim(bank: list, plan: list) -> tuple:
    """
    Remove excess tasks from bank.
    Returns (new_bank, total_removed, all_removed_ids).
    """
    remove_ids = set()
    for entry in plan:
        for tid in entry['remove_ids']:
            remove_ids.add(tid)

    cell_updated_totals = {}
    for entry in plan:
        cell_updated_totals[entry['cell_key']] = entry['target']

    new_bank = []
    removed_count = 0
    for t in bank:
        tid = t.get('original_id')
        if tid in remove_ids:
            removed_count += 1
            continue
        if is_l1_l3_task(t):
            cell_key = get_cell_key(t)
            if cell_key in cell_updated_totals:
                t['total_in_cell_pool'] = cell_updated_totals[cell_key]
        new_bank.append(t)

    return new_bank, removed_count, sorted(remove_ids)


def generate_report_text(plan, total_overfilled, total_removed, removed_ids, is_dry_run):
    """Generate report text (returns list of strings)."""
    total_before = sum(e['count'] for e in plan)
    total_after = sum(e['target'] for e in plan)

    lines = []
    def w(s=""):
        lines.append(s)

    w("=" * 80)
    w("CURATED BANK CELL TRIMMING REPORT")
    w("=" * 80)
    w(f"Mode:              {'DRY-RUN (no changes)' if is_dry_run else 'APPLIED'}")
    w(f"Overfilled cells:  {total_overfilled}")
    w(f"Total tasks before trimming: {total_before}")
    w(f"Total tasks after trimming:  {total_after}")
    w(f"Total tasks removed:         {total_removed}")
    w(f"Target per cell:             {TARGET}")
    w("=" * 80)
    w("")

    for entry in plan:
        w(f"[CELL] {entry['cell_key']}")
        w(f"  Count: {entry['count']} -> {entry['target']} (remove {entry['excess']})")
        w("")

        w(f"  KEEP ({len(entry['keep_ids'])}):")
        for kd in entry['keep_details']:
            w(f"    {kd['id']}  qs={kd['quality_score']}  rank={kd['rank_in_cell']}  topic={kd['topic'][:50]}")
        w("")

        w(f"  REMOVE ({len(entry['remove_ids'])}):")
        for rd in entry['remove_details']:
            w(f"    {rd['id']}  qs={rd['quality_score']}  rank={rd['rank_in_cell']}  topic={rd['topic'][:50]}  stmt={rd['statement_len']}ch")
        w("")

    w("=" * 80)
    w(f"ALL REMOVED IDs ({len(removed_ids)}):")
    for i in range(0, len(removed_ids), 10):
        w(f"  {', '.join(removed_ids[i:i+10])}")
    w("=" * 80)

    return lines


def create_backup(bank_path: str, backup_dir: str = BACKUP_DIR) -> str:
    """Create timestamped backup."""
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f"curated_bank_before_trim_{timestamp}.json")
    shutil.copy2(bank_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description="Trim overfilled (grade, level, subtopic) cells in curated bank to top 5"
    )
    parser.add_argument('--apply', action='store_true',
                        help='Actually remove tasks (default: dry-run)')
    parser.add_argument('--target', type=int, default=TARGET,
                        help=f'Max tasks per cell (default: {TARGET})')
    args = parser.parse_args()
    target = args.target

    # 1. Load bank
    if not os.path.exists(BANK_PATH):
        print(f"[!] Bank not found: {BANK_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading bank from {BANK_PATH}...")
    with open(BANK_PATH, 'r', encoding='utf-8') as f:
        bank = json.load(f)
    print(f"  Loaded {len(bank)} tasks total")

    # 2. Analyze cells
    cells = analyze_cells(bank)
    print(f"  Found {len(cells)} non-empty (grade, level, subtopic) cells in L1-L3")

    for cell_key in sorted(cells.keys()):
        n = len(cells[cell_key])
        marker = " OVER" if n > target else (" UNDER" if n < target else "")
        print(f"    {cell_key}: {n} tasks{marker}")

    # 3. Generate plan
    plan, total_overfilled = generate_trim_plan(cells, target)
    if not plan:
        print("\nNo overfilled cells to trim. Nothing to do.")
        return

    total_removed = sum(e['excess'] for e in plan)
    all_remove_ids = []
    for e in plan:
        all_remove_ids.extend(e['remove_ids'])
    all_remove_ids.sort()

    # 4. Generate and write report
    report_lines = generate_report_text(
        plan, total_overfilled, total_removed, all_remove_ids,
        is_dry_run=not args.apply
    )

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    print(f"\nFull report written to: {REPORT_PATH}")
    print(f"Summary: {total_overfilled} overfilled cells, {total_removed} tasks to remove")

    # 5. Apply or dry-run
    if args.apply:
        backup_path = create_backup(BANK_PATH)
        print(f"\nBackup saved to: {backup_path}")

        new_bank, actually_removed, removed_ids = apply_trim(bank, plan)
        print(f"Removed {actually_removed} tasks. New bank size: {len(new_bank)}")

        with open(BANK_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_bank, f, ensure_ascii=False, indent=2)
        print(f"Updated bank written to {BANK_PATH}")

        # Save removal log
        log_path = "trim_curated_cells_log.json"
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'target_per_cell': target,
            'cells_trimmed': len(plan),
            'tasks_removed': actually_removed,
            'removed_ids': removed_ids,
            'bank_size_before': len(bank),
            'bank_size_after': len(new_bank),
            'cells': [
                {
                    'cell': e['cell_key'],
                    'count_before': e['count'],
                    'count_after': e['target'],
                    'removed_ids': e['remove_ids'],
                }
                for e in plan
            ],
        }
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False, indent=2)
        print(f"Removal log saved to: {log_path}")

        print("\nDONE.")
    else:
        print(f"\nDRY-RUN MODE - no changes made.")
        print(f"Run with --apply to execute: python _trim_curated_cells.py --apply")


if __name__ == '__main__':
    main()
