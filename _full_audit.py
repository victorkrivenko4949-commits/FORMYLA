#!/usr/bin/env python3
"""Полный аудит состояния проекта."""
import json, os, hashlib
from collections import defaultdict

def sha256f(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

print("=" * 70)
print("ПОЛНЫЙ АУДИТ СОСТОЯНИЯ")
print("=" * 70)

# 1. Все возможные таксономии
print("\n--- 1. Все таксономии ---")
candidates = [
    "taxonomy_by_grade.json",
    "taxonomy.json",
    "l1_l3_generation/taxonomy_by_grade.json",
    "l1_l3_generation/target_grid.json",
    "l1_l3_generation/canonical_taxonomy.json",
    "l1_l3_generation/canonical_taxonomy_snapshot.json",
]
for cand in candidates:
    if os.path.exists(cand):
        sz = os.path.getsize(cand)
        sh = sha256f(cand)
        print(f"\n{cand} ({sz} bytes, {sh[:16]}...)")

# 2. Root taxonomy structure
print("\n--- 2. Root taxonomy_by_grade.json ---")
with open('taxonomy_by_grade.json', encoding='utf-8') as f:
    root = json.load(f)
meta = root.get('meta', {})
print(f"meta: {json.dumps(meta, ensure_ascii=False)[:200]}")
gd = root.get('grades', root.get('grade_themes', {}))
for gk in sorted(gd.keys(), key=lambda x: int(x) if x.isdigit() else 999):
    entry = gd[gk]
    if isinstance(entry, dict):
        themes = entry.get('themes', [])
        print(f"  Grade {gk}: {len(themes)} themes, section={entry.get('section_name', 'N/A')}")
        for t in themes[:2]:
            print(f"    {t.get('id','?')}: {t.get('name','?')[:50]}")
    elif isinstance(entry, list):
        print(f"  Grade {gk}: {len(entry)} items")
        
# 3. Target grid as authoritative flat taxonomy
print("\n--- 3. Target grid flat theme list ---")
with open('l1_l3_generation/target_grid.json', encoding='utf-8') as f:
    tg = json.load(f)
grades = tg.get('grades', {})
flat_themes = []
for gk in sorted(grades.keys()):
    g = grades[gk]
    topics = g.get('topics', {})
    for tid, tinfo in topics.items():
        topic_name = tinfo.get('topic_name', '?')
        subs = tinfo.get('subtopics', {})
        for sid, sinfo in subs.items():
            if sinfo.get('allowed', True):
                flat_themes.append({
                    'grade': int(gk),
                    'theme_id': f"G{gk}_{tid}_{sid}",
                    'core_topic': tid,
                    'subtopic': sid,
                    'theme': f"{topic_name}: {sinfo.get('subtopic_name','?')}",
                    'section': tinfo.get('section_name', topic_name)
                })

print(f"Flat themes in target_grid: {len(flat_themes)}")
# Stats per grade
grade_counts = defaultdict(int)
for ft in flat_themes:
    grade_counts[ft['grade']] += 1
for g in sorted(grade_counts.keys()):
    print(f"  Grade {g}: {grade_counts[g]} themes, need 5 per level = {grade_counts[g]*3} cells, {grade_counts[g]*15} tasks")
print(f"  Total: {sum(grade_counts.values())} final themes")
print(f"  Total cells (×3): {sum(grade_counts.values())*3}")
print(f"  Total tasks (×5): {sum(grade_counts.values())*15}")

# 4. Spec expected vs actual
print("\n--- 4. Spec expectation vs actual ---")
expected = {5:18, 6:20, 7:19, 8:19, 9:19, 10:19, 11:21}
print(f"{'Grade':>6} {'Expected':>10} {'Actual (TG)':>12} {'Actual (Root)':>12}")
for g in sorted(expected.keys()):
    actual_tg = grade_counts.get(g, 0)
    actual_root = len(gd.get(str(g), {}).get('themes', [])) if str(g) in gd else 0
    print(f"{g:>6} {expected[g]:>10} {actual_tg:>12} {actual_root:>12}")
print(f"{'Total':>6} {sum(expected.values()):>10} {sum(grade_counts.values()):>12}")

# 5. Sections in target_grid
print("\n--- 5. Sections ---")
sections = set()
for ft in flat_themes:
    sections.add(ft['section'])
print(f"Total sections: {len(sections)}")
for s in sorted(sections):
    print(f"  {s}")

# 6. Existing tasks quality
print("\n--- 6. Existing tasks audit ---")
# Check FINAL JSONL
fin = 'l1_l3_generation/max_fill_20260723_015316/FORMYLA_L1_L3_FINAL.jsonl'
approved = 0
if os.path.exists(fin):
    with open(fin, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    d = json.loads(line)
                    if d.get('quality_status') == 'APPROVE':
                        approved += 1
                except:
                    pass
print(f"Approved in FINAL JSONL: {approved}")

# Check victor2_generated.json
if os.path.exists('victor2_generated.json'):
    with open('victor2_generated.json', encoding='utf-8') as f:
        vik = json.load(f)
    l13 = 0
    for d in vik:
        lv = d.get('level', 0)
        if isinstance(lv, str):
            lv = int(lv.replace('L',''))
        if isinstance(lv, int) and 1 <= lv <= 3:
            l13 += 1
    print(f"victor2_generated.json: {len(vik)} tasks, ~{l13} L1-L3")

# Check curated bank
for bn in ['curated_bank_L1_L5_fixed.json']:
    if os.path.exists(bn):
        with open(bn, encoding='utf-8') as f:
            data = json.load(f)
        print(f"{bn}: {len(data)} tasks")

print("\n--- 7. Checkpoint info ---")
for cp in ['l1_l3_generation/l1_l3_checkpoint_20260723_015316.json',
           'l1_l3_generation/l1_l3_generation_checkpoint.json',
           'fill_cell_holes_checkpoint.json']:
    if os.path.exists(cp):
        sz = os.path.getsize(cp)
        print(f"{cp}: {sz} bytes")
        
print("\n--- 8. API Key ---")
if os.path.exists('l1_l3_generation/openrouter_key.txt'):
    with open('l1_l3_generation/openrouter_key.txt') as f:
        key = f.read().strip()
    print(f"OpenRouter key present: {key[:10]}...{key[-5:]}")
else:
    print("No OpenRouter key found!")

print("\n--- 9. VERDICT ---")
print(f"Target grid has {sum(grade_counts.values())} flat final themes")
print(f"Spec expects 135 themes")
if sum(grade_counts.values()) != 135:
    diff = 135 - sum(grade_counts.values())
    print(f"Gap: {diff} themes ({'+' if diff > 0 else ''}{diff})")
    print("TAXONOMY NOTE: Target grid has 128 subtopic-grade combinations vs spec's 135.")
    print("Proceeding with target_grid.json as authoritative project taxonomy.")
print(f"Cells: {sum(grade_counts.values())*3}")
print(f"Target tasks: {sum(grade_counts.values())*15}")
