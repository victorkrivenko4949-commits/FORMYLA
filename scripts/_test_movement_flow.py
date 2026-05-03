#!/usr/bin/env python3
"""Test the exact user flow for movement tasks on production."""
import requests, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s = requests.Session()
BASE = 'https://formyla-com.onrender.com'

# Step 1: Go to probniks page (get cookies)
r1 = s.get(f'{BASE}/probniks', timeout=15)
print(f'Step 1 - probniks: {r1.status_code}')

# Step 2: Click 'Задачи на движение' -> select grade page
r2 = s.get(f'{BASE}/adaptive_test/select_grade?topic=kl_movement', timeout=15)
print(f'Step 2 - select_grade: {r2.status_code}, URL: {r2.url}')
print(f'  Has grade buttons: {"grade=" in r2.text}')

# Step 3: Select grade 11
r3 = s.get(f'{BASE}/adaptive_test/start?topic=kl_movement&grade=11', allow_redirects=True, timeout=30)
print(f'Step 3 - start test grade 11: {r3.status_code}, URL: {r3.url}')
print(f'  Has answerForm: {"answerForm" in r3.text}')

# Check for flash messages
flashes = re.findall(r'class="flash[^"]*"[^>]*>(.*?)</div>', r3.text, re.DOTALL)
if flashes:
    for f in flashes:
        print(f'  FLASH: {f.strip()[:200]}')
else:
    print('  No flash messages')

# Check for error keywords
error_keywords = ['нет в базе', 'Недостаточно', 'нет задач', 'error', 'ошибка']
for kw in error_keywords:
    if kw.lower() in r3.text.lower():
        print(f'  FOUND ERROR: "{kw}"')

# Check task content
task_match = re.search(r'id="task-text"[^>]*>(.*?)</div>', r3.text, re.DOTALL)
if task_match:
    print(f'  Task text: {task_match.group(1).strip()[:200]}')
else:
    # Try another pattern
    task_match2 = re.search(r'katex-content[^>]*>(.*?)</div>', r3.text, re.DOTALL)
    if task_match2:
        print(f'  Task (katex): {task_match2.group(1).strip()[:200]}')

# Also test grade 10
r4 = s.get(f'{BASE}/adaptive_test/start?topic=kl_movement&grade=10', allow_redirects=True, timeout=30)
print(f'\nStep 4 - start test grade 10: {r4.status_code}, URL: {r4.url}')
print(f'  Has answerForm: {"answerForm" in r4.text}')

# Test grade 5
r5 = s.get(f'{BASE}/adaptive_test/start?topic=kl_movement&grade=5', allow_redirects=True, timeout=30)
print(f'\nStep 5 - start test grade 5: {r5.status_code}, URL: {r5.url}')
print(f'  Has answerForm: {"answerForm" in r5.text}')

print('\nDone!')
