#!/usr/bin/env python3
"""Debug: what does the user actually see when clicking movement topic."""
import requests, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s = requests.Session()
BASE = 'https://formyla-com.onrender.com'

# Get initial cookies
s.get(f'{BASE}/probniks', timeout=15)

# Start movement test for grade 11
r = s.get(f'{BASE}/adaptive_test/start?topic=kl_movement&grade=11', allow_redirects=True, timeout=30)
print(f'Final URL: {r.url}')
print(f'Status: {r.status_code}')
print(f'Page length: {len(r.text)} chars')
print()

# Search for key content
searches = [
    ('answerForm', 'answerForm'),
    ('task text area', 'id="task-text"'),
    ('katex-content', 'katex-content'),
    ('movement word', 'движени'),
    ('speed word', 'скорост'),
    ('km/h', 'км/ч'),
    ('flash error', 'нет в базе'),
    ('insufficient', 'Недостаточно'),
    ('topic name', 'Задачи на движение'),
    ('select_grade redirect', 'select_grade'),
]

for name, pattern in searches:
    found = pattern in r.text
    idx = r.text.find(pattern)
    print(f'  {name}: {"FOUND at " + str(idx) if found else "NOT FOUND"}')

print()

# Extract a chunk around the task display
# Look for the main content div
for marker in ['<div class="task-body', '<div id="task-body', 'class="task-text']:
    idx = r.text.find(marker)
    if idx >= 0:
        chunk = r.text[idx:idx+800]
        clean = re.sub(r'<[^>]+>', ' ', chunk).strip()
        clean = re.sub(r'\s+', ' ', clean)
        print(f'Content near "{marker}":')
        print(f'  {clean[:400]}')
        print()
        break

# Also extract around "Тема" display
for marker in ['Тема:', 'topic_name', 'adaptive_topic']:
    idx = r.text.find(marker)
    if idx >= 0:
        chunk = r.text[idx:idx+200]
        clean = re.sub(r'<[^>]+>', ' ', chunk).strip()
        print(f'Near "{marker}": {clean[:150]}')
        print()

# Save full HTML for inspection
with open('data/logs/_movement_page.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print('Full HTML saved to data/logs/_movement_page.html')
