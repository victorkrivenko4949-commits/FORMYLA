#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Trim overfilled cells using DeepSeek Reasoner for quality evaluation.

Strategy (hybrid heuristic + Reasoner):
  1. Heuristically pre-score all tasks in each overfilled cell
  2. Send the worst candidates to DeepSeek Reasoner for quality judgment
  3. Reasoner returns IDs of truly bad tasks to remove
  4. If not enough removed, fall back to heuristic: remove lowest-scoring remaining
  5. Keep exactly TARGET (5) tasks per cell

Usage:
  python _trim_with_reasoner.py                # dry-run (simulate only)
  python _trim_with_reasoner.py --apply        # actually remove tasks
  python _trim_with_reasoner.py --target 5     # keep 5 per cell (default)
  python _trim_with_reasoner.py --levels 1 2   # only L1, L2
  python _trim_with_reasoner.py --max-batch 20 # max tasks per Reasoner call
"""

import json
import argparse
import sys
import os
import re
from collections import defaultdict
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError

DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"
BACKUP_DIR = "backups"
TARGET = 5  # desired max tasks per cell
MAX_TASKS_PER_REASONER_CALL = 25  # safety limit for context window


# ──────────────────────────────────────────────
# Heuristic scoring (same as _trim_overfilled_cells.py)
# ──────────────────────────────────────────────

def score_task(task: dict) -> float:
    """Score a single task on quality criteria (0-3 range). Higher = better."""
    score = 0.0

    statement = (task.get('statement') or '').strip()
    answer = (task.get('answer') or '').strip()
    solution = (task.get('solution') or '').strip()

    # --- statement quality (0-1) ---
    if len(statement) >= 50:
        score += 1.0
    elif len(statement) >= 20:
        score += 0.5
    elif len(statement) > 0:
        score += 0.1

    # --- answer quality (0-1) ---
    if len(answer) >= 10:
        score += 1.0
    elif len(answer) >= 3:
        score += 0.5
    elif len(answer) > 0:
        score += 0.1

    # --- solution quality (0-1) ---
    if len(solution) >= 200:
        score += 1.0
    elif len(solution) >= 80:
        score += 0.7
    elif len(solution) >= 30:
        score += 0.4
    elif len(solution) > 0:
        score += 0.1

    # --- solution depth bonus (0-1) ---
    if len(solution) >= 500:
        score += 1.0
    elif len(solution) >= 200:
        score += 0.7
    elif len(solution) >= 80:
        score += 0.4
    elif len(solution) > 0:
        score += 0.2

    # --- LaTeX presence bonus (small) ---
    if re.search(r'\\[a-zA-Z]+', solution or ''):
        score += 0.1
    if re.search(r'\$.*?\$', solution or ''):
        score += 0.1

    return score


# ──────────────────────────────────────────────
# Cell grouping
# ──────────────────────────────────────────────

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


# ──────────────────────────────────────────────
# Reasoner evaluation
# ──────────────────────────────────────────────

def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars, adding '...' if cut."""
    if not text:
        return ''
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + '...'


def _format_task_for_prompt(task: dict) -> str:
    """Format a single task for the Reasoner prompt."""
    tid = task.get('id', '?')
    stmt = _truncate(task.get('statement', '') or '', 300)
    answer = _truncate(task.get('answer', '') or '', 150)
    solution = _truncate(task.get('solution', '') or '', 400)
    return (
        f"ID={tid}\n"
        f"  Statement: {stmt}\n"
        f"  Answer: {answer}\n"
        f"  Solution: {solution[:200]}..."
    )


def build_reasoner_prompt(cell: dict, candidates: list) -> str:
    """
    Build prompt for Reasoner to evaluate candidate tasks.
    candidates: list of (score, task) tuples, worst first.
    """
    level = cell['level']
    grade = cell['grade']
    topic = cell['topic']
    target = cell['target']

    lines = [
        f"You are a math education quality evaluator. Your task is to identify which "
        f"mathematical problems are LOW QUALITY and should be removed from a database.",
        "",
        f"Cell: Level {level}, Grade {grade}, Topic: {topic}",
        f"We need to keep only the best {target} tasks. Below are the WORST-SCORING "
        f"candidates (heuristically scored). Please evaluate each one.",
        "",
        "Quality criteria (low quality = should be removed):",
        "  1. STATEMENT: Is the problem statement unclear, incomplete, or nonsensical?",
        "  2. ANSWER: Is the answer missing, trivial, or nonsensical?",
        "  3. SOLUTION: Is the solution missing, too short, or lacking mathematical reasoning?",
        "  4. DUPLICATE: Is this task essentially a duplicate of another in the list?",
        "  5. RELEVANCE: Is the problem relevant to the topic?",
        "",
        f"There are {len(candidates)} candidate tasks. I need you to identify the WORST ones "
        f"that should be removed. You can mark up to {cell['excess']} tasks for removal.",
        "",
        "Respond ONLY with a JSON object in this exact format:",
        '  {"remove_ids": [list of task IDs to remove]}',
        "",
        "Tasks to evaluate:",
    ]

    for idx, (score, task) in enumerate(candidates, 1):
        lines.append(f"\n--- Task {idx} (heuristic_score={score:.3f}) ---")
        lines.append(_format_task_for_prompt(task))

    lines.append(f"\n--- END OF TASKS ---")
    lines.append("")
    lines.append('Output ONLY a JSON object: {"remove_ids": [id1, id2, ...]}')

    return '\n'.join(lines)


def evaluate_with_reasoner(client: DeepSeekClient, cell: dict,
                           candidates: list) -> list:
    """
    Send candidates to DeepSeek Reasoner for evaluation.
    Returns list of task IDs to remove.
    """
    if not candidates:
        return []

    prompt = build_reasoner_prompt(cell, candidates)

    try:
        content, reasoning = client.generate_with_reasoning(
            prompt=prompt,
            system_prompt=(
                "You are a strict math education quality evaluator. "
                "Respond ONLY with valid JSON."
            ),
            max_tokens=1000,
            return_reasoning=True,
            timeout=120,
        )
    except DeepSeekAPIError as e:
        print(f"  [!] Reasoner API error: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"  [!] Unexpected error: {e}", file=sys.stderr)
        return []

    # Parse JSON from response
    remove_ids = _extract_remove_ids(content)
    if remove_ids is None:
        # Try fallback: maybe reasoning_content has the JSON
        if reasoning:
            remove_ids = _extract_remove_ids(reasoning)
    if remove_ids is None:
        print(f"  [!] Failed to parse Reasoner response: {content[:300]}",
              file=sys.stderr)
        return []

    return remove_ids


def _extract_remove_ids(text: str):
    """Extract remove_ids list from text that may contain JSON."""
    if not text:
        return None
    # Try to find JSON block
    json_match = re.search(r'\{[^{}]*"remove_ids"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            ids = data.get('remove_ids', [])
            if isinstance(ids, list) and all(isinstance(x, (int, str)) for x in ids):
                return [int(x) if isinstance(x, str) and x.isdigit() else x for x in ids]
        except (json.JSONDecodeError, ValueError):
            pass
    # Try to extract IDs with regex fallback
    ids = re.findall(r'\b(\d{4,})\b', text)
    if ids:
        return [int(x) for x in ids]
    return None


# ──────────────────────────────────────────────
# Plan generation
# ──────────────────────────────────────────────

def generate_reasoner_plan(client: DeepSeekClient, cells: list,
                           target=TARGET, max_batch=MAX_TASKS_PER_REASONER_CALL,
                           dry_run=True) -> list:
    """
    For each overfilled cell, use Reasoner + heuristic to determine which tasks to remove.
    Returns list of plan entries.
    """
    plan = []
    total_cells = len(cells)
    total_remove_ids = []

    for idx, cell in enumerate(cells):
        cell_label = f"L{cell['level']}|{cell['grade']}|{cell['topic']}"
        n_tasks = cell['count']
        excess = cell['excess']
        print(f"\n[{idx+1}/{total_cells}] {cell_label}  "
              f"({n_tasks} tasks, excess={excess})")

        # 1. Score all tasks heuristically
        scored = []
        for t in cell['tasks']:
            s = score_task(t)
            scored.append((s, t))
        scored.sort(key=lambda x: x[0])  # ascending = worst first

        # 2. Split: worst candidates + safe keepers
        worst_candidates = scored[:excess]
        safe_keepers = scored[excess:]

        # 3. Send worst candidates to Reasoner (batch if needed)
        remove_ids = []
        remaining_candidates = worst_candidates[:]

        while remaining_candidates:
            batch = remaining_candidates[:max_batch]
            remaining_candidates = remaining_candidates[max_batch:]

            if dry_run:
                print(f"  [dry-run] Would send {len(batch)} tasks to Reasoner")
                # For dry-run, just use heuristic: remove the worst ones
                batch_remove = [t.get('id') for _, t in batch]
                remove_ids.extend(batch_remove)
            else:
                print(f"  Calling Reasoner with {len(batch)} tasks...", end=' ', flush=True)
                batch_remove = evaluate_with_reasoner(client, cell, batch)
                print(f"Reasoner marked {len(batch_remove)} for removal")
                remove_ids.extend(batch_remove)

        # Deduplicate
        remove_ids = list(dict.fromkeys(remove_ids))

        # 4. If Reasoner didn't remove enough, fall back to heuristic
        tasks_removed = len(remove_ids)
        if tasks_removed < excess and not dry_run:
            # Get all tasks not yet marked for removal
            remaining_tasks = [(s, t) for s, t in scored
                               if t.get('id') not in remove_ids]
            need_more = excess - tasks_removed
            # Remove the lowest-scoring remaining
            extra_removals = [t.get('id') for _, t in remaining_tasks[:need_more]]
            remove_ids.extend(extra_removals)
            remove_ids = list(dict.fromkeys(remove_ids))
            print(f"  [heuristic fallback] Added {len(extra_removals)} more")
        elif tasks_removed < excess and dry_run:
            # In dry-run, our 'fake' Reasoner already removes exactly excess
            pass

        # 5. Enforce exactly target count
        remove_ids = remove_ids[:excess]  # at most 'excess' removals

        plan.append({
            'cell_key': cell['cell_key'],
            'cell_label': cell_label,
            'count': n_tasks,
            'target': target,
            'excess': excess,
            'to_remove': remove_ids,
            'removed_count': len(remove_ids),
        })

        total_remove_ids.extend(remove_ids)
        print(f"  -> Will remove {len(remove_ids)} tasks")

    return plan


def generate_heuristic_plan(cells, target=TARGET) -> list:
    """
    Pure heuristic fallback plan (for dry-run or fallback).
    """
    plan = []
    for cell in cells:
        scored = []
        for t in cell['tasks']:
            s = score_task(t)
            scored.append((s, t))
        scored.sort(key=lambda x: x[0])

        to_remove = scored[:cell['excess']]
        remove_ids = [t.get('id') for _, t in to_remove]

        plan.append({
            'cell_key': cell['cell_key'],
            'cell_label': f"L{cell['level']}|{cell['grade']}|{cell['topic']}",
            'count': cell['count'],
            'target': target,
            'excess': cell['excess'],
            'to_remove': remove_ids,
            'removed_count': len(remove_ids),
        })
    return plan


# ──────────────────────────────────────────────
# Apply plan to DB
# ──────────────────────────────────────────────

def apply_removal_plan(db: list, plan: list) -> tuple:
    """Remove tasks from db according to plan. Returns (new_db, removed_count, removed_ids)."""
    remove_ids = set()
    for entry in plan:
        for tid in entry['to_remove']:
            remove_ids.add(tid)

    new_db = [t for t in db if t.get('id') not in remove_ids]
    removed_count = len(db) - len(new_db)
    return new_db, removed_count, sorted(remove_ids)


def print_report(plan, total_removed, removed_ids):
    """Print a detailed report without emoji (Windows-safe)."""
    total_before = sum(c['count'] for c in plan)

    print("=" * 80)
    print("OVERFILL CELL TRIMMING REPORT (DeepSeek Reasoner)")
    print("=" * 80)
    print(f"Total overfilled cells: {len(plan)}")
    print(f"Total tasks before:    {total_before}")
    print(f"Total tasks removed:   {total_removed}")
    print(f"Total tasks after:     {total_before - total_removed}")
    print(f"Target per cell:       {plan[0]['target'] if plan else 'N/A'}")
    print("=" * 80)

    for entry in plan:
        print(f"\n[CELL] {entry['cell_label']}")
        print(f"   Count: {entry['count']} -> {entry['target']} "
              f"(remove {entry['excess']})")
        print(f"   Actually removed: {entry['removed_count']}")
        if entry['to_remove']:
            print(f"   Removed IDs: {entry['to_remove']}")

    print(f"\n{'=' * 80}")
    print(f"TOTAL REMOVED IDs ({len(removed_ids)}): {list(removed_ids)}")
    print(f"{'=' * 80}")


def create_backup(db, backup_dir=BACKUP_DIR):
    """Create a timestamped backup of the DB."""
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f"adaptive_full_{timestamp}_BEFORE_REASONER_TRIM.json")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    return backup_path


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Trim overfilled cells using DeepSeek Reasoner"
    )
    parser.add_argument('--apply', action='store_true',
                        help='Actually remove tasks (default: dry-run)')
    parser.add_argument('--target', type=int, default=TARGET,
                        help=f'Target tasks per cell (default: {TARGET})')
    parser.add_argument('--levels', type=int, nargs='+', default=[1, 2, 3],
                        help='Levels to process (default: 1 2 3)')
    parser.add_argument('--max-batch', type=int, default=MAX_TASKS_PER_REASONER_CALL,
                        help=f'Max tasks per Reasoner call (default: {MAX_TASKS_PER_REASONER_CALL})')
    args = parser.parse_args()

    print("=" * 80)
    print("DeepSeek Reasoner Overfilled Cell Trimmer")
    print("=" * 80)
    print(f"Mode:         {'APPLY (will modify DB)' if args.apply else 'DRY-RUN'}")
    print(f"Target:       {args.target} per cell")
    print(f"Levels:       {args.levels}")
    print(f"Max batch:    {args.max_batch}")
    print(f"DB path:      {DB_PATH}")
    print("=" * 80)

    # 1. Load DB
    if not os.path.exists(DB_PATH):
        print(f"[!] DB not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    print("\nLoading DB...")
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        db = json.load(f)
    print(f"  Loaded {len(db)} tasks")

    # 2. Filter by level
    tasks = [t for t in db if t.get('level') in args.levels]
    print(f"  Filtered to levels {args.levels}: {len(tasks)} tasks")

    # 3. Find overfilled cells
    cells = get_overfilled_cells(tasks, target=args.target)
    print(f"  Found {len(cells)} overfilled cells "
          f"(total tasks in these cells: {sum(c['count'] for c in cells)})")

    if not cells:
        print("\nNo overfilled cells found. Nothing to do.")
        return

    # 4. Generate plan
    if args.apply:
        # Initialize DeepSeek client
        try:
            client = DeepSeekClient()
        except ValueError as e:
            print(f"\n[!] {e}", file=sys.stderr)
            print("Set DEEPSEEK_API_KEY environment variable or create .env file.")
            sys.exit(1)

        print(f"\nGenerating Reasoner-based removal plan...")
        plan = generate_reasoner_plan(
            client, cells,
            target=args.target,
            max_batch=args.max_batch,
            dry_run=False,
        )
    else:
        # Dry-run: use heuristic only (no API calls)
        print(f"\n[Dry-run] Generating heuristic removal plan (no Reasoner calls)...")
        plan = generate_heuristic_plan(cells, target=args.target)

    # 5. Apply plan
    if args.apply:
        print(f"\nApplying removal plan...")
        backup_path = create_backup(db)
        print(f"  Backup saved: {backup_path}")

        new_db, removed_count, removed_ids = apply_removal_plan(db, plan)
        print(f"  Removed: {removed_count} tasks")

        # Save updated DB
        with open(DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_db, f, ensure_ascii=False, indent=2)
        print(f"  Updated DB saved: {DB_PATH}")
        print(f"  New task count: {len(new_db)}")
    else:
        # Dry-run: simulate
        _, removed_count, removed_ids = apply_removal_plan(db, plan)
        print(f"\n[Dry-run] Would remove: {removed_count} tasks")
        print(f"[Dry-run] Remaining:    {len(db) - removed_count} tasks")

    # 6. Print report
    print_report(plan, removed_count, removed_ids)


if __name__ == '__main__':
    main()
