#!/usr/bin/env python3
"""
Phase 5: Fill 53 missing L3 tasks from real olympiad data sources.

Strategy:
  1. Formyla cells (11 cells, ~41 tasks): Use formyla_dataset_slightly_fixed.json at difficulty=3
  2. Hard cells (5 cells, 12 tasks - F3/G1/G2 at grades 5,6,7): Use olympiad_DB_final_fixed.jsonl

Each cell targets 5 L3 tasks total (difficulty=3).
"""
import json, sys, re, os
from collections import defaultdict, Counter
from copy import deepcopy

sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

DOWN = r'C:\Users\Victor\Downloads'
OUTPUT_MAIN_PATH = f'{DOWN}/final_clean_dataset_5levels.json'
BACKUP_PATH = f'{DOWN}/final_clean_dataset_5levels_BEFORE_PHASE5.json'

# ============================================================
# 1. Load current main JSON
# ============================================================
print("=" * 60)
print("PHASE 5: FILL MISSING L3 TASKS")
print("=" * 60)

with open(OUTPUT_MAIN_PATH, 'r', encoding='utf-8') as f:
    main_tasks = json.load(f)

# Backup
with open(BACKUP_PATH, 'w', encoding='utf-8') as f:
    json.dump(main_tasks, f, ensure_ascii=False, indent=2)
print(f"Backup saved to: {BACKUP_PATH}")

# Determine incomplete cells (target=5 per cell)
cell_tasks = defaultdict(list)
for t in main_tasks:
    if t.get('difficulty') == 3:
        key = (t['grade'], t['method_code'])
        cell_tasks[key].append(t)

incomplete_cells = []
for key, tasks in sorted(cell_tasks.items()):
    g, m = key
    have = len(tasks)
    if have < 5:
        incomplete_cells.append((g, m, have, 5 - have))

print(f"\nIncomplete L3 cells: {len(incomplete_cells)}, total missing: {sum(n for _,_,_,n in incomplete_cells)}")

# ============================================================
# 2. Load formyla dataset
# ============================================================
with open(f'{DOWN}/formyla_dataset_slightly_fixed.json', 'r', encoding='utf-8') as f:
    formyla = json.load(f)

# Group formyla tasks by (grade, method, difficulty)
formyla_index = defaultdict(list)
for t in formyla:
    formyla_index[(t['grade'], t['method_code'], t.get('difficulty'))].append(t)

# ============================================================
# 3. Load olympiad DB
# ============================================================
with open(f'{DOWN}/olympiad_DB_final_fixed.jsonl', 'r', encoding='utf-8') as f:
    oly_entries = [json.loads(l) for l in f if l.strip()]

# Index olympiad problems by grade
oly_by_grade = defaultdict(list)
for entry in oly_entries:
    grade = entry.get('grade')
    for p in entry.get('problems', []):
        text = p.get('text', '')
        if text and len(text) > 30:
            oly_by_grade[grade].append({
                'olympiad': entry.get('olympiad'),
                'year': entry.get('year'),
                'round': entry.get('round'),
                'num': p.get('num'),
                'text': text,
                'answer': p.get('answer', ''),
                'solution': p.get('solution', ''),
            })

# ============================================================
# 4. Helper: quality score for a candidate task
# ============================================================
def quality_score(t):
    """Higher is better: prefer tasks with solution, answer, meaningful text."""
    score = 0
    if t.get('solution') and len(t['solution']) > 20:
        score += 3
    if t.get('correct_answer') and len(str(t['correct_answer'])) > 0:
        score += 2
    text = t.get('task_text', '')
    if len(text) > 50:
        score += 2
    elif len(text) > 20:
        score += 1
    # Prefer tasks without "stub" in ID
    t_id = t.get('id', '')
    if 'stub' not in t_id.lower():
        score += 1
    return score

def quality_score_oly(p):
    score = 0
    if p.get('solution') and len(p.get('solution', '')) > 20:
        score += 3
    if p.get('answer') and len(p.get('answer', '')) > 0:
        score += 2
    if len(p.get('text', '')) > 50:
        score += 2
    return score

# ============================================================
# 5. Determine max existing ID sequence per (grade, method)
# ============================================================
# Find existing IDs for each cell to determine sequence continuation
existing_seq = defaultdict(int)
for t in main_tasks:
    tid = t.get('id', '')
    # Match pattern like OLY-5-F3-L3-1 or FORM-6-B1-L3-1
    m = re.match(r'^(.+)-(\d+)-([A-Z0-9]+)-L3-(\d+)$', tid)
    if m:
        prefix, grade, method, seq = m.groups()
        existing_seq[(prefix, int(grade), method)] = max(existing_seq.get((prefix, int(grade), method), 0), int(seq))

# Also check for existing OLY prefix tasks
oly_seq_counter = max([existing_seq.get(('OLY', g, m), 0) for g, m in cell_tasks.keys()] or [0])

def make_new_id(grade, method, existing_ids):
    """Generate a new ID following the pattern OLY-{GRADE}-{METHOD}-L3-{N}."""
    prefix = 'OLY'
    # Find existing max N for this cell
    max_n = 0
    for tid in existing_ids:
        m = re.match(rf'^{prefix}-{grade}-{re.escape(method)}-L3-(\d+)$', tid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}-{grade}-{method}-L3-{max_n + 1}"

# ============================================================
# 6. Build new tasks
# ============================================================
new_tasks = []
add_log = []  # (grade, method, source, count)

# For each incomplete cell
for g, m, have, need in sorted(incomplete_cells):
    existing_ids = [t['id'] for t in cell_tasks[(g, m)]]
    existing_texts = {t.get('task_text', '') for t in cell_tasks[(g, m)]}
    
    print(f"\n--- Grade {g}, Method {m}: need {need} more ---")
    
    # Try formyla first
    candidates = formyla_index.get((g, m, 3), [])
    
    if len(candidates) >= need:
        # Select best candidates, avoid duplicates with existing
        scored = [(quality_score(t), t) for t in candidates 
                  if t['task_text'] not in existing_texts]
        scored.sort(key=lambda x: -x[0])
        
        selected = scored[:need]
        print(f"  Using formyla: {len(selected)} tasks (from {len(candidates)} candidates)")
        
        for score, t in selected:
            new_id = make_new_id(g, m, existing_ids)
            existing_ids.append(new_id)
            
            new_task = {
                'id': new_id,
                'grade': g,
                'method_code': m,
                'difficulty': 3,
                'task_text': t['task_text'],
                'correct_answer': t.get('correct_answer', ''),
                'solution': t.get('solution', ''),
                'theme': t.get('theme', ''),
                'subtopic': t.get('subtopic', ''),
                'original_difficulty': t.get('difficulty', 3),
                'status': 'olympiad_import',
                'review_note': '',
                'audit_note': f'Imported from formyla dataset (original id: {t["id"]})',
                'compression_rule': '',
                'compression_status': 'main',
            }
            new_tasks.append(new_task)
            print(f"    {new_id}: {t['task_text'][:60]}...")
        
        add_log.append((g, m, 'formyla', len(selected)))
        continue
    
    # If formyla has some but not enough
    if candidates:
        scored = [(quality_score(t), t) for t in candidates 
                  if t['task_text'] not in existing_texts]
        scored.sort(key=lambda x: -x[0])
        selected = [t for _, t in scored]
        remaining = need - len(selected)
        print(f"  Formyla partial: {len(selected)} tasks, need {remaining} more from olympiad DB")
        
        for t in selected:
            new_id = make_new_id(g, m, existing_ids)
            existing_ids.append(new_id)
            new_task = {
                'id': new_id,
                'grade': g,
                'method_code': m,
                'difficulty': 3,
                'task_text': t['task_text'],
                'correct_answer': t.get('correct_answer', ''),
                'solution': t.get('solution', ''),
                'theme': t.get('theme', ''),
                'subtopic': t.get('subtopic', ''),
                'original_difficulty': t.get('difficulty', 3),
                'status': 'olympiad_import',
                'review_note': '',
                'audit_note': f'Imported from formyla dataset (original id: {t["id"]})',
                'compression_rule': '',
                'compression_status': 'main',
            }
            new_tasks.append(new_task)
        
        add_log.append((g, m, 'formyla_partial', len(selected)))
        need = remaining
    else:
        print(f"  No formyla candidates at diff=3. Searching olympiad DB...")
    
    # For remaining needs, search olympiad DB
    if need > 0:
        # Determine keyword heuristics based on method
        method_keywords = {
            'F3': ['сколькими способов', 'сколько', 'выбрать', 'комбинатор', 'сочетани', 'размещени', 'перестановк', 'вариант', 'расположени'],
            'G1': ['может ли', 'всегда', 'докажите', 'найдется', 'инвариант', 'четность', 'чётность', 'остаток', 'чётно'],
            'G2': ['раскрас', 'шахмат', 'клетк', 'разреза', 'двумя цвет', 'три цвета', 'различные цвет', 'конфетк', 'плитк'],
        }
        keywords = method_keywords.get(m, ['найдите', 'сколько'])
        
        # Search olympiad DB entries matching grade and keywords
        grade_range = [g]  # Start with exact grade
        if g > 5:
            grade_range.append(g - 1)  # Allow one grade lower
        if g < 11:
            grade_range.append(g + 1)  # Allow one grade higher
        
        oly_candidates = []
        for gr in grade_range:
            for p in oly_by_grade.get(gr, []):
                text = p.get('text', '')
                # Score by keyword matches
                kw_score = sum(2 for kw in keywords if kw.lower() in text.lower())
                if kw_score > 0:
                    oly_candidates.append((kw_score + quality_score_oly(p), gr, p))
        
        # Sort by score descending
        oly_candidates.sort(key=lambda x: -x[0])
        
        # Deduplicate by text
        used_texts = existing_texts | {nt['task_text'] for nt in new_tasks}
        unique_candidates = []
        for score, gr, p in oly_candidates:
            if p['text'] not in used_texts:
                used_texts.add(p['text'])
                unique_candidates.append((score, gr, p))
        
        selected_oly = unique_candidates[:need]
        print(f"  Olympiad DB: found {len(unique_candidates)} unique candidates, selected {len(selected_oly)}")
        
        for score, gr, p in selected_oly:
            new_id = make_new_id(g, m, existing_ids)
            existing_ids.append(new_id)
            
            # Determine theme based on method
            theme_map = {
                'F3': 'Комбинаторика',
                'G1': 'Логика и инварианты',
                'G2': 'Логика и комбинаторика',
            }
            
            new_task = {
                'id': new_id,
                'grade': g,
                'method_code': m,
                'difficulty': 3,
                'task_text': p.get('text', ''),
                'correct_answer': p.get('answer', ''),
                'solution': p.get('solution', ''),
                'theme': theme_map.get(m, 'Логика и комбинаторика'),
                'subtopic': f"{p.get('olympiad', 'olympiad').title()} {p.get('year', '')} round {p.get('round', '')} P{p.get('num', '')}",
                'original_difficulty': 3,
                'status': 'olympiad_import',
                'review_note': '',
                'audit_note': f'Imported from olympiad DB: {p.get("olympiad")} {p.get("year")} grade {gr} round {p.get("round")} P{p.get("num")}',
                'compression_rule': '',
                'compression_status': 'main',
            }
            new_tasks.append(new_task)
            print(f"    {new_id} (from {p.get('olympiad')} gr{gr} P{p.get('num')}): {p.get('text', '')[:60]}...")
        
        add_log.append((g, m, 'olympiad_db', len(selected_oly)))

# ============================================================
# 7. Add new tasks and save
# ============================================================
print(f"\n\n{'=' * 60}")
print(f"Total new L3 tasks to add: {len(new_tasks)}")
print(f"{'=' * 60}")

main_tasks.extend(new_tasks)

with open(OUTPUT_MAIN_PATH, 'w', encoding='utf-8') as f:
    json.dump(main_tasks, f, ensure_ascii=False, indent=2)

print(f"Updated main JSON saved to: {OUTPUT_MAIN_PATH}")

# ============================================================
# 8. Verify
# ============================================================
print(f"\n{'=' * 60}")
print("VERIFICATION")
print(f"{'=' * 60}")

after_cell_counts = defaultdict(int)
after_cell_ids = defaultdict(list)
for t in main_tasks:
    if t.get('difficulty') == 3:
        key = (t['grade'], t['method_code'])
        after_cell_counts[key] += 1
        after_cell_ids[key].append(t['id'])

all_complete = True
for key in sorted(after_cell_counts):
    g, m = key
    cnt = after_cell_counts[key]
    if cnt != 5:
        all_complete = False
        print(f"  ** Grade {g}, Method {m}: {cnt} tasks (expected 5) **")
        print(f"     IDs: {after_cell_ids[key]}")

if all_complete:
    print("  All 134 L3 cells have exactly 5 tasks! [OK]")
else:
    print("  Some cells still incomplete.")

# Summary
print(f"\n{'=' * 60}")
print("ADDITION SUMMARY")
print(f"{'=' * 60}")
for g, m, source, count in add_log:
    print(f"  Grade {g}, Method {m}: +{count} from {source}")

print(f"\nTotal new tasks added: {len(new_tasks)}")
print(f"Total main.json tasks: {len(main_tasks)}")
print(f"Backup at: {BACKUP_PATH}")
print("Phase 5 complete!")
