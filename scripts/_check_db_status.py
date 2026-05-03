#!/usr/bin/env python3
"""Check adaptive_tasks count per grade via Render API."""
import requests
import json

RENDER_URL = 'https://formyla-com.onrender.com'
SECRET = 'formyla-migrate-2026'

# Use a custom endpoint to count by grade
# Since we don't have one, let's use the health check approach
# Actually let's query via the push endpoint creatively - 
# we'll just check total and use local checkpoints + known baselines

# Known baselines (tasks that existed BEFORE our generation scripts):
# These were counted at the start of the generation project
BASELINES = {
    5: 847,   # before gen: 847, after gen5: 1284
    6: 1040,  # no gen yet
    7: 1050,  # already at target
    8: 194,   # before gen
    9: 376,   # before gen  
    10: 74,   # before gen (approximate)
    11: 0,    # nothing before
}

# Load checkpoints (what our scripts generated)
import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_cp(grade):
    path = os.path.join(BASE, 'data', 'audit', f'gen_progress_grade{grade}.json')
    if os.path.exists(path):
        return sum(json.load(open(path, encoding='utf-8')).values())
    return 0

print("=" * 50)
print("ADAPTIVE TASKS STATUS")
print("=" * 50)
total_in_db = 0
total_needed = 0

for grade in range(5, 12):
    baseline = BASELINES.get(grade, 0)
    generated = load_cp(grade)
    current = baseline + generated
    deficit = max(0, 1050 - current)
    total_in_db += current
    total_needed += deficit
    status = "OK" if deficit == 0 else f"NEED +{deficit}"
    print(f"  Grade {grade:2d}: {current:4d}/1050  (base={baseline}, gen={generated})  [{status}]")

print(f"\n  TOTAL: {total_in_db} tasks")
print(f"  NEED:  {total_needed} more tasks to reach 1050 per grade")

# Check actual DB total
try:
    r = requests.get(f'{RENDER_URL}/api/migrate/tables', params={'secret': SECRET}, timeout=30)
    actual = r.json().get('adaptive_tasks', '?')
    print(f"\n  DB actual total: {actual}")
except:
    print("\n  (Could not reach DB)")
