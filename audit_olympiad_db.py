"""
Phase 1 Audit: Examine olympiad tasks database structure and content.
"""
import sys
sys.path.insert(0, '.')

from olympiads import OLYMPIADS_DB

print("=" * 70)
print("PHASE 1: OLYMPIAD DATABASE AUDIT")
print("=" * 70)

total_combos = len(OLYMPIADS_DB)
total_problems = sum(len(c.get('problems', [])) for c in OLYMPIADS_DB)
print(f"\nTotal combos (variants): {total_combos}")
print(f"Total problems: {total_problems}")

# Count by olympiad type
from collections import Counter
olympiad_counts = Counter(c.get('olympiad') for c in OLYMPIADS_DB)
print("\n=== OLYMPIAD TYPES ===")
for oly, cnt in olympiad_counts.most_common():
    print(f"  {oly}: {cnt} combos")

# Count by year
year_counts = Counter(c.get('year') for c in OLYMPIADS_DB)
print("\n=== YEARS ===")
for yr, cnt in sorted(year_counts.items()):
    print(f"  {yr}: {cnt} combos")

# Count by round
round_counts = Counter(c.get('round') for c in OLYMPIADS_DB)
print("\n=== ROUNDS ===")
for rnd, cnt in round_counts.most_common():
    print(f"  {rnd}: {cnt} combos")

# Count by grade
grade_counts = Counter(c.get('grade') for c in OLYMPIADS_DB)
print("\n=== GRADES ===")
for gr, cnt in sorted(grade_counts.items()):
    print(f"  Grade {gr}: {cnt} combos")

# Check solution coverage
problems_with_solution = 0
problems_without_solution = 0
problems_with_source_url = 0
problems_with_source_name = 0
problems_verified = 0

for combo in OLYMPIADS_DB:
    for prob in combo.get('problems', []):
        sol = prob.get('solution', '')
        if sol and sol.strip():
            problems_with_solution += 1
        else:
            problems_without_solution += 1
        if prob.get('source_url'):
            problems_with_source_url += 1
        if prob.get('source_name'):
            problems_with_source_name += 1
        if prob.get('solution_verified'):
            problems_verified += 1

print("\n=== SOLUTION COVERAGE ===")
print(f"  With solution: {problems_with_solution} ({100*problems_with_solution//total_problems}%)")
print(f"  Without solution: {problems_without_solution}")
print(f"  With source_url: {problems_with_source_url}")
print(f"  With source_name: {problems_with_source_name}")
print(f"  Verified (official): {problems_verified}")

# Show sample problem structure
print("\n=== SAMPLE PROBLEM (first combo, first problem) ===")
if OLYMPIADS_DB:
    combo = OLYMPIADS_DB[0]
    print(f"Combo: {combo.get('olympiad_title')} {combo.get('year')}, Grade {combo.get('grade')}, {combo.get('round_title')}")
    if combo.get('problems'):
        prob = combo['problems'][0]
        print(f"Problem keys: {list(prob.keys())}")
        print(f"Text (first 200 chars): {prob.get('text','')[:200]}")
        print(f"Answer: {prob.get('answer','')}")
        sol = prob.get('solution', '')
        print(f"Solution (first 300 chars): {sol[:300] if sol else 'NO SOLUTION'}")

# Show 5 sample combos
print("\n=== SAMPLE COMBOS (first 5) ===")
for combo in OLYMPIADS_DB[:5]:
    print(f"  ID={combo.get('id')} | {combo.get('olympiad')} | {combo.get('year')} | Grade {combo.get('grade')} | {combo.get('round')} | {len(combo.get('problems',[]))} problems")

# Check for any existing source metadata
print("\n=== CHECKING EXISTING SOURCE METADATA ===")
sample_with_meta = []
for combo in OLYMPIADS_DB:
    for prob in combo.get('problems', []):
        if prob.get('source_url') or prob.get('source_name') or prob.get('author'):
            sample_with_meta.append({
                'combo_id': combo.get('id'),
                'olympiad': combo.get('olympiad'),
                'prob_num': prob.get('num'),
                'source_url': prob.get('source_url'),
                'source_name': prob.get('source_name'),
                'author': prob.get('author'),
            })

if sample_with_meta:
    print(f"Found {len(sample_with_meta)} problems with existing metadata:")
    for m in sample_with_meta[:5]:
        print(f"  {m}")
else:
    print("  No existing source_url/source_name/author fields found in problems.")

# Check combo-level metadata
print("\n=== CHECKING COMBO-LEVEL METADATA ===")
combo_with_meta = [c for c in OLYMPIADS_DB if c.get('source_url') or c.get('source_name')]
if combo_with_meta:
    print(f"Found {len(combo_with_meta)} combos with source metadata")
    for c in combo_with_meta[:3]:
        print(f"  {c.get('id')}: {c.get('source_url')} | {c.get('source_name')}")
else:
    print("  No source_url/source_name at combo level either.")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)
