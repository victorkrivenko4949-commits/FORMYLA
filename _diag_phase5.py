#!/usr/bin/env python3
"""Diagnose the current state for Phase 5: filling missing L3 tasks."""
import json, sys
from collections import Counter

DOWN = r'C:\Users\Victor\Downloads'

sys.stdout = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)

print("=" * 60)
print("PHASE 5 DIAGNOSTIC")
print("=" * 60)

# Load output main
with open(f'{DOWN}/final_clean_dataset_5levels.json', 'r', encoding='utf-8') as f:
    out_main = json.load(f)

# Get max ID
ids = [t['id'] for t in out_main]
print(f"\nMax ID in main: {max(ids)}")
print(f"Min ID in main: {min(ids)}")
print(f"Total main tasks: {len(out_main)}")

# L3 incomplete cells
l3 = [t for t in out_main if t['difficulty'] == 3]
l3_cells = Counter((t['grade'], t['method_code']) for t in l3)
incomplete = {k: v for k, v in l3_cells.items() if v < 5}

print(f"\nL3 cells in main: {len(l3_cells)}")
print(f"Incomplete L3 cells: {len(incomplete)}")
print(f"Total deficit: {sum(5 - v for v in incomplete.values())}")
print()

# Show existing tasks in incomplete cells (just IDs and status)
print("=" * 60)
print("EXISTING TASKS IN INCOMPLETE CELLS")
print("=" * 60)
for (g, m), cnt in sorted(incomplete.items()):
    cell_tasks = [t for t in l3 if t['grade'] == g and t['method_code'] == m]
    print(f"\nGrade={g}, Method={m}: {cnt}/5 tasks (need {5-cnt})")
    for t in cell_tasks:
        print(f"  id={t['id']}, status={t.get('status')}, theme={t.get('theme')}")

print("\n" + "=" * 60)
print("OLYMPIAD DATA FILES")
print("=" * 60)

# Check vsosh_9_2027_tasks_v3.json
try:
    with open(f'{DOWN}/vsosh_9_2027_tasks_v3.json', 'r', encoding='utf-8') as f:
        vsosh9 = json.load(f)
    print(f"\nvsosh_9_2027_tasks_v3.json: type={type(vsosh9).__name__}", end="")
    if isinstance(vsosh9, list):
        print(f", len={len(vsosh9)}")
        if len(vsosh9) > 0:
            keys = list(vsosh9[0].keys()) if isinstance(vsosh9[0], dict) else 'N/A'
            print(f"  Sample task keys: {keys}")
            if isinstance(vsosh9[0], dict):
                for k, v in vsosh9[0].items():
                    sv = str(v)[:80]
                    print(f"    {k}: {sv}")
    elif isinstance(vsosh9, dict):
        print(f", keys={list(vsosh9.keys())[:20]}")
except Exception as e:
    print(f"\nvsosh_9_2027_tasks_v3.json: ERROR {e}")

# Check vsosh_zadachi_10_11_2027.json
try:
    with open(f'{DOWN}/vsosh_zadachi_10_11_2027.json', 'r', encoding='utf-8') as f:
        vsosh10 = json.load(f)
    print(f"\nvsosh_zadachi_10_11_2027.json: type={type(vsosh10).__name__}", end="")
    if isinstance(vsosh10, list):
        print(f", len={len(vsosh10)}")
        if len(vsosh10) > 0:
            keys = list(vsosh10[0].keys()) if isinstance(vsosh10[0], dict) else 'N/A'
            print(f"  Sample task keys: {keys}")
            if isinstance(vsosh10[0], dict):
                for k, v in vsosh10[0].items():
                    sv = str(v)[:80]
                    print(f"    {k}: {sv}")
    elif isinstance(vsosh10, dict):
        print(f", keys={list(vsosh10.keys())[:20]}")
except Exception as e:
    print(f"\nvsosh_zadachi_10_11_2027.json: ERROR {e}")

# Check olympiad_DB_final_fixed.jsonl
try:
    with open(f'{DOWN}/olympiad_DB_final_fixed.jsonl', 'r', encoding='utf-8') as f:
        lines = [l.strip() for l in f if l.strip()]
    print(f"\nolympiad_DB_final_fixed.jsonl: {len(lines)} lines")
    if len(lines) > 0:
        entry = json.loads(lines[0])
        print(f"  Sample entry keys: {list(entry.keys())}")
        for k, v in entry.items():
            sv = str(v)[:80]
            print(f"    {k}: {sv}")
except Exception as e:
    print(f"\nolympiad_DB_final_fixed.jsonl: ERROR {e}")

# Check formyla_dataset_slightly_fixed.json
try:
    with open(f'{DOWN}/formyla_dataset_slightly_fixed.json', 'r', encoding='utf-8') as f:
        formyla = json.load(f)
    print(f"\nformyla_dataset_slightly_fixed.json: type={type(formyla).__name__}", end="")
    if isinstance(formyla, list):
        print(f", len={len(formyla)}")
        if len(formyla) > 0:
            keys = list(formyla[0].keys()) if isinstance(formyla[0], dict) else 'N/A'
            print(f"  Sample keys: {keys}")
            if isinstance(formyla[0], dict):
                for k, v in formyla[0].items():
                    sv = str(v)[:80]
                    print(f"    {k}: {sv}")
    elif isinstance(formyla, dict):
        print(f", keys={list(formyla.keys())[:20]}")
except Exception as e:
    print(f"\nformyla_dataset_slightly_fixed.json: ERROR {e}")

# Check methods catalog
try:
    with open('data/olympiads/methods_catalog_105.json', 'r', encoding='utf-8') as f:
        catalog = json.load(f)
    print(f"\nmethods_catalog_105.json: type={type(catalog).__name__}")
    if isinstance(catalog, list):
        print(f"  len={len(catalog)}")
        if len(catalog) > 0:
            print(f"  Sample: {json.dumps(catalog[0], ensure_ascii=False)[:200]}")
    elif isinstance(catalog, dict):
        print(f"  keys={list(catalog.keys())[:20]}")
        # Show a few entries
        for k in list(catalog.keys())[:10]:
            print(f"  {k}: {str(catalog[k])[:100]}")
except Exception as e:
    print(f"\nmethods_catalog_105.json: ERROR {e}")
