#!/usr/bin/env python
"""Diagnose the mapping between curated bank, regenerated output, and DB."""
import json
import sys

# Load regenerated output (smaller file)
print("=" * 60)
print("LOADING REGENERATED OUTPUT")
with open("_regenerated_675_tasks.json", "r", encoding="utf-8") as f:
    regen = json.load(f)
results = regen.get("results", [])
print(f"  Total results: {len(results)}")
successful = [r for r in results if r.get("success")]
failed = [r for r in results if not r.get("success")]
print(f"  Successful: {len(successful)}")
print(f"  Failed: {len(failed)}")

# Show first successful result structure
if successful:
    r0 = successful[0]
    print(f"\n  First successful result keys: {list(r0.keys())}")
    print(f"  original_id: {r0.get('original_id')}")
    print(f"  task_index: {r0.get('task_index')}")
    st = r0.get("source_task", {})
    print(f"  source_task keys: {list(st.keys())}")
    print(f"  source_task.task_text: {str(st.get('task_text', ''))[:80]}")
    print(f"  source_task.source_index: {st.get('source_index')}")
    ft = r0.get("fixed_task", {})
    print(f"  fixed_task keys: {list(ft.keys())}")
    print(f"  fixed_task.statement: {str(ft.get('statement', ''))[:80]}")

# Show first failed result
if failed:
    f0 = failed[0]
    print(f"\n  First failed result keys: {list(f0.keys())}")
    print(f"  original_id: {f0.get('original_id')}")
    print(f"  error: {str(f0.get('error', ''))[:200]}")

# Load DB (first 100 tasks only to save time)
print("\n" + "=" * 60)
print("LOADING DB (first 200 tasks)")
with open("adaptive_data/adaptive_full_9120_fixed.json", "r", encoding="utf-8") as f:
    db = json.load(f)
print(f"  Total DB tasks: {len(db)}")
print(f"  First task id: {db[0].get('id')}")
print(f"  First task statement: {str(db[0].get('statement', ''))[:80]}")

# Try to find curated bank tasks in DB using statement matching
# Use fixed_task.statement from regenerated output
print("\n" + "=" * 60)
print("MATCHING REGENERATED TASKS TO DB (sample of 10)")

# Build DB fingerprint index (first 80 chars, lowercase, no spaces)
db_index = {}
for i, t in enumerate(db):
    stmt = t.get("statement", "").strip()
    if stmt:
        fp = stmt[:80].lower().replace(" ", "")
        db_index[fp] = i

matches_found = 0
no_match = 0
for r in successful[:100]:  # Check first 100
    ft = r.get("fixed_task", {})
    stmt = ft.get("statement", "").strip()
    if not stmt:
        no_match += 1
        continue
    fp = stmt[:80].lower().replace(" ", "")
    if fp in db_index:
        matches_found += 1
        db_idx = db_index[fp]
        db_task = db[db_idx]
        print(f"  MATCH: original_id={r.get('original_id')}")
        print(f"    DB id={db_task.get('id')}, statement matches fixed_task.statement")
    else:
        no_match += 1

print(f"\n  Matches found (first 100): {matches_found}")
print(f"  No match (first 100): {no_match}")

# Also try matching source_task.task_text to DB statements
print("\n" + "=" * 60)
print("MATCHING SOURCE TASK TEXT TO DB (sample of 10)")
db_index2 = {}
for i, t in enumerate(db):
    stmt = t.get("statement", "").strip()
    if stmt:
        fp = stmt[:80].lower().replace(" ", "")
        db_index2[fp] = i

src_matches = 0
src_no_match = 0
for r in successful[:100]:
    st = r.get("source_task", {})
    txt = st.get("task_text", "").strip()
    if not txt:
        src_no_match += 1
        continue
    fp = txt[:80].lower().replace(" ", "")
    if fp in db_index2:
        src_matches += 1
    else:
        src_no_match += 1

print(f"  Source matches (first 100): {src_matches}")
print(f"  Source no match (first 100): {src_no_match}")

print("\nDone!")
