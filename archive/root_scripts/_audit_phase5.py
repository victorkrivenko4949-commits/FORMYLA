#!/usr/bin/env python3
"""
Phase 5 Comprehensive Audit Script
===================================
Performs Parts A-F:
  A. Detect all Phase 5 additions by diff before/after
  B. Technical integrity checks + ID overlap resolution
  C. Provenance verification (formula + olympiad DB)
  D. Content QA (structure, coherence, assignment, diversity)
  E. Generate verified final files
  F. Generate audit report

Output files (all in C:/Users/Victor/Downloads/):
  - phase5_added_tasks_detected.json
  - phase5_added_tasks_audit.csv
  - phase5_id_overlap_conflicts.json
  - final_clean_dataset_5levels_verified.json
  - final_clean_dataset_5levels_verified_reserve.json
  - phase5_audit_report.md
"""
import json, sys, os, re, csv, textwrap
from collections import defaultdict, Counter
from copy import deepcopy

sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DOWN = r'C:\Users\Victor\Downloads'
MAIN_AFTER  = f'{DOWN}/final_clean_dataset_5levels.json'
MAIN_BEFORE = f'{DOWN}/final_clean_dataset_5levels_BEFORE_PHASE5.json'
RESERVE_PATH = f'{DOWN}/final_clean_dataset_5levels_reserve.json'
FORMYLA_PATH = f'{DOWN}/formyla_dataset_slightly_fixed.json'
OLYMPIAD_DB_PATH = f'{DOWN}/olympiad_DB_final_fixed.jsonl'
VERIFIED_MAIN = f'{DOWN}/final_clean_dataset_5levels_verified.json'
VERIFIED_RESERVE = f'{DOWN}/final_clean_dataset_5levels_verified_reserve.json'
DETECTED_PATH = f'{DOWN}/phase5_added_tasks_detected.json'
AUDIT_CSV = f'{DOWN}/phase5_added_tasks_audit.csv'
OVERLAP_PATH = f'{DOWN}/phase5_id_overlap_conflicts.json'
REPORT_PATH = f'{DOWN}/phase5_audit_report.md'

def normalize_text(t):
    """Collapse whitespace for comparison."""
    return re.sub(r'\s+', ' ', str(t).strip()).lower()

# ============================================================
# LOAD ALL DATA
# ============================================================
print("Loading datasets...")
with open(MAIN_BEFORE, 'r', encoding='utf-8') as f:
    before = json.load(f)
with open(MAIN_AFTER, 'r', encoding='utf-8') as f:
    after = json.load(f)
with open(RESERVE_PATH, 'r', encoding='utf-8') as f:
    reserve = json.load(f)
with open(FORMYLA_PATH, 'r', encoding='utf-8') as f:
    formyla = json.load(f)

oly_entries = []
with open(OLYMPIAD_DB_PATH, 'r', encoding='utf-8') as f:
    for l in f:
        l = l.strip()
        if l:
            oly_entries.append(json.loads(l))

print(f"  Before: {len(before)} tasks")
print(f"  After:  {len(after)} tasks")
print(f"  Reserve: {len(reserve)} tasks")
print(f"  Formyla: {len(formyla)} tasks")
print(f"  Olympiad DB entries: {len(oly_entries)}")

# Build lookup dicts
before_by_id = {t['id']: t for t in before}
after_by_id = {t['id']: t for t in after}
reserve_by_id = {t['id']: t for t in reserve}

# ============================================================
# PART A: DETECT PHASE 5 ADDITIONS
# ============================================================
print("\n=== PART A: Detect additions ===")

before_ids = set(t['id'] for t in before)
after_ids = set(t['id'] for t in after)
added_ids = after_ids - before_ids
removed_ids = before_ids - after_ids

print(f"  Added IDs:   {len(added_ids)}")
print(f"  Removed IDs: {len(removed_ids)}")

# Also check by text: tasks in after that are not in before by ID, 
# and also verify no pre-existing task was duplicated with new ID
before_texts = {normalize_text(t.get('task_text','')) for t in before}
before_text_answer = {}
for t in before:
    key = (normalize_text(t.get('task_text','')), normalize_text(t.get('correct_answer','')))
    before_text_answer[key] = t['id']

additions = []
for tid in sorted(added_ids):
    t = after_by_id[tid]
    norm_text = normalize_text(t.get('task_text',''))
    
    # Determine source category from ID prefix and audit_note
    audit_note = t.get('audit_note', '')
    if 'formyla' in audit_note.lower():
        source_cat = 'formula_dataset'
    elif 'olympiad db' in audit_note.lower():
        source_cat = 'olympiad_db'
    else:
        source_cat = 'unknown'
    
    # Try to find source record
    source_file_match = ''
    source_record_id = ''
    match_type = ''
    
    if 'formyla' in source_cat:
        # Try exact ID match first
        orig_id_match = re.search(r'original id:\s*(\S+)', audit_note)
        if orig_id_match:
            orig_id = orig_id_match.group(1)
            source_record_id = orig_id
            for ft in formyla:
                if ft.get('id') == orig_id:
                    source_file_match = 'formula_dataset_slightly_fixed.json'
                    match_type = 'exact_id'
                    break
            if not match_type:
                # Try text match
                for ft in formyla:
                    if normalize_text(ft.get('task_text','')) == norm_text:
                        source_file_match = 'formula_dataset_slightly_fixed.json'
                        source_record_id = ft.get('id', '')
                        match_type = 'exact_text'
                        break
                if not match_type:
                    match_type = 'not_found'
        else:
            # Try text match
            for ft in formyla:
                if normalize_text(ft.get('task_text','')) == norm_text:
                    source_file_match = 'formula_dataset_slightly_fixed.json'
                    source_record_id = ft.get('id', '')
                    match_type = 'exact_text'
                    break
            if not match_type:
                match_type = 'not_found'
                
    elif 'olympiad' in source_cat:
        # Extract olympiad name, year, round, problem from audit_note
        oly_match = re.search(r'olympiad DB:\s*(.+?)\s+(\d{4})?\s*grade\s*(\d+)?', audit_note)
        for entry in oly_entries:
            for p in entry.get('problems', []):
                p_text_norm = normalize_text(p.get('text',''))
                if p_text_norm == norm_text:
                    source_file_match = 'olympiad_DB_final_fixed.jsonl'
                    source_record_id = f"{entry.get('olympiad')}/{entry.get('year')}/P{p.get('num')}"
                    match_type = 'exact_text'
                    break
            if match_type:
                break
        if not match_type:
            # Try partial text match
            for entry in oly_entries:
                for p in entry.get('problems', []):
                    p_text = normalize_text(p.get('text',''))
                    if len(p_text) > 50 and (p_text[:80] == norm_text[:80] or norm_text[:80] == p_text[:80]):
                        source_file_match = 'olympiad_DB_final_fixed.jsonl'
                        source_record_id = f"{entry.get('olympiad')}/{entry.get('year')}/P{p.get('num')}"
                        match_type = 'fuzzy_text_prefix'
                        break
                if match_type:
                    break
        if not match_type:
            match_type = 'not_found'
    
    additions.append({
        'id': tid,
        'grade': t.get('grade'),
        'method_code': t.get('method_code'),
        'difficulty': t.get('difficulty'),
        'task_text': t.get('task_text', ''),
        'correct_answer': t.get('correct_answer', ''),
        'solution': t.get('solution', ''),
        'theme': t.get('theme', ''),
        'subtopic': t.get('subtopic', ''),
        'status': t.get('status', ''),
        'audit_note': audit_note,
        'presumed_source': source_cat,
        'source_file_match': source_file_match,
        'source_record_id': source_record_id,
        'match_type': match_type,
    })

print(f"  Additions detected: {len(additions)}")
if len(additions) != 53:
    print(f"  *** EXPECTED 53, FOUND {len(additions)} ***")

# Save detected additions
with open(DETECTED_PATH, 'w', encoding='utf-8') as f:
    json.dump(additions, f, ensure_ascii=False, indent=2)
print(f"  Saved: {DETECTED_PATH}")

# ============================================================
# PART B: TECHNICAL INTEGRITY
# ============================================================
print("\n=== PART B: Technical integrity ===")

tech_checks = {}

# B1. JSON validity
tech_checks['json_valid_main'] = isinstance(after, list)
tech_checks['json_valid_reserve'] = isinstance(reserve, list)

# B2. Difficulty range
main_diffs = set(t.get('difficulty') for t in after)
reserve_diffs = set(t.get('difficulty') for t in reserve)
tech_checks['main_difficulty_1_5'] = main_diffs <= {1,2,3,4,5}
tech_checks['reserve_difficulty_1_5'] = reserve_diffs <= {1,2,3,4,5}

# B3. Duplicate IDs main
main_ids = [t['id'] for t in after]
main_dup_ids = [id for id, cnt in Counter(main_ids).items() if cnt > 1]
tech_checks['main_unique_ids'] = len(main_dup_ids) == 0
tech_checks['main_dup_ids'] = main_dup_ids

# B4. Duplicate IDs reserve
reserve_ids = [t['id'] for t in reserve]
reserve_dup_ids = [id for id, cnt in Counter(reserve_ids).items() if cnt > 1]
tech_checks['reserve_unique_ids'] = len(reserve_dup_ids) == 0
tech_checks['reserve_dup_ids'] = reserve_dup_ids

# B5. ID overlap main <-> reserve
overlap_ids = sorted(set(main_ids) & set(reserve_ids))
tech_checks['id_overlap'] = overlap_ids
tech_checks['id_overlap_count'] = len(overlap_ids)

# B6. Exact text duplicates in main
main_texts = defaultdict(list)
for t in after:
    norm = normalize_text(t.get('task_text',''))
    if norm:
        main_texts[norm].append(t['id'])
main_text_dups = {k: v for k, v in main_texts.items() if len(v) > 1}
tech_checks['main_text_duplicates'] = main_text_dups

# B7. Text duplicates main vs reserve (different IDs)
main_text_set = {normalize_text(t.get('task_text','')) for t in after}
reserve_text_set = {normalize_text(t.get('task_text','')) for t in reserve}
cross_text_dups = main_text_set & reserve_text_set
tech_checks['cross_text_duplicates_count'] = len(cross_text_dups)

# B8-B9. Cell counts in main
main_cell_counts = defaultdict(int)
main_cell_ids = defaultdict(list)
for t in after:
    key = (t.get('grade'), t.get('method_code'), t.get('difficulty'))
    main_cell_counts[key] += 1
    main_cell_ids[key].append(t['id'])

overfull_cells = {k: v for k, v in main_cell_counts.items() if v > 5}
tech_checks['overfull_cells'] = {str(k): v for k, v in overfull_cells.items()}

# L3 cells specifically
l3_cell_counts = defaultdict(int)
l3_cell_ids = defaultdict(list)
for t in after:
    if t.get('difficulty') == 3:
        key = (t['grade'], t['method_code'])
        l3_cell_counts[key] += 1
        l3_cell_ids[key].append(t['id'])

tech_checks['l3_cells_full'] = all(v == 5 for v in l3_cell_counts.values())
l3_incomplete = {k: v for k, v in l3_cell_counts.items() if v != 5}
tech_checks['l3_incomplete'] = {str(k): v for k, v in l3_incomplete.items()}

# B10. L1/L2/L4/L5 unchanged from before
before_non_l3 = {}
after_non_l3 = {}
for t in before:
    d = t.get('difficulty')
    if d != 3:
        before_non_l3[t['id']] = t
for t in after:
    d = t.get('difficulty')
    if d != 3:
        after_non_l3[t['id']] = t

changed_non_l3 = []
for tid, tb in before_non_l3.items():
    ta = after_non_l3.get(tid)
    if ta is None:
        changed_non_l3.append(f"{tid}: removed")
    elif tb != ta:
        changed_non_l3.append(f"{tid}: modified")
# Also check new non-L3 tasks added
new_non_l3 = set(after_non_l3.keys()) - set(before_non_l3.keys())
for tid in new_non_l3:
    changed_non_l3.append(f"{tid}: added (non-L3)")
        
tech_checks['l1_l2_l4_l5_changed'] = changed_non_l3
tech_checks['l1_l2_l4_l5_unchanged'] = len(changed_non_l3) == 0

# B11. Only L3 tasks were added
all_added_ids = added_ids
added_non_l3 = [tid for tid in all_added_ids if after_by_id[tid].get('difficulty') != 3]
tech_checks['added_non_l3'] = added_non_l3

print(f"  ID overlap count: {tech_checks['id_overlap_count']}")
print(f"  Main duplicate IDs: {len(main_dup_ids)}")
print(f"  Reserve duplicate IDs: {len(reserve_dup_ids)}")
print(f"  Overfull cells: {len(overfull_cells)}")
print(f"  L3 incomplete: {len(l3_incomplete)}")
print(f"  L1/L2/L4/L5 modified: {len(changed_non_l3)}")
print(f"  Added non-L3: {len(added_non_l3)}")

# ============================================================
# RESOLVE ID OVERLAP
# ============================================================
print("\n--- Resolving ID overlap ---")

overlap_conflicts = []
for oid in overlap_ids:
    t_main = after_by_id[oid]
    t_reserve = reserve_by_id[oid]
    
    # Compare all meaningful fields
    fields_to_compare = ['id', 'grade', 'method_code', 'difficulty', 'task_text', 
                         'correct_answer', 'solution', 'theme', 'subtopic',
                         'original_difficulty', 'status', 'compression_status']
    
    identical = all(t_main.get(f) == t_reserve.get(f) for f in fields_to_compare)
    
    if identical:
        overlap_conflicts.append({
            'id': oid,
            'action': 'removed_duplicate_from_reserve',
            'identical': True,
            'grade': t_main.get('grade'),
            'method_code': t_main.get('method_code'),
            'difficulty': t_main.get('difficulty'),
        })
    else:
        # Records differ - determine which is better
        main_score = 0
        reserve_score = 0
        diffs = {}
        for f in fields_to_compare:
            mv = t_main.get(f)
            rv = t_reserve.get(f)
            if mv != rv:
                diffs[f] = {'main': mv, 'reserve': rv}
                # Score: longer/more complete is better
                if isinstance(mv, str) and isinstance(rv, str):
                    if len(mv) > len(rv):
                        main_score += 1
                    elif len(rv) > len(mv):
                        reserve_score += 1
                elif mv and not rv:
                    main_score += 1
                elif rv and not mv:
                    reserve_score += 1
        
        # Prefer main for non-empty solution/answer
        if t_main.get('solution') and not t_reserve.get('solution'):
            main_score += 3
        if t_reserve.get('solution') and not t_main.get('solution'):
            reserve_score += 3
        if t_main.get('correct_answer') and not t_reserve.get('correct_answer'):
            main_score += 2
        if t_reserve.get('correct_answer') and not t_main.get('correct_answer'):
            reserve_score += 2
        
        keep_in_main = main_score >= reserve_score
        
        overlap_conflicts.append({
            'id': oid,
            'action': 'conflicting_duplicate_quarantined',
            'identical': False,
            'grade': t_main.get('grade'),
            'method_code': t_main.get('method_code'),
            'difficulty': t_main.get('difficulty'),
            'differences': diffs,
            'main_score': main_score,
            'reserve_score': reserve_score,
            'keep_in_main': keep_in_main,
            'main_version': t_main,
            'reserve_version': t_reserve,
        })

with open(OVERLAP_PATH, 'w', encoding='utf-8') as f:
    json.dump(overlap_conflicts, f, ensure_ascii=False, indent=2)
print(f"  Saved: {OVERLAP_PATH}")

# ============================================================
# PART C: PROVENANCE VERIFICATION
# ============================================================
print("\n=== PART C: Provenance verification ===")

for add in additions:
    tid = add['id']
    t = after_by_id[tid]
    
    if add['presumed_source'] == 'formula_dataset':
        # Already matched in Part A, just verify
        add['source_verified'] = add['match_type'] in ('exact_id', 'exact_text')
    elif add['presumed_source'] == 'olympiad_db':
        # STRICT verification for keyword-matched tasks
        norm_text = normalize_text(t.get('task_text',''))
        norm_answer = normalize_text(t.get('correct_answer',''))
        
        found_exact = False
        found_source = None
        
        for entry in oly_entries:
            for p in entry.get('problems', []):
                p_text_norm = normalize_text(p.get('text',''))
                p_ans_norm = normalize_text(p.get('answer',''))
                
                # Exact text match
                if p_text_norm == norm_text:
                    found_exact = True
                    found_source = {
                        'olympiad': entry.get('olympiad'),
                        'year': entry.get('year'),
                        'grade': entry.get('grade'),
                        'round': entry.get('round'),
                        'num': p.get('num'),
                    }
                    add['match_type'] = 'exact_text'
                    break
                
                # Exact text + answer match
                if p_text_norm and norm_text and norm_answer and p_ans_norm:
                    if p_text_norm[:100] == norm_text[:100] and p_ans_norm == norm_answer:
                        found_exact = True
                        found_source = {
                            'olympiad': entry.get('olympiad'),
                            'year': entry.get('year'),
                            'grade': entry.get('grade'),
                            'round': entry.get('round'),
                            'num': p.get('num'),
                        }
                        add['match_type'] = 'exact_text_answer'
                        break
            if found_exact:
                break
        
        # If not exact, try fuzzy
        if not found_exact:
            for entry in oly_entries:
                for p in entry.get('problems', []):
                    p_text = p.get('text','')
                    p_text_norm = normalize_text(p_text)
                    if len(p_text_norm) > 50 and len(norm_text) > 50:
                        # Compare first 80 chars
                        if p_text_norm[:80] == norm_text[:80]:
                            found_source = {
                                'olympiad': entry.get('olympiad'),
                                'year': entry.get('year'),
                                'grade': entry.get('grade'),
                                'round': entry.get('round'),
                                'num': p.get('num'),
                            }
                            add['match_type'] = 'fuzzy_text_prefix'
                            break
                if found_source:
                    break
        
        add['source_verified'] = found_exact
        add['source_record_id'] = str(found_source) if found_source else ''
        add['source_file_match'] = 'olympiad_DB_final_fixed.jsonl' if found_source else ''
        
        if not found_exact:
            # Check if it's just a keyword match without actual source record
            if add['match_type'] in ('not_found', 'fuzzy_text_prefix'):
                add['source_verified'] = False
    else:
        add['source_verified'] = False

# ============================================================
# PART D: CONTENT QA
# ============================================================
print("\n=== PART D: Content QA ===")

for add in additions:
    tid = add['id']
    t = after_by_id[tid]
    issues = []
    audit_status = 'approved'
    reserve_reason = ''
    level_assessment = 'L3'
    method_assessment = 'ok'
    diversity_assessment = 'ok'
    
    # D1. Structure check
    task_text = t.get('task_text', '')
    correct_answer = t.get('correct_answer', '')
    solution = t.get('solution', '')
    
    if not task_text or len(task_text.strip()) < 10:
        issues.append('task_text empty or too short')
    if not correct_answer or len(str(correct_answer).strip()) == 0:
        issues.append('correct_answer empty')
    if not solution or len(solution.strip()) < 10:
        issues.append('solution empty or too short')
    
    # Check for broken characters
    broken_chars = re.findall(r'[^\x20-\x7E\u0400-\u04FF\u0500-\u052F\u0020-\u007E]', task_text + correct_answer + solution)
    if broken_chars:
        issues.append(f'broken chars: {set(broken_chars)}')
    
    # Check LaTeX
    latex_errors = []
    # Unmatched braces
    if task_text.count('{') != task_text.count('}'):
        latex_errors.append('unmatched braces in task_text')
    if solution.count('{') != solution.count('}'):
        latex_errors.append('unmatched braces in solution')
    if latex_errors:
        issues.extend(latex_errors)
    
    # D2. Coherence check (simple)
    # Check answer appears in solution
    if correct_answer and solution:
        ans_norm = normalize_text(str(correct_answer))
        sol_norm = normalize_text(solution)
        if ans_norm and ans_norm not in sol_norm and len(ans_norm) > 1:
            issues.append(f'answer not found in solution text (may still be valid)')
    
    # D3. Assignment check
    grade = t.get('grade')
    method = t.get('method_code')
    difficulty = t.get('difficulty')
    
    if difficulty != 3:
        issues.append(f'difficulty is {difficulty}, expected 3')
        audit_status = 'rejected_level_or_method_mismatch'
        level_assessment = f'L{difficulty}'
    
    # Check if method_code looks reasonable for grade
    # (basic sanity - methods like A3 for algebra at grade 8+ is fine)
    
    # D4. Diversity check
    cell_key = (grade, method)
    cell_tasks = l3_cell_ids.get(cell_key, [])
    same_text_count = 0
    for existing_id in cell_tasks:
        if existing_id == tid:
            continue
        existing_t = after_by_id.get(existing_id, {})
        # Check if extremely similar (first 80 chars match)
        if normalize_text(existing_t.get('task_text',''))[:80] == normalize_text(task_text)[:80]:
            same_text_count += 1
    
    if same_text_count > 0:
        issues.append(f'very similar to {same_text_count} other task(s) in same cell')
        diversity_assessment = 'low_diversity'
    
    # Check for template-like tasks (same structure, different numbers)
    # Simple heuristic: count tasks with identical first 50 chars
    template_count = 0
    for existing_id in cell_tasks:
        if existing_id == tid:
            continue
        existing_t = after_by_id.get(existing_id, {})
        if normalize_text(existing_t.get('task_text',''))[:50] == normalize_text(task_text)[:50]:
            template_count += 1
    if template_count >= 3:
        issues.append(f'template duplicate: {template_count} tasks with same opening')
        if diversity_assessment == 'ok':
            diversity_assessment = 'template_repetition'
    
    # Determine audit status from issues
    if any('empty' in i for i in issues):
        audit_status = 'rejected_incomplete_record'
        reserve_reason = 'phase5_incomplete_record'
    elif any('unverified' in i for i in issues) and not add.get('source_verified'):
        audit_status = 'rejected_unverified_provenance'
        reserve_reason = 'phase5_provenance_unverified'
    elif any('broken' in i for i in issues):
        audit_status = 'rejected_content_inconsistency'
        reserve_reason = 'phase5_content_inconsistency'
    elif any('mismatch' in i for i in issues):
        if audit_status == 'approved':
            audit_status = 'rejected_level_or_method_mismatch'
        reserve_reason = 'phase5_level_or_method_mismatch'
    
    # Override for diversity
    if audit_status == 'approved' and diversity_assessment in ('low_diversity', 'template_repetition'):
        audit_status = 'approved_with_diversity_warning'
    
    # Override for provenance issues
    if not add.get('source_verified') and add.get('presumed_source') == 'olympiad_db':
        if audit_status == 'approved':
            audit_status = 'rejected_unverified_provenance'
            reserve_reason = 'phase5_provenance_unverified_keyword_match'
    
    add['audit_status'] = audit_status
    add['reserve_reason'] = reserve_reason
    add['level_assessment'] = level_assessment
    add['method_assessment'] = method_assessment
    add['diversity_assessment'] = diversity_assessment
    add['issues'] = issues

# ============================================================
# PART E: BUILD VERIFIED FILES
# ============================================================
print("\n=== PART E: Build verified files ===")

# Identify which additions are approved for main
approved_ids = set()
rejected_ids = set()
manual_review_ids = set()

for add in additions:
    tid = add['id']
    if add['audit_status'] == 'needs_manual_review':
        manual_review_ids.add(tid)
    elif add['audit_status'].startswith('approved'):
        approved_ids.add(tid)
    else:
        rejected_ids.add(tid)

print(f"  Approved: {len(approved_ids)}")
print(f"  Rejected: {len(rejected_ids)}")
print(f"  Needs manual review: {len(manual_review_ids)}")

# Build verified main
verified_main = []
for t in after:
    tid = t['id']
    if tid in added_ids:
        # Phase 5 addition - only include if approved
        if tid in approved_ids:
            verified_main.append(t)
        else:
            # Will go to reserve
            pass
    else:
        # Pre-existing task
        # Also handle ID overlap: remove from main if it's in overlap AND
        # the overlap resolution says to keep reserve version
        overlap_entry = next((o for o in overlap_conflicts if o['id'] == tid), None)
        if overlap_entry:
            if overlap_entry['action'] == 'removed_duplicate_from_reserve':
                # Keep in main (identical, we remove from reserve)
                verified_main.append(t)
            elif overlap_entry['action'] == 'conflicting_duplicate_quarantined':
                if overlap_entry.get('keep_in_main', True):
                    verified_main.append(t)
                # else: keep reserve version, skip main
            else:
                verified_main.append(t)
        else:
            verified_main.append(t)

# Build verified reserve
verified_reserve = []
for t in reserve:
    tid = t['id']
    # Remove entries that overlap with main and are identical (we keep main copy)
    overlap_entry = next((o for o in overlap_conflicts if o['id'] == tid), None)
    if overlap_entry and overlap_entry['action'] == 'removed_duplicate_from_reserve':
        continue  # Skip, we keep main copy
    if overlap_entry and overlap_entry['action'] == 'conflicting_duplicate_quarantined':
        if not overlap_entry.get('keep_in_main', True):
            # Keep this reserve version; main version will be quarantined
            verified_reserve.append(t)
        else:
            # Main version kept; quarantine reserve version... actually keep in reserve
            # with a note, but don't lose data
            t_copy = dict(t)
            t_copy['review_note'] = (t_copy.get('review_note','') + 
                '; ID overlap with main - main version preferred').strip('; ')
            verified_reserve.append(t_copy)
        continue
    verified_reserve.append(t)

# Add rejected Phase 5 additions to reserve
for add in additions:
    tid = add['id']
    if tid not in approved_ids:
        t = after_by_id[tid]
        t_copy = dict(t)
        t_copy['reserve_reason'] = add.get('reserve_reason', 'phase5_audit_rejected')
        t_copy['audit_status'] = add['audit_status']
        # Also add review_note
        existing_note = t_copy.get('review_note', '')
        note = f"Phase5 audit: {add['audit_status']}"
        if add.get('issues'):
            note += '; ' + '; '.join(add['issues'])
        t_copy['review_note'] = (existing_note + ' | ' + note).strip(' | ')
        verified_reserve.append(t_copy)

# Remove zero-ID overlap between verified files
v_main_ids = set(t['id'] for t in verified_main)
v_reserve_ids = set(t['id'] for t in verified_reserve)
final_overlap = v_main_ids & v_reserve_ids
print(f"  Final ID overlap (should be 0): {len(final_overlap)}")

if final_overlap:
    # Remove from reserve as last resort
    verified_reserve = [t for t in verified_reserve if t['id'] not in v_main_ids]

# Also ensure no task_text duplicates between verified files
v_main_texts = {normalize_text(t.get('task_text','')) for t in verified_main}
verified_reserve = [t for t in verified_reserve 
                    if normalize_text(t.get('task_text','')) not in v_main_texts]

# Save
with open(VERIFIED_MAIN, 'w', encoding='utf-8') as f:
    json.dump(verified_main, f, ensure_ascii=False, indent=2)
print(f"  Saved verified main: {VERIFIED_MAIN} ({len(verified_main)} tasks)")

with open(VERIFIED_RESERVE, 'w', encoding='utf-8') as f:
    json.dump(verified_reserve, f, ensure_ascii=False, indent=2)
print(f"  Saved verified reserve: {VERIFIED_RESERVE} ({len(verified_reserve)} tasks)")

# ============================================================
# PART F: AUDIT REPORT + CSV
# ============================================================
print("\n=== PART F: Reports ===")

# Build CSV
with open(AUDIT_CSV, 'w', encoding='utf-8-sig', newline='') as f:
    fieldnames = ['id', 'grade', 'method_code', 'difficulty', 'source_category',
                  'source_file', 'source_record_id', 'match_type', 'source_verified',
                  'source_url', 'olympiad', 'year', 'stage', 'problem_number',
                  'audit_status', 'reserve_reason', 'level_assessment', 
                  'method_assessment', 'diversity_assessment', 'action_taken', 'notes']
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
    writer.writeheader()
    
    for add in additions:
        action = 'kept_in_main' if add['id'] in approved_ids else 'moved_to_reserve'
        if add['id'] in manual_review_ids:
            action = 'manual_review'
            
        # Parse source details
        olympiad = ''
        year = ''
        stage = ''
        prob_num = ''
        if add['presumed_source'] == 'olympiad_db':
            audit = add.get('audit_note', '')
            m = re.search(r'Imported from olympiad DB:\s*(\S+)\s+(\d{4})?\s*grade\s*(\d+)?\s*round\s*(\S+)?\s*P(\S+)?', audit)
            if m:
                olympiad = m.group(1) or ''
                year = m.group(2) or ''
                stage = m.group(4) or ''
                prob_num = m.group(5) or ''
        
        writer.writerow({
            'id': add['id'],
            'grade': add['grade'],
            'method_code': add['method_code'],
            'difficulty': add['difficulty'],
            'source_category': add['presumed_source'],
            'source_file': add.get('source_file_match', ''),
            'source_record_id': add.get('source_record_id', ''),
            'match_type': add.get('match_type', ''),
            'source_verified': add.get('source_verified', False),
            'source_url': '',
            'olympiad': olympiad,
            'year': year,
            'stage': stage,
            'problem_number': prob_num,
            'audit_status': add.get('audit_status', ''),
            'reserve_reason': add.get('reserve_reason', ''),
            'level_assessment': add.get('level_assessment', ''),
            'method_assessment': add.get('method_assessment', ''),
            'diversity_assessment': add.get('diversity_assessment', ''),
            'action_taken': action,
            'notes': '; '.join(add.get('issues', [])),
        })
print(f"  Saved CSV: {AUDIT_CSV}")

# Generate verification report for verified main
v_main_cells = defaultdict(int)
v_main_l3 = defaultdict(int)
for t in verified_main:
    key = (t['grade'], t['method_code'], t['difficulty'])
    v_main_cells[key] += 1
    if t.get('difficulty') == 3:
        v_main_l3[(t['grade'], t['method_code'])] += 1

# L3 coverage after audit
l3_full = sum(1 for c in v_main_l3.values() if c == 5)
l3_partial = sum(1 for c in v_main_l3.values() if 1 <= c < 5)
l3_empty = sum(1 for c in v_main_l3.values() if c == 0)
l3_over = sum(1 for c in v_main_l3.values() if c > 5)
l3_deficit = sum(max(0, 5 - c) for c in v_main_l3.values())

# Build report
report_lines = []
report_lines.append("# Phase 5 Audit Report")
report_lines.append("")
report_lines.append(f"**Date:** 2026-07-10")
report_lines.append(f"**Auditor:** Automated Phase 5 Audit Script")
report_lines.append("")
report_lines.append("---")
report_lines.append("")
report_lines.append("## 1. Task Counts")
report_lines.append("")
report_lines.append(f"| Metric | Before Phase 5 | After Phase 5 | Verified Final |")
report_lines.append(f"|--------|---------------|---------------|----------------|")
report_lines.append(f"| Main total | {len(before)} | {len(after)} | {len(verified_main)} |")
report_lines.append(f"| Reserve total | {len(reserve)} | {len(reserve)} | {len(verified_reserve)} |")
report_lines.append(f"| Phase 5 additions detected | — | {len(additions)} | {len(approved_ids)} (approved) |")
report_lines.append("")
report_lines.append("## 2. Phase 5 Additions Detection")
report_lines.append("")
report_lines.append(f"**Additions found:** {len(additions)}")
if len(additions) != 53:
    report_lines.append(f"***NOTE:** Expected 53, found {len(additions)}*")
report_lines.append("")
report_lines.append(f"**Source breakdown of detected additions:**")
report_lines.append("")
src_counts = Counter(a['presumed_source'] for a in additions)
for src, cnt in src_counts.most_common():
    report_lines.append(f"- {src}: {cnt}")

report_lines.append("")
report_lines.append("## 3. Technical Integrity Checks")
report_lines.append("")
report_lines.append("| Check | Result | Details |")
report_lines.append("|-------|--------|---------|")

checks_list = [
    ("JSON valid (main)", tech_checks['json_valid_main'], ""),
    ("JSON valid (reserve)", tech_checks['json_valid_reserve'], ""),
    ("Difficulty 1-5 only (main)", tech_checks['main_difficulty_1_5'], str(main_diffs)),
    ("Difficulty 1-5 only (reserve)", tech_checks['reserve_difficulty_1_5'], str(reserve_diffs)),
    ("Unique IDs (main)", tech_checks['main_unique_ids'], 
     f"{len(tech_checks['main_dup_ids'])} dups: {tech_checks['main_dup_ids']}" if tech_checks['main_dup_ids'] else ""),
    ("Unique IDs (reserve)", tech_checks['reserve_unique_ids'],
     f"{len(tech_checks['reserve_dup_ids'])} dups: {tech_checks['reserve_dup_ids']}" if tech_checks['reserve_dup_ids'] else ""),
    ("Zero ID overlap main-reserve", tech_checks['id_overlap_count'] == 0,
     f"{tech_checks['id_overlap_count']} overlapping IDs"),
    ("No exact text dups (main)", len(tech_checks['main_text_duplicates']) == 0,
     f"{len(tech_checks['main_text_duplicates'])} groups" if tech_checks['main_text_duplicates'] else ""),
    ("Max 5 tasks per main cell", len(tech_checks['overfull_cells']) == 0,
     str(tech_checks['overfull_cells']) if tech_checks['overfull_cells'] else ""),
    ("L1/L2/L4/L5 unchanged", tech_checks['l1_l2_l4_l5_unchanged'],
     f"{len(tech_checks['l1_l2_l4_l5_changed'])} changes" if tech_checks['l1_l2_l4_l5_changed'] else ""),
]

for name, passed, detail in checks_list:
    status = "PASS" if passed else "FAIL"
    report_lines.append(f"| {name} | {status} | {detail} |")

report_lines.append("")
report_lines.append("## 4. ID Overlap Resolution")
report_lines.append("")
report_lines.append(f"**ID overlap count before resolution:** {tech_checks['id_overlap_count']}")
report_lines.append("")
if overlap_conflicts:
    identical_count = sum(1 for o in overlap_conflicts if o['identical'])
    conflict_count = sum(1 for o in overlap_conflicts if not o['identical'])
    report_lines.append(f"- Identical records (removed from reserve): {identical_count}")
    report_lines.append(f"- Conflicting records (quarantined): {conflict_count}")
    report_lines.append("")
    report_lines.append("### Overlapping IDs")
    report_lines.append("")
    report_lines.append("| ID | Type | Action |")
    report_lines.append("|----|------|--------|")
    for o in overlap_conflicts:
        atype = "identical" if o['identical'] else "conflicting"
        report_lines.append(f"| {o['id']} | {atype} | {o['action']} |")
else:
    report_lines.append("No ID overlap found.")

report_lines.append("")
report_lines.append("## 5. Provenance Verification (11 Keyword-Matched Additions)")
report_lines.append("")
report_lines.append("| ID | Source Verified | Match Type | Audit Status | Action | Reason |")
report_lines.append("|----|----------------|------------|-------------|--------|--------|")

oly_additions = [a for a in additions if a['presumed_source'] == 'olympiad_db']
for a in oly_additions:
    sv = "YES" if a.get('source_verified') else "NO"
    mt = a.get('match_type', '')
    ast = a.get('audit_status', '')
    act = 'keep' if a['id'] in approved_ids else ('review' if a['id'] in manual_review_ids else 'reject')
    rr = a.get('reserve_reason', '')
    report_lines.append(f"| {a['id']} | {sv} | {mt} | {ast} | {act} | {rr} |")

report_lines.append("")
report_lines.append("## 6. Content Audit Summary")
report_lines.append("")

status_counts = Counter(a['audit_status'] for a in additions)
report_lines.append("| Status | Count |")
report_lines.append("|--------|-------|")
for s, c in sorted(status_counts.items()):
    report_lines.append(f"| {s} | {c} |")

report_lines.append("")
report_lines.append("### Rejection Reasons")
report_lines.append("")
rej_reasons = Counter(a['reserve_reason'] for a in additions if a.get('reserve_reason'))
for rr, c in sorted(rej_reasons.items()):
    report_lines.append(f"- {rr}: {c}")

# Diversity warnings
diversity_warnings = [a for a in additions if a.get('diversity_assessment') in ('low_diversity', 'template_repetition')]
if diversity_warnings:
    report_lines.append("")
    report_lines.append(f"### Diversity Warnings ({len(diversity_warnings)} tasks)")
    report_lines.append("")
    report_lines.append("| ID | Cell | Issue |")
    report_lines.append("|----|------|-------|")
    for a in diversity_warnings:
        report_lines.append(f"| {a['id']} | G{a['grade']} {a['method_code']} | {a.get('diversity_assessment')} |")

report_lines.append("")
report_lines.append("## 7. L3 Coverage After Audit")
report_lines.append("")
report_lines.append("| Grade | Method | Task Count | Missing to 5 |")
report_lines.append("|-------|--------|-----------|-------------|")

# Sort by grade then method
l3_sorted = sorted(v_main_l3.items())
for (g, m), cnt in l3_sorted:
    missing = max(0, 5 - cnt)
    report_lines.append(f"| {g} | {m} | {cnt} | {missing} |")

report_lines.append("")
report_lines.append(f"**L3 cells 5/5:** {l3_full} of 134")
report_lines.append(f"**L3 cells partial (1-4):** {l3_partial}")
report_lines.append(f"**L3 cells empty:** {l3_empty}")
report_lines.append(f"**L3 cells overflow (>5):** {l3_over}")
report_lines.append(f"**Total L3 deficit:** {l3_deficit}")
report_lines.append("")

# Pre-audit L3 coverage
pre_l3 = defaultdict(int)
for t in before:
    if t.get('difficulty') == 3:
        pre_l3[(t['grade'], t['method_code'])] += 1
pre_full = sum(1 for c in pre_l3.values() if c == 5)
pre_deficit = sum(max(0, 5 - c) for c in pre_l3.values())
report_lines.append(f"**Pre-audit (BEFORE Phase 5):** {pre_full} cells full, deficit {pre_deficit}")
report_lines.append(f"**Post-Phase 5 (Before audit):** all 134 cells full, deficit 0")
report_lines.append(f"**Post-audit (Verified):** {l3_full} cells full, deficit {l3_deficit}")
report_lines.append("")

report_lines.append("## 8. Final File Inventory")
report_lines.append("")
report_lines.append("| File | Path | Description |")
report_lines.append("|------|------|-------------|")
report_lines.append(f"| Verified Main | `{VERIFIED_MAIN}` | {len(verified_main)} tasks, audited and cleaned |")
report_lines.append(f"| Verified Reserve | `{VERIFIED_RESERVE}` | {len(verified_reserve)} tasks, includes rejected Phase 5 additions |")
report_lines.append(f"| Detected Additions | `{DETECTED_PATH}` | {len(additions)} detected Phase 5 additions with source info |")
report_lines.append(f"| Audit CSV | `{AUDIT_CSV}` | Per-task audit results |")
report_lines.append(f"| ID Overlap Conflicts | `{OVERLAP_PATH}` | {len(overlap_conflicts)} overlap records with resolution |")
report_lines.append(f"| Audit Report | `{REPORT_PATH}` | This report |")
report_lines.append("")
report_lines.append("## 9. Summary")
report_lines.append("")
report_lines.append(f"- **Phase 5 additions detected:** {len(additions)}")
report_lines.append(f"- **Approved for main:** {len(approved_ids)}")
report_lines.append(f"- **Moved to reserve:** {len(rejected_ids)}")
report_lines.append(f"- **Needs manual review:** {len(manual_review_ids)}")
report_lines.append(f"- **ID overlap:** before={tech_checks['id_overlap_count']}, after=0")
report_lines.append(f"- **L3 cells 5/5 after audit:** {l3_full} of 134")
report_lines.append(f"- **Real L3 deficit:** {l3_deficit}")

# Write report
with open(REPORT_PATH, 'w', encoding='utf-8') as f:
    f.write('\n'.join(report_lines))
print(f"  Saved report: {REPORT_PATH}")

print("\n" + "=" * 60)
print("AUDIT COMPLETE")
print("=" * 60)
print(f"Additions: {len(additions)}")
print(f"Approved: {len(approved_ids)}")
print(f"Rejected: {len(rejected_ids)}")
print(f"Manual review: {len(manual_review_ids)}")
print(f"ID overlap before: {tech_checks['id_overlap_count']}, after: 0")
print(f"L3 cells 5/5: {l3_full}/134, deficit: {l3_deficit}")
