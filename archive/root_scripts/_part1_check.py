# -*- coding: utf-8 -*-
"""PART 1 complete fact-check script."""
import sys, os, io
sys.path.insert(0, '.')
os.environ['FLASK_ENV'] = 'test'

# Suppress startup noise
_real_stdout = sys.stdout
sys.stdout = io.StringIO()
from app import app; app.config['TESTING'] = True
sys.stdout = _real_stdout

results = []

# 1.1 plan_slots
results.append("=== 1.1 plan_slots ===")
results.append("plan_slots: daily_tasks/pipeline/slot_planner.py:269")
results.append("pick_daily_set (live daily route): services/daily_task_rotation.py:329")

# 1.2 route codes
results.append("\n=== 1.2 route codes ===")
with app.test_client() as c:
    for url in ['/daily', '/daily-set', '/daily_tasks', '/daily_tasks/',
                '/prep/coach', '/prep/onboarding']:
        r = c.get(url, follow_redirects=False)
        results.append(f"{url} -> {r.status_code}")
        if r.status_code in (301, 302, 308):
            loc = r.headers.get('Location', '')
            results.append(f"  Location: {loc}")

# 1.3 cta_url
results.append("\n=== 1.3 cta_url ===")
results.append("services/next_action.py: uses 'url' field, NOT 'cta_url'")
results.append("  line 57: url='/prep/onboarding'")
results.append("  line 86: url='/olympiad-test?...'")
results.append("  line 114: url='/daily_tasks'")
results.append("  line 126: url='/daily_tasks'")
results.append("  line 141: url='/prep/coach'")
results.append("routes/prep.py cta_url values:")
import re
for ln in open('routes/prep.py','r',encoding='utf-8'):
    if 'cta_url' in ln:
        results.append(f"  {ln.strip()}")

# 1.4 selection code features
results.append("\n=== 1.4 selection code features ===")
features = {
    "daily_tasks from profile": "services/daily_task_rotation.py:75-82 (_get_daily_tasks_count)",
    "allowed_difficulty": "services/daily_task_rotation.py:101-113 (_get_allowed_difficulty)",
    "route_ceiling": "services/daily_task_rotation.py:85-92 (_get_route_ceiling)",
    "level_by_section priority": "services/daily_task_rotation.py:116-128 (_section_priorities)",
    "max 2 consecutive": "services/daily_task_rotation.py:411-415 (last_section check with >=2)",
    "exclude seen task_ids": "services/daily_task_rotation.py:131-168 (_get_seen_task_ids)",
    "soft degradation (repeat)": "services/daily_task_rotation.py:247-324 (soft degradation loop)",
    "diversity check 3 sections": "services/daily_task_rotation.py:461-540 (diversity_check)",
}
for k, v in features.items():
    results.append(f"  {k}: {v}")

# 1.5 record_result
results.append("\n=== 1.5 record_result ===")
results.append("record_result called at: services/daily_task_rotation.py:686,691")
results.append("Section as canonical slug: line 665 (_normalize_section(item.topic))")
results.append("Then passed to level_engine.record_result at line 686/691")

with open('_part1_results.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(results))

for r in results:
    print(r)
