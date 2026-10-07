#!/usr/bin/env python
"""Analyze weak tasks from stage6_generated_tasks.json and save to report."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_PATH = os.path.join(ROOT, "l4_l5_completion_work", "stage6_generated_tasks.json")

with open(GEN_PATH, 'r', encoding='utf-8') as f:
    tasks = json.load(f)

def compute_quality_score(task):
    sol = task.get('solution', task.get('solution_text', ''))
    stmt = task.get('text', task.get('statement', task.get('task_text', '')))
    sol_len = len(sol.strip()) if sol else 0
    sol_completeness = min(1.0, sol_len / 500) if sol_len > 0 else 0.0
    stmt_len = len(stmt.strip()) if stmt else 0
    statement_clarity = min(1.0, stmt_len / 200) if stmt_len > 0 else 0.0
    subtopic_relevance = 0.7
    has_valid = task.get('has_valid_solution', task.get('solution_verified', False))
    difficulty_confidence = 0.9 if has_valid else 0.5
    olympiad = task.get('_olympiad', task.get('olympiad', ''))
    if olympiad in ('vsosh','region','final'):
        source_quality = 1.0
    elif olympiad in ('euler','kysh','turloomath'):
        source_quality = 0.9
    elif olympiad in ('mos','spb','mipt'):
        source_quality = 0.8
    elif olympiad:
        source_quality = 0.7
    else:
        source_quality = 0.5
    score = (0.30 * sol_completeness + 0.25 * statement_clarity + 0.20 * subtopic_relevance +
             0.15 * difficulty_confidence + 0.10 * source_quality)
    return round(score * 100, 1)

lines = []
lines.append("=" * 70)
lines.append("  WEAK TASKS ANALYSIS")
lines.append("  Generated: all tasks with quality < 60 and 60-70")
lines.append("=" * 70)

# Group tasks by cell
from collections import defaultdict
cell_groups = defaultdict(list)
for t in tasks:
    cell_groups[t.get("cell_key", "?")].append(t)

# Phase 1: < 60
lines.append("\n" + "=" * 70)
lines.append("  PHASE 1: QUALITY < 60 (25 tasks)")
lines.append("=" * 70)

below_60 = [t for t in tasks if compute_quality_score(t) < 60]
below_60.sort(key=lambda x: compute_quality_score(x))

for t in below_60:
    qs = compute_quality_score(t)
    lines.append(f"\n  task_id: {t.get('task_id','?')}")
    lines.append(f"  cell_key: {t.get('cell_key','?')}")
    lines.append(f"  quality: {qs:.1f}")
    lines.append(f"  grade: {t.get('grade','?')}  level: {t.get('level','?')}")
    lines.append(f"  solution_len: {len(str(t.get('solution','')))}")
    lines.append(f"  statement: {str(t.get('statement',''))[:200]}")

lines.append("\n" + "=" * 70)
lines.append("  PHASE 2: QUALITY 60-70 (38 tasks)")
lines.append("=" * 70)

between_60_70 = [t for t in tasks if 60 <= compute_quality_score(t) < 70]
between_60_70.sort(key=lambda x: compute_quality_score(x))

for t in between_60_70:
    qs = compute_quality_score(t)
    lines.append(f"\n  task_id: {t.get('task_id','?')}")
    lines.append(f"  cell_key: {t.get('cell_key','?')}")
    lines.append(f"  quality: {qs:.1f}")
    lines.append(f"  grade: {t.get('grade','?')}  level: {t.get('level','?')}")
    lines.append(f"  solution_len: {len(str(t.get('solution','')))}")
    lines.append(f"  statement: {str(t.get('statement',''))[:200]}")

lines.append("\n" + "=" * 70)
lines.append("  CELL-LEVEL ANALYSIS")
lines.append("=" * 70)

for ck in sorted(cell_groups):
    scores = [compute_quality_score(t) for t in cell_groups[ck]]
    avg = sum(scores) / len(scores)
    if avg < 70:
        lines.append(f"\n  cell: {ck}")
        lines.append(f"  tasks: {len(cell_groups[ck])}  avg: {avg:.1f}")
        lines.append(f"  scores: {[f'{s:.1f}' for s in scores]}")

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weak_tasks_report.txt")
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Report written to {out_path}", flush=True)
print(f"Total tasks <60: {len(below_60)}", flush=True)
print(f"Total tasks 60-70: {len(between_60_70)}", flush=True)
print(f"Total cells with avg<70: {sum(1 for ck in cell_groups if sum(compute_quality_score(t) for t in cell_groups[ck])/len(cell_groups[ck]) < 70)}", flush=True)
