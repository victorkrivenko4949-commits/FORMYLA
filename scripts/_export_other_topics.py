#!/usr/bin/env python3
"""Export sample tasks from working topics for comparison."""
import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

RENDER_URL = 'https://formyla-com.onrender.com'
SECRET = 'formyla-migrate-2026'

# Get first 500 rows (should contain algebra, geometry, etc.)
r = requests.get(f'{RENDER_URL}/api/migrate/export', params={
    'secret': SECRET, 'table': 'adaptive_tasks', 'offset': 0, 'limit': 500
}, timeout=60)

data = r.json()
rows = data['rows']

# Group by topic, take 2 samples each
from collections import defaultdict
by_topic = defaultdict(list)
for row in rows:
    topic = row.get('topic', '')
    if len(by_topic[topic]) < 2:
        by_topic[topic].append(row)

# Export algebra sample
algebra_tasks = [r for r in rows if 'алгебр' in (r.get('topic','') or '').lower() or 'тождеств' in (r.get('topic','') or '').lower()][:5]
geometry_tasks = [r for r in rows if 'геометр' in (r.get('topic','') or '').lower() or 'начала' in (r.get('topic','') or '').lower()][:5]

with open('data/algebra_sample.json', 'w', encoding='utf-8') as f:
    json.dump(algebra_tasks, f, ensure_ascii=False, indent=2)
print(f'Algebra sample: {len(algebra_tasks)} tasks saved to data/algebra_sample.json')

with open('data/geometry_sample.json', 'w', encoding='utf-8') as f:
    json.dump(geometry_tasks, f, ensure_ascii=False, indent=2)
print(f'Geometry sample: {len(geometry_tasks)} tasks saved to data/geometry_sample.json')

# Show all unique topics in first 500 rows
topics = set(r.get('topic','') for r in rows)
print(f'\nUnique topics in first 500 rows:')
for t in sorted(topics):
    count = sum(1 for r in rows if r.get('topic') == t)
    print(f'  [{t}]: {count}')
