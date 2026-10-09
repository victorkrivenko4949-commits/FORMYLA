#!/usr/bin/env python
"""Stage 7: Independent verification of generated tasks."""
import json, re, sys
from collections import Counter, defaultdict

def main():
    data = json.load(open('stage6_generated_tasks.json','r',encoding='utf-8'))
    errors = []
    warnings = []
    report = []
    
    def log(msg):
        report.append(msg)
        print(msg)
    
    log("=" * 70)
    log("  STAGE 7: INDEPENDENT VERIFICATION REPORT")
    log("=" * 70)
    log(f"  Total tasks in file: {len(data)}")
    log("")
    
    # 1. Required fields check
    log("--- 1. Required Fields Check ---")
    required = ['statement','answer','solution','task_id','cell_key','grade','level']
    missing_keys = 0
    empty_fields = 0
    for i, t in enumerate(data):
        for k in required:
            if k not in t:
                errors.append(f"Task {i}: missing key '{k}'")
                missing_keys += 1
            elif k in ('statement','answer','solution'):
                if not isinstance(t[k], str) or not t[k].strip():
                    errors.append(f"Task {i} ({t.get('task_id','?')}): '{k}' is empty/not string")
                    empty_fields += 1
    log(f"  Missing keys: {missing_keys}")
    log(f"  Empty string fields: {empty_fields}")
    log(f"  Result: {'PASS' if missing_keys == 0 and empty_fields == 0 else 'FAIL'}")
    log("")
    
    # 2. Unique task_ids
    log("--- 2. Unique Task IDs ---")
    task_ids = [t.get('task_id','') for t in data]
    id_counts = Counter(task_ids)
    dupes = {tid: cnt for tid, cnt in id_counts.items() if cnt > 1}
    if dupes:
        errors.append(f"Duplicate task_ids: {dict(list(dupes.items())[:10])}")
    log(f"  Total unique IDs: {len(id_counts)}")
    log(f"  Duplicates: {len(dupes)}")
    log(f"  Result: {'PASS' if not dupes else 'FAIL'}")
    log("")
    
    # 3. Cell key validation
    log("--- 3. Cell Key Validation ---")
    pattern = re.compile(r'^G(\d+)\|L([45])\|T(\d+)\|S(\d+)$')
    invalid = []
    cell_counts = Counter()
    grade_mismatch = 0
    level_mismatch = 0
    for t in data:
        ck = t.get('cell_key','')
        m = pattern.match(ck)
        if not m:
            invalid.append(ck)
            continue
        g, l, th, s = m.groups()
        cell_counts[ck] += 1
        if t.get('grade') is not None and int(t['grade']) != int(g):
            errors.append(f"Task {t.get('task_id','?')}: grade field {t['grade']} != cell_key grade {g}")
            grade_mismatch += 1
        if t.get('level') and str(t['level']) != l:
            errors.append(f"Task {t.get('task_id','?')}: level field {t['level']} != cell_key level {l}")
            level_mismatch += 1
    
    log(f"  Invalid cell_keys: {len(invalid)}")
    if invalid:
        log(f"  Invalid examples: {invalid[:5]}")
    log(f"  Grade mismatches: {grade_mismatch}")
    log(f"  Level mismatches: {level_mismatch}")
    log(f"  Unique cell_keys in data: {len(cell_counts)}")
    log(f"  Result: {'PASS' if not invalid and grade_mismatch == 0 and level_mismatch == 0 else 'FAIL'}")
    log("")
    
    # 4. Report counts match
    log("--- 4. Cell Count vs Generation Report ---")
    expected = {
        'G11|L5|T001|S1':5,'G11|L5|T001|S2':5,'G11|L5|T034|S0':5,'G11|L5|T043|S1':5,
        'G5|L4|T004|S2':5,'G5|L4|T005|S0':5,'G5|L4|T005|S1':5,'G5|L4|T008|S1':5,
        'G5|L5|T004|S1':5,'G5|L5|T004|S2':5,'G5|L5|T005|S0':5,'G5|L5|T005|S1':5,
        'G5|L5|T008|S0':5,'G5|L5|T008|S1':5,'G5|L5|T022|S0':5,'G5|L5|T022|S1':5,
        'G5|L5|T022|S2':5,'G5|L5|T024|S1':5,'G5|L5|T024|S2':5,'G6|L5|T006|S2':5,
        'G6|L5|T007|S0':5,'G6|L5|T007|S1':5,'G6|L5|T007|S2':5,'G6|L5|T016|S1':5,
        'G6|L5|T018|S2':5,'G6|L5|T032|S1':5,'G6|L5|T033|S0':5,'G6|L5|T033|S1':5,
        'G6|L5|T033|S2':5,'G7|L5|T003|S2':5,'G7|L5|T003|S1':4,'G11|L5|T021|S1':4,
        'G5|L5|T002|S1':4,'G5|L5|T002|S2':4,'G5|L5|T004|S0':4,'G5|L5|T005|S2':4,
        'G6|L5|T018|S1':4,'G5|L5|T024|S0':3,'G6|L5|T018|S0':3,'G5|L4|T022|S2':2,
        'G7|L5|T023|S1':2,
    }
    count_errors = 0
    for ck, exp in expected.items():
        actual = cell_counts.get(ck, 0)
        if actual != exp:
            errors.append(f"Cell {ck}: report says {exp}, file has {actual}")
            count_errors += 1
    log(f"  Cells with count mismatch: {count_errors}")
    
    # Extra cells
    extra = set(cell_counts.keys()) - set(expected.keys())
    if extra:
        warnings.append(f"Extra cells in file not in report: {sorted(extra)}")
    missing = set(expected.keys()) - set(cell_counts.keys())
    if missing:
        errors.append(f"Cells in report missing from file: {sorted(missing)}")
    log(f"  Extra cells (in file, not in report): {len(extra)}")
    log(f"  Missing cells (in report, not in file): {len(missing)}")
    log(f"  Result: {'PASS' if count_errors == 0 and not missing else 'FAIL'}")
    log("")
    
    # 5. Duplicate statements within cell
    log("--- 5. Duplicate Statements Check ---")
    cell_stmts = defaultdict(set)
    dup_stmts = 0
    for t in data:
        ck = t.get('cell_key','')
        stmt = t.get('statement','')
        if stmt and stmt in cell_stmts[ck]:
            dup_stmts += 1
            warnings.append(f"Duplicate statement in {ck}")
        cell_stmts[ck].add(stmt)
    log(f"  Duplicate statements within cells: {dup_stmts}")
    log(f"  Result: {'PASS' if dup_stmts == 0 else 'WARN'}")
    log("")
    
    # 6. Summary
    log("--- SUMMARY ---")
    log(f"  Total tasks: {len(data)}")
    log(f"  Total errors: {len(errors)}")
    log(f"  Total warnings: {len(warnings)}")
    log(f"  Errors:")
    for e in errors:
        log(f"    - {e}")
    log(f"  Warnings:")
    for w in warnings:
        log(f"    - {w}")
    
    # Grade/level distribution
    grades = Counter()
    levels = Counter()
    for t in data:
        ck = t.get('cell_key','')
        m = pattern.match(ck)
        if m:
            grades[int(m.group(1))] += 1
            levels[m.group(2)] += 1
    log(f"  Grade distribution: {dict(sorted(grades.items()))}")
    log(f"  Level distribution: {dict(levels)}")
    
    log("")
    log(f"  VERDICT: {'ALL CHECKS PASSED' if not errors else f'{len(errors)} ERROR(S) FOUND'}")
    log("=" * 70)
    
    # Write report
    with open('stage7_verification_report.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    return len(errors) == 0

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
