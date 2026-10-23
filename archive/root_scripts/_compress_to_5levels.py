#!/usr/bin/env python3
"""
Compress FORMULA task database from 8 difficulty levels to 5 levels.

Input:  C:/Users/Victor/Downloads/final_clean_dataset.json  (4948 tasks)
Output: 3 files in Downloads:
  1. final_clean_dataset_5levels.json  (main, <=5 per cell)
  2. final_clean_dataset_5levels_reserve.json  (reserve)
  3. final_clean_dataset_5levels_report.md  (detailed report)

Difficulty mapping: 1+2->1, 3+4->2, 5+6->3, 7->4, 8->5
Cell = (grade, method_code, new_difficulty)
Max 5 tasks per cell in main output.

Author: Roo
"""

import json
import re
import os
from collections import defaultdict, Counter
from copy import deepcopy
from datetime import datetime

# -- Paths -------------------------------------------------------------------
INPUT_PATH = r'C:\Users\Victor\Downloads\final_clean_dataset.json'
OUT_DIR    = r'C:\Users\Victor\Downloads'
MAIN_OUT   = os.path.join(OUT_DIR, 'final_clean_dataset_5levels.json')
RESERVE_OUT = os.path.join(OUT_DIR, 'final_clean_dataset_5levels_reserve.json')
REPORT_OUT = os.path.join(OUT_DIR, 'final_clean_dataset_5levels_report.md')

# -- Difficulty mapping -------------------------------------------------------
OLD_TO_NEW = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 5}
COMPRESSION_RULES = {
    1: "1+2 -> 1",
    2: "3+4 -> 2",
    3: "5+6 -> 3",
    4: "7 -> 4",
    5: "8 -> 5",
}

# -- Status priority (lower = better) -----------------------------------------
STATUS_PRIORITY = {
    'keep': 0,
    'fixed': 1,
    'moved_level': 2,
    'olympiad_import': 2,
    'imported': 3,
    'generated': 3,
}

# -- Helpers -------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """Normalize task_text for deduplication comparison."""
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    s = s.replace('\u201c', "'").replace('\u201d', "'").replace('\u2018', "'").replace('\u2019', "'")
    s = s.replace('\u00ab', "'").replace('\u00bb', "'")
    s = s.replace('$$', '$').replace('\\[', '$').replace('\\]', '$')
    s = s.replace('\\(', '$').replace('\\)', '$')
    s = re.sub(r'\\(displaystyle|textstyle|scriptstyle|limits|nolimits|big|bigg|Big|Bigg)\b', '', s)
    s = re.sub(r'\\(quad|qquad|enspace|thinspace)\b', ' ', s)
    s = re.sub(r'\\(label|tag)\s*\{[^}]*\}', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def difficulty_rule_text(old_d: int) -> str:
    """Describe the compression rule for a given old difficulty."""
    new_d = OLD_TO_NEW.get(old_d, old_d)
    return f"old_level_{old_d}_to_new_level_{new_d}"


def status_sort_key(task: dict):
    """Return a tuple for sorting within a cell (lower = better)."""
    status = task.get('status', '')
    sp = STATUS_PRIORITY.get(status, 99)
    has_solution = 1 if task.get('solution') else 0
    has_answer = 1 if task.get('correct_answer') else 0
    completeness = has_solution + has_answer
    source_bonus = 1 if status in ('keep', 'fixed', 'moved_level', 'olympiad_import') else 0
    text_len = len(task.get('task_text', '') or '')
    return (-sp, -completeness, -source_bonus, -text_len)


def quality_score(task: dict) -> float:
    """Compute a quality score for reporting purposes."""
    score = 0.0
    status = task.get('status', '')
    score += max(0, 10 - STATUS_PRIORITY.get(status, 99)) * 20
    if task.get('solution'): score += 15
    if task.get('correct_answer'): score += 10
    text = task.get('task_text', '') or ''
    score += min(len(text) / 10, 15)
    if task.get('theme'): score += 5
    if task.get('subtopic'): score += 5
    return score


# -- Main processing -----------------------------------------------------------

def main():
    print("=" * 70)
    print("FORMULA Task Database: 8 -> 5 Difficulty Levels Compression")
    print("=" * 70)

    # 1. Load input
    print(f"\n[1] Loading {INPUT_PATH} ...")
    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"    Loaded {len(data)} tasks.")

    # 2. Analyze original distribution
    print(f"\n[2] Analyzing original distribution ...")
    old_diff_dist = Counter(t['difficulty'] for t in data)
    grade_dist = Counter(t['grade'] for t in data)
    method_dist = Counter(t['method_code'] for t in data)
    status_dist = Counter(t.get('status', '') for t in data)
    print(f"    Old difficulty: {dict(sorted(old_diff_dist.items()))}")
    print(f"    Grade: {dict(sorted(grade_dist.items()))}")
    print(f"    Status: {dict(status_dist.items())}")

    # 3. Assign new difficulty and build cells
    print(f"\n[3] Assigning new difficulty levels and building cells ...")
    for t in data:
        old_d = t['difficulty']
        new_d = OLD_TO_NEW.get(old_d)
        if new_d is None:
            print(f"    WARNING: task {t.get('id')} has unexpected difficulty {old_d}, mapping to 5")
            new_d = 5
        t['_new_difficulty'] = new_d
        t['_cell_key'] = (t['grade'], t['method_code'], new_d)

    cells = defaultdict(list)
    for t in data:
        cells[t['_cell_key']].append(t)

    print(f"    Total cells: {len(cells)}")
    cell_sizes = [len(v) for v in cells.values()]
    cells_le5 = sum(1 for s in cell_sizes if s <= 5)
    cells_gt5 = sum(1 for s in cell_sizes if s > 5)
    print(f"    Cells with <=5 tasks: {cells_le5}")
    print(f"    Cells with >5 tasks: {cells_gt5}")
    print(f"    Max tasks in a cell: {max(cell_sizes)}")
    print(f"    Avg tasks per cell: {sum(cell_sizes)/len(cell_sizes):.1f}")

    # Find overloaded cells
    overloaded = [(k, len(v)) for k, v in sorted(cells.items(), key=lambda x: -len(x[1])) if len(v) > 5]
    print(f"    Overloaded cells (>5): {len(overloaded)}")
    for k, v in overloaded[:15]:
        print(f"      grade={k[0]} method={k[1]} new_d={k[2]}: {v} tasks")

    # 4. Sort tasks within each cell by priority
    print(f"\n[4] Sorting tasks within cells by priority ...")
    for cell_key in cells:
        cells[cell_key].sort(key=status_sort_key, reverse=True)

    # 5. Global deduplication
    print(f"\n[5] Performing global deduplication by normalized task_text ...")
    norm_map = defaultdict(list)
    for cell_key, task_list in cells.items():
        for idx, t in enumerate(task_list):
            norm = normalize_text(t.get('task_text', ''))
            norm_map[norm].append((t, cell_key, idx))

    dup_groups = {k: v for k, v in norm_map.items() if len(v) > 1}
    total_duplicates = sum(len(v) - 1 for v in dup_groups.values())
    print(f"    Unique texts: {len(norm_map)}")
    print(f"    Duplicate groups: {len(dup_groups)}")
    print(f"    Total duplicate tasks (to be moved to reserve): {total_duplicates}")

    # Mark dedup clones across ALL tasks
    dedup_clone_ids = set()
    dedup_kept_ids = set()
    for norm, group in dup_groups.items():
        group_sorted = sorted(group, key=lambda x: quality_score(x[0]), reverse=True)
        best_task = group_sorted[0][0]
        dedup_kept_ids.add(best_task.get('id'))
        for clone_task, _, _ in group_sorted[1:]:
            dedup_clone_ids.add(clone_task.get('id'))

    print(f"    Tasks kept as originals: {len(dedup_kept_ids)}")
    print(f"    Tasks marked as clones: {len(dedup_clone_ids)}")

    # 6. Select top 5 per cell, handling dedup
    print(f"\n[6] Selecting top 5 tasks per cell ...")
    main_tasks = []
    reserve_tasks = []
    cell_main_counts = Counter()

    for cell_key, task_list in sorted(cells.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
        selected = 0
        for t in task_list:
            tid = t.get('id')
            t_copy = deepcopy(t)

            # Remove internal fields
            new_d = t_copy.pop('_new_difficulty', None)
            t_copy.pop('_cell_key', None)

            # Overwrite difficulty with the NEW compressed value (1-5)
            # original_difficulty already exists in input and is preserved
            t_copy['difficulty'] = new_d

            # Add new fields
            t_copy['compression_rule'] = difficulty_rule_text(t['difficulty'])

            # Check if this is a dedup clone
            if tid in dedup_clone_ids:
                t_copy['compression_status'] = 'reserve'
                t_copy['reserve_reason'] = 'exact_duplicate'
                reserve_tasks.append(t_copy)
            elif selected < 5:
                # Goes to main
                t_copy['compression_status'] = 'main'
                main_tasks.append(t_copy)
                selected += 1
                cell_main_counts[cell_key] += 1
            else:
                # Cell is full, goes to reserve
                t_copy['compression_status'] = 'reserve'
                t_copy['reserve_reason'] = 'cell_capacity'
                reserve_tasks.append(t_copy)

    print(f"    Main tasks: {len(main_tasks)}")
    print(f"    Reserve tasks: {len(reserve_tasks)}")
    print(f"    Total: {len(main_tasks) + len(reserve_tasks)}")

    # Verify cell counts in main output
    main_cells = Counter()
    for t in main_tasks:
        main_cells[(t['grade'], t['method_code'], t['difficulty'])] += 1
    exceeded = {k: v for k, v in main_cells.items() if v > 5}
    if exceeded:
        print(f"    WARNING: {len(exceeded)} cells have >5 tasks in main output!")
        for k, v in list(exceeded.items())[:10]:
            print(f"      grade={k[0]} method={k[1]} new_d={k[2]}: {v} tasks")
    else:
        print(f"    All cells have <=5 tasks in main output. [OK]")

    # 7. Verify no duplicate IDs within or across files
    print(f"\n[7] Verifying no duplicate IDs ...")
    main_ids = set(t.get('id') for t in main_tasks)
    reserve_ids = set(t.get('id') for t in reserve_tasks)
    main_dup = len(main_tasks) - len(main_ids)
    reserve_dup = len(reserve_tasks) - len(reserve_ids)
    cross_dup = len(main_ids & reserve_ids)
    if main_dup:
        print(f"    WARNING: {main_dup} duplicate IDs within main output!")
    if reserve_dup:
        print(f"    WARNING: {reserve_dup} duplicate IDs within reserve output!")
    if cross_dup:
        print(f"    WARNING: {cross_dup} IDs appear in BOTH main and reserve!")
    if not main_dup and not reserve_dup and not cross_dup:
        print(f"    No duplicate IDs found. [OK]")
        print(f"    Main IDs: {len(main_ids)}, Reserve IDs: {len(reserve_ids)}, Union: {len(main_ids | reserve_ids)}")

    # 8. Verify difficulty range
    print(f"\n[8] Verifying new difficulty levels ...")
    all_new_diffs_main = set(t['difficulty'] for t in main_tasks)
    all_new_diffs_reserve = set(t['difficulty'] for t in reserve_tasks)
    print(f"    Main difficulties: {sorted(all_new_diffs_main)}")
    print(f"    Reserve difficulties: {sorted(all_new_diffs_reserve)}")
    if all_new_diffs_main.issubset({1, 2, 3, 4, 5}):
        print(f"    All main tasks have difficulty 1-5. [OK]")
    else:
        print(f"    WARNING: Unexpected difficulties in main!")
    if all_new_diffs_reserve.issubset({1, 2, 3, 4, 5}):
        print(f"    All reserve tasks have difficulty 1-5. [OK]")
    else:
        print(f"    WARNING: Unexpected difficulties in reserve!")

    # 9. Write output files
    print(f"\n[9] Writing output files ...")

    main_tasks.sort(key=lambda t: (
        t.get('grade', 0),
        t.get('method_code', ''),
        t.get('difficulty', 5),
        t.get('id', 0)
    ))

    reserve_tasks.sort(key=lambda t: (
        t.get('reserve_reason', ''),
        t.get('grade', 0),
        t.get('method_code', ''),
        t.get('difficulty', 5),
        t.get('id', 0)
    ))

    with open(MAIN_OUT, 'w', encoding='utf-8') as f:
        json.dump(main_tasks, f, ensure_ascii=False, indent=2)
    print(f"    Written: {MAIN_OUT} ({len(main_tasks)} tasks)")

    with open(RESERVE_OUT, 'w', encoding='utf-8') as f:
        json.dump(reserve_tasks, f, ensure_ascii=False, indent=2)
    print(f"    Written: {RESERVE_OUT} ({len(reserve_tasks)} tasks)")

    # 10. Generate report
    print(f"\n[10] Generating report ...")

    new_diff_main = Counter()
    for t in main_tasks:
        new_diff_main[t['difficulty']] += 1

    new_diff_reserve = Counter()
    for t in reserve_tasks:
        new_diff_reserve[t['difficulty']] += 1

    grade_main = Counter(t['grade'] for t in main_tasks)
    method_main = Counter(t['method_code'] for t in main_tasks)
    reserve_reasons = Counter(t.get('reserve_reason', '') for t in reserve_tasks)

    cells_final = Counter()
    for t in main_tasks:
        cells_final[(t['grade'], t['method_code'], t['difficulty'])] += 1

    cells_1_2 = sum(1 for v in cells_final.values() if v == 1)
    cells_3_4 = sum(1 for v in cells_final.values() if v in (3, 4))
    cells_5 = sum(1 for v in cells_final.values() if v == 5)
    cells_empty = len(cells) - len(cells_final)

    status_main = Counter(t.get('status', '') for t in main_tasks)

    report_lines = []
    report_lines.append("# FORMULA Task Database: Compression Report")
    report_lines.append("")
    report_lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("")
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append("| Metric | Value |")
    report_lines.append("|--------|-------|")
    report_lines.append("| Input file | `final_clean_dataset.json` |")
    report_lines.append(f"| Input tasks | {len(data)} |")
    report_lines.append(f"| Main output tasks | {len(main_tasks)} |")
    report_lines.append(f"| Reserve output tasks | {len(reserve_tasks)} |")
    report_lines.append(f"| Total output tasks | {len(main_tasks) + len(reserve_tasks)} |")
    report_lines.append(f"| Compression ratio | {len(data) - (len(main_tasks) + len(reserve_tasks))} removed (dedup) |")
    report_lines.append(f"| Total cells | {len(cells)} |")
    report_lines.append(f"| Cells with >=1 task in main | {len(cells_final)} |")
    report_lines.append(f"| Cells with 1-2 tasks | {cells_1_2} |")
    report_lines.append(f"| Cells with 3-4 tasks | {cells_3_4} |")
    report_lines.append(f"| Cells with 5 tasks (full) | {cells_5} |")
    report_lines.append(f"| Empty cells (0 in main) | {cells_empty} |")
    report_lines.append("")

    report_lines.append("## Difficulty Mapping")
    report_lines.append("")
    report_lines.append("| Old Level | New Level | Rule |")
    report_lines.append("|-----------|-----------|------|")
    for old_d in sorted(OLD_TO_NEW):
        report_lines.append(f"| {old_d} | {OLD_TO_NEW[old_d]} | {COMPRESSION_RULES[OLD_TO_NEW[old_d]]} |")
    report_lines.append("")

    report_lines.append("## Difficulty Distribution")
    report_lines.append("")
    report_lines.append("| New Difficulty | Input | Main | Reserve |")
    report_lines.append("|---------------|-------|------|---------|")
    input_new_diff = Counter()
    for t in data:
        nd = OLD_TO_NEW.get(t['difficulty'], 5)
        input_new_diff[nd] += 1
    for nd in range(1, 6):
        report_lines.append(f"| {nd} | {input_new_diff.get(nd, 0)} | {new_diff_main.get(nd, 0)} | {new_diff_reserve.get(nd, 0)} |")
    report_lines.append("")

    report_lines.append("## Grade Distribution (Main)")
    report_lines.append("")
    report_lines.append("| Grade | Tasks |")
    report_lines.append("|-------|-------|")
    for g in sorted(grade_main):
        report_lines.append(f"| {g} | {grade_main[g]} |")
    report_lines.append("")

    report_lines.append("## Method Distribution (Main)")
    report_lines.append("")
    report_lines.append("| Method | Tasks |")
    report_lines.append("|--------|-------|")
    for m, cnt in method_main.most_common():
        report_lines.append(f"| {m} | {cnt} |")
    report_lines.append("")

    report_lines.append("## Status Distribution")
    report_lines.append("")
    report_lines.append("| Status | Input | Main |")
    report_lines.append("|--------|-------|------|")
    for status in ['keep', 'fixed', 'moved_level', 'olympiad_import', 'imported', 'generated']:
        inp_c = status_dist.get(status, 0)
        main_c = status_main.get(status, 0)
        report_lines.append(f"| {status} | {inp_c} | {main_c} |")
    report_lines.append("")

    report_lines.append("## Reserve Breakdown")
    report_lines.append("")
    report_lines.append("| Reason | Count |")
    report_lines.append("|--------|-------|")
    for reason, cnt in reserve_reasons.most_common():
        report_lines.append(f"| {reason} | {cnt} |")
    report_lines.append("")

    report_lines.append("## Deduplication")
    report_lines.append("")
    report_lines.append("| Metric | Value |")
    report_lines.append("|--------|-------|")
    report_lines.append(f"| Duplicate groups | {len(dup_groups)} |")
    report_lines.append(f"| Total duplicate tasks (clones) | {total_duplicates} |")
    report_lines.append(f"| Unique task texts | {len(norm_map)} |")
    report_lines.append("")

    report_lines.append("## Top Overloaded Cells (>5 tasks in input)")
    report_lines.append("")
    report_lines.append("| Grade | Method | New Diff | Input Tasks | Main Tasks | Reserve Tasks |")
    report_lines.append("|-------|--------|----------|-------------|------------|---------------|")
    overloaded_sorted = sorted(overloaded, key=lambda x: -x[1])[:20]
    for (g, mc, nd), inp_cnt in overloaded_sorted:
        main_cnt = cells_final.get((g, mc, nd), 0)
        res_cnt = inp_cnt - main_cnt
        report_lines.append(f"| {g} | {mc} | {nd} | {inp_cnt} | {main_cnt} | {res_cnt} |")
    report_lines.append("")

    report_lines.append("## Quality Statistics (Main)")
    report_lines.append("")
    scores = [quality_score(t) for t in main_tasks]
    report_lines.append("| Metric | Value |")
    report_lines.append("|--------|-------|")
    report_lines.append(f"| Average quality score | {sum(scores)/len(scores):.1f} |")
    report_lines.append(f"| Min quality score | {min(scores):.1f} |")
    report_lines.append(f"| Max quality score | {max(scores):.1f} |")
    report_lines.append(f"| Tasks with solution | {sum(1 for t in main_tasks if t.get('solution'))} |")
    report_lines.append(f"| Tasks with theme | {sum(1 for t in main_tasks if t.get('theme'))} |")
    report_lines.append(f"| Tasks with subtopic | {sum(1 for t in main_tasks if t.get('subtopic'))} |")
    report_lines.append("")

    report_lines.append("## Verification Checks")
    report_lines.append("")
    all_diffs_ok = all(t['difficulty'] in (1, 2, 3, 4, 5) for t in main_tasks + reserve_tasks)
    report_lines.append(f"- All difficulties in 1-5: {'PASS' if all_diffs_ok else 'FAIL'}")
    cell_max = max(cells_final.values()) if cells_final else 0
    report_lines.append(f"- Max tasks per cell in main: {cell_max} {'PASS' if cell_max <= 5 else 'FAIL'}")
    all_ids = [t.get('id') for t in main_tasks]
    all_ids.extend(t.get('id') for t in reserve_tasks)
    report_lines.append(f"- No duplicate IDs across files: {'PASS' if len(all_ids) == len(set(all_ids)) else 'FAIL'}")
    total_out = len(main_tasks) + len(reserve_tasks)
    expected = len(data)
    report_lines.append(f"- Total output = input ({len(data)}): {'PASS' if total_out == expected else f'FAIL (got {total_out})'}")
    report_lines.append("")

    report_text = '\n'.join(report_lines)

    with open(REPORT_OUT, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"    Written: {REPORT_OUT}")

    # -- Final summary --
    print()
    print("=" * 70)
    print("COMPRESSION COMPLETE")
    print("=" * 70)
    print(f"  Main:   {MAIN_OUT} ({len(main_tasks)} tasks)")
    print(f"  Reserve: {RESERVE_OUT} ({len(reserve_tasks)} tasks)")
    print(f"  Report: {REPORT_OUT}")
    print(f"  Total output: {len(main_tasks) + len(reserve_tasks)} tasks")
    print(f"  Dedup clones moved to reserve: {total_duplicates} tasks")
    actual_total = len(main_tasks) + len(reserve_tasks)
    if actual_total == len(data):
        print(f"  Integrity: OK (all {len(data)} tasks accounted for)")
    else:
        print(f"  WARNING: output ({actual_total}) != input ({len(data)})")
    print()


if __name__ == '__main__':
    main()
