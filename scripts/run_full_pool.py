#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrator: dispatches Celery tasks for Daily Olympiad Pool generation.

Usage:
    # Full pool (all 89 combos x 30 days x 2 stacks):
    python scripts/run_full_pool.py --days 30

    # Pilot (1 combo x 7 days x 2 stacks):
    python scripts/run_full_pool.py --pilot

    # Single combo test:
    python scripts/run_full_pool.py --combo vsosh/9/regional --days 1 --stack A
"""
import argparse
import sys
import os
from datetime import date, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_all_combinations():
    """Get all 89 unique combinations from problems_archive."""
    from app import app
    with app.app_context():
        from models import db
        rows = db.session.execute(
            db.text("""
                SELECT DISTINCT olympiad_slug, grade, round
                FROM problems_archive
                ORDER BY olympiad_slug, grade, round
            """)
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]


def get_pilot_combo():
    """Return the pilot combination: vsosh/9/regional."""
    return [("vsosh", 9, "regional")]


def dispatch_tasks(combinations, days, stacks, dry_run=False):
    """Dispatch Celery tasks for all combinations x days x stacks."""
    from tasks.daily_pool import generate_variant_task

    today = date.today()
    total = len(combinations) * days * len(stacks)
    dispatched = 0
    task_ids = []

    print(f"Dispatching {total} tasks:")
    print(f"  Combinations: {len(combinations)}")
    print(f"  Days: {days}")
    print(f"  Stacks: {stacks}")
    print()

    for day_offset in range(days):
        variant_date = (today + timedelta(days=day_offset + 1)).isoformat()

        for slug, grade, round_name in combinations:
            for stack in stacks:
                dispatched += 1
                task_desc = f"{slug}/{grade}/{round_name} {variant_date} stack={stack}"

                if dry_run:
                    print(f"  [{dispatched}/{total}] DRY RUN: {task_desc}")
                else:
                    result = generate_variant_task.delay(
                        slug, grade, round_name, variant_date, stack
                    )
                    task_ids.append(result.id)
                    print(f"  [{dispatched}/{total}] {task_desc} -> {result.id}")

    print(f"\nDispatched {dispatched} tasks.")
    if task_ids:
        print(f"First task ID: {task_ids[0]}")
        print(f"Last task ID: {task_ids[-1]}")
    return task_ids


def check_status(task_ids):
    """Check status of dispatched tasks."""
    from tasks.daily_pool import celery_app
    from celery.result import AsyncResult

    statuses = dict(PENDING=0, STARTED=0, PROGRESS=0, SUCCESS=0, FAILURE=0)
    for tid in task_ids:
        result = AsyncResult(tid, app=celery_app)
        state = result.state
        statuses[state] = statuses.get(state, 0) + 1

    print("\nTask Status Summary:")
    for state, count in sorted(statuses.items()):
        if count > 0:
            print(f"  {state}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Daily Pool Orchestrator")
    parser.add_argument("--pilot", action="store_true",
                        help="Pilot mode: vsosh/9/regional, 7 days, both stacks")
    parser.add_argument("--combo", type=str, default=None,
                        help="Single combo: slug/grade/round")
    parser.add_argument("--days", type=int, default=30,
                        help="Number of days to generate (default: 30)")
    parser.add_argument("--stack", type=str, default=None,
                        help="Stack A or B (default: both)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print tasks without dispatching")
    parser.add_argument("--status", nargs="*",
                        help="Check status of task IDs")

    args = parser.parse_args()

    if args.status is not None:
        check_status(args.status)
        return

    # Determine combinations
    if args.pilot:
        combinations = get_pilot_combo()
        days = 7
        stacks = ["A", "B"]
        print("=== PILOT MODE ===")
    elif args.combo:
        parts = args.combo.split("/")
        if len(parts) != 3:
            print("Error: --combo must be slug/grade/round")
            sys.exit(1)
        combinations = [(parts[0], int(parts[1]), parts[2])]
        days = args.days
        stacks = [args.stack] if args.stack else ["A", "B"]
    else:
        combinations = get_all_combinations()
        days = args.days
        stacks = [args.stack] if args.stack else ["A", "B"]
        print(f"=== FULL POOL MODE ({len(combinations)} combos x {days} days) ===")

    dispatch_tasks(combinations, days, stacks, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
