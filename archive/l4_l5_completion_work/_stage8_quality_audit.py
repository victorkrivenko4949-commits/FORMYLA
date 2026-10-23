#!/usr/bin/env python
"""Stage 8: Cell quality audit — score all generated tasks, trim over-generated cells to top 5.

1. Load stage6_generated_tasks.json (192 tasks)
2. Compute quality score for each task using compute_quality_score() logic
3. Group by cell_key, sort desc by score
4. For cells with >5 tasks, keep only top 5
5. Save trimmed file and quality audit report
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_PATH = os.path.join(WORK_DIR, "stage6_generated_tasks.json")
REPORT_PATH = os.path.join(WORK_DIR, "stage8_quality_report.txt")


def compute_quality_score(task):
    """Compute quality score for a generated task (mirrors _fill_l4_l5_pipeline.py:778)."""
    sol = task.get('solution', task.get('solution_text', ''))
    stmt = task.get('text', task.get('statement', task.get('task_text', '')))

    # solution_completeness (0.30)
    sol_len = len(sol.strip()) if sol else 0
    sol_completeness = min(1.0, sol_len / 500) if sol_len > 0 else 0.0

    # statement_clarity (0.25)
    stmt_len = len(stmt.strip()) if stmt else 0
    statement_clarity = min(1.0, stmt_len / 200) if stmt_len > 0 else 0.0

    # subtopic_relevance (0.20) - default 0.7 for generated
    subtopic_relevance = 0.7

    # difficulty_confidence (0.15) - no has_valid_solution for generated tasks
    has_valid = task.get('has_valid_solution', task.get('solution_verified', False))
    difficulty_confidence = 0.9 if has_valid else 0.5

    # source_quality (0.10)
    olympiad = task.get('_olympiad', task.get('olympiad', ''))
    if olympiad in ('vsosh', 'region', 'final'):
        source_quality = 1.0
    elif olympiad in ('euler', 'kysh', 'turloomath'):
        source_quality = 0.9
    elif olympiad in ('mos', 'spb', 'mipt'):
        source_quality = 0.8
    elif olympiad:
        source_quality = 0.7
    else:
        source_quality = 0.5

    score = (0.30 * sol_completeness +
             0.25 * statement_clarity +
             0.20 * subtopic_relevance +
             0.15 * difficulty_confidence +
             0.10 * source_quality)
    return round(score * 100, 1)


def main():
    print("=" * 70)
    print("  STAGE 8: CELL QUALITY AUDIT")
    print("=" * 70)

    # 1. Load tasks
    if not os.path.exists(TASKS_PATH):
        print(f"ERROR: {TASKS_PATH} not found")
        sys.exit(1)

    with open(TASKS_PATH, 'r', encoding='utf-8') as f:
        tasks = json.load(f)

    print(f"\nLoaded {len(tasks)} tasks from stage6_generated_tasks.json")

    # 2. Score all tasks
    for t in tasks:
        t['_quality_score'] = compute_quality_score(t)

    # 3. Group by cell_key
    cells = defaultdict(list)
    for t in tasks:
        cells[t['cell_key']].append(t)

    print(f"\n  Total cells: {len(cells)}")
    print(f"  Tasks per cell distribution:")
    counts = Counter(len(v) for v in cells.values())
    for cnt in sorted(counts.keys()):
        print(f"    {cnt} tasks: {counts[cnt]} cells")

    # 4. Identify over-generated cells
    over_generated = {ck: ts for ck, ts in cells.items() if len(ts) > 5}
    under_generated = {ck: ts for ck, ts in cells.items() if len(ts) < 5}
    exact_cells = {ck: ts for ck, ts in cells.items() if len(ts) == 5}

    print(f"\n  Over-generated cells (>5): {len(over_generated)}")
    for ck, ts in sorted(over_generated.items()):
        scores = sorted([(t['_quality_score'], t.get('task_id', ''), t.get('statement', '')[:60])
                         for t in ts], reverse=True)
        print(f"    {ck}: {len(ts)} tasks, scores: {[s[0] for s in scores]}")

    print(f"\n  Exactly 5 tasks cells: {len(exact_cells)}")
    if under_generated:
        print(f"  Under-generated cells (<5): {len(under_generated)} (expected — some cells needed <5)")
        for ck, ts in sorted(under_generated.items()):
            print(f"    {ck}: {len(ts)} tasks")

    # Capture scores for report BEFORE any in-place deletion
    all_scores_before = [t['_quality_score'] for t in tasks]
    avg_score = sum(all_scores_before) / len(all_scores_before) if all_scores_before else 0

    # 5. Trim over-generated cells to top 5
    trimmed = []
    removed = []
    for ck, ts in sorted(cells.items()):
        if len(ts) > 5:
            sorted_ts = sorted(ts, key=lambda t: t['_quality_score'], reverse=True)
            keep = sorted_ts[:5]
            discard = sorted_ts[5:]
            trimmed.extend(keep)
            for t in discard:
                tid = t.get('task_id', '')
                score = t['_quality_score']
                stmt = t.get('statement', '')[:80]
                removed.append({'cell_key': ck, 'task_id': tid, 'score': score, 'statement': stmt})
                print(f"    REMOVED {ck} | task_id={tid} | score={score} | {stmt}...")
        else:
            trimmed.extend(ts)

    # 6. Clean up internal score field before saving
    for t in trimmed:
        del t['_quality_score']

    print(f"\n  --- Summary ---")
    print(f"  Before: {len(tasks)} tasks")
    print(f"  After trim: {len(trimmed)} tasks")
    print(f"  Removed: {len(removed)} tasks (over-generated cells trimmed to top 5)")

    # Verify no cell has >5 tasks (under-generated cells with <5 are expected)
    trimmed_cells = defaultdict(list)
    for t in trimmed:
        trimmed_cells[t['cell_key']].append(t)
    over_violations = {ck: len(ts) for ck, ts in trimmed_cells.items() if len(ts) > 5}
    if over_violations:
        print(f"\n  ERROR: cells still with >5 tasks after trim: {over_violations}")
    else:
        print(f"\n  [OK] No cells with >5 tasks after trim")
    print(f"  Under-generated cells (<5, expected): {len([ck for ck, ts in trimmed_cells.items() if len(ts) < 5])}")

    # 7. Save trimmed file
    with open(TASKS_PATH, 'w', encoding='utf-8') as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved trimmed tasks to {TASKS_PATH}")

    # 8. Write quality report
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 8: CELL QUALITY AUDIT REPORT\n")
        f.write(f"  Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total tasks loaded: {len(tasks)}\n")
        f.write(f"Total cells: {len(cells)}\n")
        f.write(f"Over-generated cells: {len(over_generated)}\n")
        f.write(f"Exactly 5 cells: {len(exact_cells)}\n")
        f.write(f"Under-generated cells: {len(under_generated)}\n")
        f.write(f"Tasks after trim: {len(trimmed)}\n")
        f.write(f"Tasks removed: {len(removed)}\n\n")

        f.write("Tasks per cell distribution:\n")
        for cnt in sorted(counts.keys()):
            f.write(f"  {cnt} tasks: {counts[cnt]} cells\n")
        f.write("\n")

        if removed:
            f.write("Removed tasks (over-generated cells trimmed to top 5):\n")
            f.write(f"{'cell_key':<20} {'task_id':<16} {'score':<8} statement\n")
            f.write("-" * 100 + "\n")
            for r in removed:
                f.write(f"{r['cell_key']:<20} {r['task_id']:<16} {r['score']:<8} {r['statement'][:80]}\n")
            f.write("\n")

        f.write("Quality score distribution:\n")
        f.write(f"  Average score: {avg_score:.1f}\n")
        f.write(f"  Min score: {min(all_scores_before):.1f}\n")
        f.write(f"  Max score: {max(all_scores_before):.1f}\n\n")

        f.write("Cell-level quality summary (before trim):\n")
        f.write(f"{'cell_key':<20} {'count':<6} {'avg_score':<10} {'min_score':<10} {'max_score':<10}\n")
        f.write("-" * 70 + "\n")

        # Re-load fresh data from file to get accurate scores (in-memory was modified in-place)
        if os.path.exists(TASKS_PATH):
            with open(TASKS_PATH, 'r', encoding='utf-8') as f_reload:
                saved_tasks = json.load(f_reload)
        else:
            saved_tasks = trimmed  # fallback

        # Build cell stats from saved (post-trim) file
        saved_cells = defaultdict(list)
        for t in saved_tasks:
            saved_cells[t['cell_key']].append(t)

        for ck in sorted(saved_cells.keys()):
            ts = saved_cells[ck]
            # Recompute scores for report
            scores = [compute_quality_score(t) for t in ts]
            f.write(f"{ck:<20} {len(ts):<6} {sum(scores)/len(scores):<10.1f} {min(scores):<10.1f} {max(scores):<10.1f}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("  END OF STAGE 8 REPORT\n")
        f.write("=" * 70 + "\n")

    print(f"\n  Report written to {REPORT_PATH}")
    print(f"\n{'=' * 70}")
    print(f"  STAGE 8 COMPLETE")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
