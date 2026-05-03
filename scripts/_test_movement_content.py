#!/usr/bin/env python3
"""Check what task content is shown for movement topic."""
import requests, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s = requests.Session()
BASE = 'https://formyla-com.onrender.com'

for grade in [5, 7, 9, 11]:
    # Start fresh session each time
    s = requests.Session()
    s.get(f'{BASE}/probniks', timeout=15)
    r = s.get(f'{BASE}/adaptive_test/start?topic=kl_movement&grade={grade}', allow_redirects=True, timeout=30)
    
    # Extract task text from the page
    # Look for the task text div
    patterns = [
        r'<div[^>]*class="[^"]*task-text[^"]*"[^>]*>(.*?)</div>',
        r'<div[^>]*id="taskText"[^>]*>(.*?)</div>',
        r'katex-content[^>]*>(.*?)</div>',
        r'<p[^>]*class="[^"]*task[^"]*"[^>]*>(.*?)</p>',
    ]
    
    task_text = None
    for pat in patterns:
        m = re.search(pat, r.text, re.DOTALL | re.IGNORECASE)
        if m:
            task_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            break
    
    # Also try to find topic name displayed
    topic_shown = re.search(r'Тема:?\s*(.*?)<', r.text)
    
    # Check for movement keywords in the full page
    movement_words = ['скорост', 'движен', 'км/ч', 'навстречу', 'выехал', 'пешеход', 'велосипед']
    found_movement = [w for w in movement_words if w in r.text.lower()]
    
    print(f'=== Grade {grade} ===')
    print(f'  URL: {r.url}')
    print(f'  Task text: {task_text[:150] if task_text else "NOT FOUND"}')
    print(f'  Topic shown: {topic_shown.group(1).strip()[:50] if topic_shown else "NOT FOUND"}')
    print(f'  Movement words in page: {found_movement}')
    print()
