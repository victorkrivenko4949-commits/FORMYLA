#!/usr/bin/env python3
"""
Phase 2: Fill incomplete L1-L3 cells in the 5-level FORMULA database.

Reads from Downloads, writes updated files back to Downloads.
"""
import json
import copy
import os
from collections import defaultdict

DOWN = 'C:/Users/Victor/Downloads'
MAIN_PATH = DOWN + '/final_clean_dataset_5levels.json'
RESERVE_PATH = DOWN + '/final_clean_dataset_5levels_reserve.json'
REPORT_PATH = DOWN + '/final_clean_dataset_5levels_L1_L3_fill_report.md'

def load():
    main = json.load(open(MAIN_PATH, 'r', encoding='utf-8'))
    reserve = json.load(open(RESERVE_PATH, 'r', encoding='utf-8'))
    return main, reserve

def save(main, reserve):
    json.dump(main, open(MAIN_PATH, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    json.dump(reserve, open(RESERVE_PATH, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)

def build_cell_dict(tasks, diffs=(1,2,3)):
    """Return { (grade, method_code, difficulty): [task, ...] } for given diffs."""
    d = defaultdict(list)
    for t in tasks:
        if t['difficulty'] in diffs:
            key = (t['grade'], t['method_code'], t['difficulty'])
            d[key].append(t)
    return d

def task_completeness_score(t):
    """Score 0-3 for non-empty task_text, correct_answer, solution."""
    s = 0
    if t.get('task_text') and len(t['task_text'].strip()) > 10:
        s += 1
    if t.get('correct_answer') and len(t['correct_answer'].strip()) > 0:
        s += 1
    if t.get('solution') and len(t['solution'].strip()) > 10:
        s += 1
    return s

def task_reliability_score(t):
    """Score based on status."""
    status = t.get('status', '')
    order = {'keep': 3, 'fixed': 2, 'moved_level': 1, 'olympiad_import': 1, 'imported': 0, 'generated': 0}
    return order.get(status, 0)

def task_quality_score(t):
    """Combined quality metric for sorting."""
    comp = task_completeness_score(t)
    rel = task_reliability_score(t)
    text_len = len((t.get('task_text') or '').strip())
    # Avoid very short/garbage texts
    if text_len < 20:
        comp = max(0, comp - 1)
    has_source = 1 if t.get('audit_note') and len(t['audit_note'].strip()) > 5 else 0
    return (comp, rel, has_source, text_len)

def text_normalize(s):
    """Normalize text for similarity comparison."""
    if not s:
        return ''
    import re
    s = s.lower()
    s = re.sub(r'\s+', ' ', s)
    s = s.replace('$$', '$').replace('\[', '$').replace('\]', '$')
    s = re.sub(r'\\displaystyle\s*', '', s)
    s = re.sub(r'\\quad\s*', ' ', s)
    s = re.sub(r'\\,', '', s)
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = re.sub(r'[^a-zа-яё0-9\s+\-*/=(){}[\]^_$]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def text_similarity(t1, t2):
    """Return a similarity ratio 0-1 between two task texts."""
    a = text_normalize(t1.get('task_text', ''))
    b = text_normalize(t2.get('task_text', ''))
    if not a or not b:
        return 0
    # Simple word-overlap Jaccard
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0
    return len(wa & wb) / len(wa | wb)

def has_technical_issues(t):
    """Check if task has technical problems."""
    text = t.get('task_text', '') or ''
    ans = t.get('correct_answer', '') or ''
    sol = t.get('solution', '') or ''
    # Check for stub/placeholder content
    stubs = ['task_text_', 'template_', 'TODO', 'FIXME', 'xxx']
    for stub in stubs:
        if stub in text.lower() or stub in ans.lower() or stub in sol.lower():
            return True
    return False

def analyze(main, reserve):
    """Analyze current state and return all structures needed."""
    cells_main = build_cell_dict(main)
    cells_reserve = build_cell_dict(reserve)

    # Incomplete cells (0-4 tasks)
    incomplete = {k: v for k, v in cells_main.items() if len(v) < 5}

    # For each incomplete cell, find candidates in reserve
    candidates = {}
    for key in incomplete:
        need = 5 - len(incomplete[key])
        avail = cells_reserve.get(key, [])
        candidates[key] = {'need': need, 'available': avail}

    return cells_main, cells_reserve, incomplete, candidates

def select_best_candidates(main_tasks_in_cell, reserve_candidates, need):
    """
    From reserve_candidates, select up to 'need' best ones.
    Returns (to_promote, to_move_to_reserve, replacements_log)
    to_promote: list of task dicts to add to main
    to_move_to_reserve: list of (task_dict, reason) to move from main to reserve
    """
    if not reserve_candidates:
        return [], [], []

    # Filter out candidates with technical issues
    clean = [t for t in reserve_candidates if not has_technical_issues(t)]

    # Score each candidate
    scored = []
    for t in clean:
        q = task_quality_score(t)
        # Also check similarity to existing main tasks
        max_sim = 0
        for mt in main_tasks_in_cell:
            sim = text_similarity(t, mt)
            max_sim = max(max_sim, sim)
        scored.append((t, q, max_sim))

    # Sort: higher quality first, lower similarity to existing preferred (for diversity)
    scored.sort(key=lambda x: (-x[1][0], -x[1][1], -x[1][2], x[2]))

    to_promote = []
    replacements_log = []
    to_move_to_reserve = []

    promoted_count = 0
    for t, q, max_sim in scored:
        if promoted_count >= need:
            break

        # If very similar to an existing task (>0.75 Jaccard), consider replacement
        if max_sim > 0.85:
            # Find the most similar main task that is WEAKER
            weakest_sim = None
            weakest_idx = None
            for i, mt in enumerate(main_tasks_in_cell):
                sim = text_similarity(t, mt)
                if sim > 0.85:
                    mt_q = task_quality_score(mt)
                    # Replace only if candidate is clearly better
                    if (q[0] > mt_q[0] or (q[0] == mt_q[0] and q[1] > mt_q[1])):
                        if weakest_sim is None or sim > weakest_sim:
                            weakest_sim = sim
                            weakest_idx = i

            if weakest_idx is not None:
                # Replace: move old to reserve, add new
                old_task = main_tasks_in_cell[weakest_idx]
                to_move_to_reserve.append((old_task, 'replaced_by_higher_quality_variant'))
                main_tasks_in_cell[weakest_idx] = t
                replacements_log.append({
                    'retained_id': t['id'],
                    'moved_id': old_task['id'],
                    'grade': t['grade'],
                    'method_code': t['method_code'],
                    'difficulty': t['difficulty'],
                    'reason': 'Better quality variant with similar task pattern'
                })
                promoted_count += 1
                continue
            else:
                # Too similar but not better - skip
                continue

        # Regular promotion
        to_promote.append(t)
        promoted_count += 1

    return to_promote, to_move_to_reserve, replacements_log

def main():
    print("Loading data...")
    main, reserve = load()
    print(f"Main: {len(main)} tasks, Reserve: {len(reserve)} tasks")

    cells_main, cells_reserve, incomplete_before, candidates = analyze(main, reserve)

    total_incomplete_before = len(incomplete_before)
    print(f"\nIncomplete L1-L3 cells before: {total_incomplete_before}")

    # Count by difficulty before
    before_by_diff = {1:0, 2:0, 3:0}
    for k in incomplete_before:
        before_by_diff[k[2]] += 1
    print(f"  L1: {before_by_diff[1]}, L2: {before_by_diff[2]}, L3: {before_by_diff[3]}")

    # Track stats
    total_promoted = 0
    total_replacements = 0
    all_replacements_log = []
    promotions_log = []

    # Track tasks that get moved from main to reserve
    tasks_to_demote = []  # list of (task_dict, reason)

    # Process each incomplete cell
    for key in sorted(incomplete_before.keys(), key=lambda x: (x[2], x[0], x[1])):
        need = candidates[key]['need']
        avail = candidates[key]['available']

        if not avail:
            continue

        main_tasks = cells_main[key]
        to_promote, to_demote, repl_log = select_best_candidates(
            main_tasks, avail, need
        )

        # Log promotions
        for t in to_promote:
            promotions_log.append({
                'id': t['id'],
                'grade': t['grade'],
                'method_code': t['method_code'],
                'difficulty': t['difficulty'],
                'reason': f"Fill cell ({t['grade']}, {t['method_code']}, L{t['difficulty']}) - quality score {task_quality_score(t)}"
            })
            t['compression_status'] = 'main'
            # Remove from reserve list
            reserve_copy = [x for x in reserve if x['id'] != t['id']]
            reserve[:] = reserve_copy
            # Add to main
            main.append(t)

        total_promoted += len(to_promote)

        # Log replacements
        for repl in repl_log:
            all_replacements_log.append(repl)
            # The old task is already in to_demote list
        tasks_to_demote.extend(to_demote)
        total_replacements += len(to_demote)

    # Process demotions (move old tasks from main to reserve)
    for old_task, reason in tasks_to_demote:
        old_task['compression_status'] = 'reserve'
        old_task['reserve_reason'] = reason
        # Remove from main
        main[:] = [t for t in main if t['id'] != old_task['id']]
        # Add to reserve
        reserve.append(old_task)

    # --- REBUILD cells after changes ---
    cells_main_after = build_cell_dict(main)
    cells_reserve_after = build_cell_dict(reserve)
    incomplete_after = {k: v for k, v in cells_main_after.items() if len(v) < 5}

    total_incomplete_after = len(incomplete_after)
    after_by_diff = {1:0, 2:0, 3:0}
    for k in incomplete_after:
        after_by_diff[k[2]] += 1

    # Count cells now at exactly 5
    full_cells_before = {}
    for d in [1,2,3]:
        full_before = sum(1 for k,v in cells_main.items() if k[2]==d and len(v)==5)
        full_after = sum(1 for k,v in cells_main_after.items() if k[2]==d and len(v)==5)
        full_cells_before[d] = full_before
        full_cells_after_d = full_after

    full_after_by_diff = {1:0, 2:0, 3:0}
    for k, v in cells_main_after.items():
        if k[2] in (1,2,3) and len(v) == 5:
            full_after_by_diff[k[2]] += 1

    # --- VERIFICATION ---
    errors = []
    # 1. JSON validity
    # (already loaded)

    # 2. Difficulty range
    for t in main:
        if t['difficulty'] not in (1,2,3,4,5):
            errors.append(f"Task {t['id']} has invalid difficulty {t['difficulty']}")
    for t in reserve:
        if t['difficulty'] not in (1,2,3,4,5):
            errors.append(f"Reserve task {t['id']} has invalid difficulty {t['difficulty']}")

    # 3. No cell > 5 in main
    for k, v in cells_main_after.items():
        if len(v) > 5:
            errors.append(f"Cell {k} has {len(v)} tasks (max 5)")

    # 4. No duplicate IDs in main
    main_ids = [t['id'] for t in main]
    if len(main_ids) != len(set(main_ids)):
        dupes = [x for x in main_ids if main_ids.count(x) > 1]
        errors.append(f"Duplicate IDs in main: {set(dupes)}")

    # 5. No duplicate IDs in reserve
    res_ids = [t['id'] for t in reserve]
    if len(res_ids) != len(set(res_ids)):
        dupes = [x for x in res_ids if res_ids.count(x) > 1]
        errors.append(f"Duplicate IDs in reserve: {set(dupes)}")

    # 6. No overlap
    overlap = set(main_ids) & set(res_ids)
    if overlap:
        errors.append(f"ID overlap between main and reserve: {overlap}")

    # 7. Total integrity
    total_before = sum(len(v) for v in build_cell_dict(main, (1,2,3,4,5)).values())
    # We need to track the ORIGINAL total
    orig_total = 4948  # known from previous run

    total_now = len(main) + len(reserve)
    if total_now != orig_total:
        errors.append(f"Total changed: {total_now} vs original {orig_total}")

    # --- WRITE FILES ---
    print("Saving updated files...")
    save(main, reserve)

    # --- GENERATE REPORT ---
    print("Generating report...")
    report_lines = []
    report_lines.append("# L1-L3 Cell Fill Report")
    report_lines.append("")
    report_lines.append(f"Date: 2026-07-10")
    report_lines.append("")
    report_lines.append("## Summary")
    report_lines.append("")
    report_lines.append(f"- Incomplete L1-L3 cells **before**: {total_incomplete_before}")
    report_lines.append(f"  - L1: {before_by_diff[1]}, L2: {before_by_diff[2]}, L3: {before_by_diff[3]}")
    report_lines.append(f"- Incomplete L1-L3 cells **after**: {total_incomplete_after}")
    report_lines.append(f"  - L1: {after_by_diff[1]}, L2: {after_by_diff[2]}, L3: {after_by_diff[3]}")
    report_lines.append(f"- Tasks promoted from reserve to main: **{total_promoted}**")
    report_lines.append(f"- Replacements in main (weak swapped for better): **{total_replacements}**")
    report_lines.append("")
    report_lines.append("### Cells now at exactly 5 tasks")
    report_lines.append(f"- L1: {full_after_by_diff[1]} cells full")
    report_lines.append(f"- L2: {full_after_by_diff[2]} cells full")
    report_lines.append(f"- L3: {full_after_by_diff[3]} cells full")
    report_lines.append("")

    # Incomplete cells after
    report_lines.append("## Still Incomplete Cells (L1-L3)")
    report_lines.append("")
    report_lines.append("| grade | method_code | difficulty | current_count | missing_to_5 | reserve_candidates_left |")
    report_lines.append("|-------|-------------|------------|--------------|--------------|------------------------|")
    for key in sorted(incomplete_after.keys(), key=lambda x: (x[2], x[0], x[1])):
        g, m, d = key
        cnt = len(incomplete_after[key])
        missing = 5 - cnt
        res_left = len(cells_reserve_after.get(key, []))
        report_lines.append(f"| {g} | {m} | {d} | {cnt} | {missing} | {res_left} |")
    report_lines.append("")

    # Promoted tasks
    report_lines.append("## Promoted Tasks (Reserve -> Main)")
    report_lines.append("")
    report_lines.append("| id | grade | method_code | difficulty | reason |")
    report_lines.append("|----|-------|-------------|------------|--------|")
    for p in promotions_log:
        report_lines.append(f"| {p['id']} | {p['grade']} | {p['method_code']} | {p['difficulty']} | {p['reason']} |")
    report_lines.append("")

    # Replacements
    if all_replacements_log:
        report_lines.append("## Replacements (Swapped in Main)")
        report_lines.append("")
        report_lines.append("| retained_id | moved_to_reserve_id | grade | method_code | difficulty | reason |")
        report_lines.append("|-------------|---------------------|-------|-------------|------------|--------|")
        for r in all_replacements_log:
            report_lines.append(f"| {r['retained_id']} | {r['moved_id']} | {r['grade']} | {r['method_code']} | {r['difficulty']} | {r['reason']} |")
        report_lines.append("")

    # Verification
    report_lines.append("## Verification Checks")
    report_lines.append("")
    if errors:
        report_lines.append("### FAILURES")
        for e in errors:
            report_lines.append(f"- [FAIL] {e}")
    else:
        report_lines.append("- [PASS] Main JSON valid")
        report_lines.append("- [PASS] Reserve JSON valid")
        report_lines.append("- [PASS] All difficulties in range 1-5")
        report_lines.append("- [PASS] No cell in main exceeds 5 tasks")
        report_lines.append("- [PASS] No duplicate IDs in main")
        report_lines.append("- [PASS] No duplicate IDs in reserve")
        report_lines.append("- [PASS] No ID overlap between main and reserve")
        report_lines.append("- [PASS] Total task count unchanged")
    report_lines.append("")

    # Final counts
    report_lines.append("## Final Task Counts")
    report_lines.append("")
    report_lines.append(f"- Main tasks: **{len(main)}**")
    report_lines.append(f"- Reserve tasks: **{len(reserve)}**")
    report_lines.append(f"- Total: **{len(main) + len(reserve)}**")
    report_lines.append("")

    # Cells needing external sources
    report_lines.append("## Cells Requiring External Sources")
    report_lines.append("")
    report_lines.append("These L1-L3 cells still have <5 tasks and no candidates remain in reserve:")
    report_lines.append("")
    report_lines.append("| grade | method_code | difficulty | current_count | missing_to_5 |")
    report_lines.append("|-------|-------------|------------|--------------|--------------|")
    for key in sorted(incomplete_after.keys(), key=lambda x: (x[2], x[0], x[1])):
        g, m, d = key
        cnt = len(incomplete_after[key])
        missing = 5 - cnt
        res_left = len(cells_reserve_after.get(key, []))
        if res_left == 0:
            report_lines.append(f"| {g} | {m} | {d} | {cnt} | {missing} |")
    report_lines.append("")

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    print(f"\nReport written: {REPORT_PATH}")
    print(f"\nFinal stats:")
    print(f"  Main: {len(main)} tasks")
    print(f"  Reserve: {len(reserve)} tasks")
    print(f"  Total: {len(main) + len(reserve)}")
    print(f"  Promoted: {total_promoted}")
    print(f"  Replacements: {total_replacements}")
    print(f"  Incomplete cells remaining: {total_incomplete_after}")
    print(f"  Errors: {len(errors)}")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")

if __name__ == '__main__':
    main()
