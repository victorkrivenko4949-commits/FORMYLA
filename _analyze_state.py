#!/usr/bin/env python3
"""Quick comprehensive state analysis."""
import json, os, hashlib
from collections import defaultdict

print("=== FILES IN l1_l3_generation ===")
for f in sorted(os.listdir('l1_l3_generation')):
    p = os.path.join('l1_l3_generation', f)
    if os.path.isfile(p):
        sz = os.path.getsize(p)
        print(f"  {f:50s} {sz:>8}")

print("\n=== TAXONOMY COMPARISON ===")
# Root taxonomy
with open('taxonomy_by_grade.json', encoding='utf-8') as f:
    root_tax = json.load(f)
print(f"Root taxonomy_by_grade.json: {list(root_tax.keys())}")
if 'meta' in root_tax:
    print(f"  meta: {root_tax['meta'].get('total_themes')} themes, {root_tax['meta'].get('total_subtopics')} subtopics")
if 'grades' in root_tax:
    total = 0
    for gk in sorted(root_tax['grades'].keys()):
        g = root_tax['grades'][gk]
        if isinstance(g, dict):
            themes = g.get('themes', [])
            print(f"  Grade {gk}: {len(themes)} themes")
            total += len(themes)
        elif isinstance(g, list):
            print(f"  Grade {gk}: {len(g)} items")
            total += len(g)
    print(f"  Total: {total}")
if 'grade_themes' in root_tax:
    total = 0
    for gk in sorted(root_tax['grade_themes'].keys()):
        items = root_tax['grade_themes'][gk]
        total += len(items)
    print(f"  grade_themes total: {total}")

# L1L3 taxonomy
with open('l1_l3_generation/taxonomy_by_grade.json', encoding='utf-8') as f:
    l1_tax = json.load(f)
print(f"\nl1_l3_generation/taxonomy_by_grade.json: {list(l1_tax.keys())}")
if 'grade_themes' in l1_tax:
    total = 0
    for gk in sorted(l1_tax['grade_themes'].keys()):
        items = l1_tax['grade_themes'][gk]
        print(f"  Grade {gk}: {len(items)} themes")
        for item in items[:3]:
            print(f"    {item.get('theme_id','?')}: {str(item.get('theme','?'))[:50]}")
        total += len(items)
    print(f"  Total: {total}")
if 'theme_definitions' in l1_tax:
    print(f"  theme_definitions: {len(l1_tax['theme_definitions'])} items")

# Canonical taxonomy
with open('l1_l3_generation/canonical_taxonomy.json', encoding='utf-8') as f:
    ct = json.load(f)
print(f"\ncanonical_taxonomy.json: {list(ct.keys())}")
topics = ct.get('topics', {})
print(f"  topics: {len(topics)}")
# Count subtopics
sub_count = sum(len(t.get('subtopics', {})) for t in topics.values())
print(f"  subtopics: {sub_count}")

print("\n=== EXISTING TASK FILES ===")
for fname in ['victor2_generated.json', 'curated_bank_L1_L5_fixed.json', 'curated_bank_L1_L5_taxonomy_v2.json']:
    if os.path.exists(fname):
        sz = os.path.getsize(fname)
        with open(fname, encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    print(f"  {fname:45s} {sz:>8} bytes, {len(data)} items")
                    # Check L1-L3 count
                    l13 = [d for d in data if d.get('level') in [1,2,3] or str(d.get('level','')).replace('L','').isdigit()]
                    print(f"    L1-L3 candidates: {len(l13)}")
                elif isinstance(data, dict):
                    print(f"  {fname:45s} {sz:>8} bytes, dict keys={list(data.keys())[:5]}")
            except Exception as e:
                print(f"  {fname:45s} {sz:>8} bytes, ERROR: {e}")

print("\n=== FINAL JSONL STATUS (0 APPROVE) ===")
print("The FINAL JSONL contains 387 tasks but 0 APPROVE — all entries lack quality_status validation.")
print("This means the previous run failed to verify/approve any tasks.")

print("\n=== NEXT STEPS ===")
print("The task requires a taxonomy of 135 final themes. The existing taxonomy has 41 themes (127 subtopics).")
print("Need to:")
print("1. Create the 135-theme final taxonomy (grade x final_theme)")
print("2. Use the existing pipeline infrastructure")
print("3. Set up OpenRouter API for generation")
print("4. Run generation with proper verification")
