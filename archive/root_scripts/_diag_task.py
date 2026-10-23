import requests, sys, os
sys.stdout.reconfigure(encoding='utf-8')
s = requests.Session()
s.get('http://127.0.0.1:5000/dev_login?uid=1', allow_redirects=True)
s.get('http://127.0.0.1:5000/olympiad-test?length=10&level_hint=2&scope=all_sections')
r = s.get('http://127.0.0.1:5000/olympiad-test/select-section?grade=7', allow_redirects=False)
print(f"select-section status: {r.status_code} location: {r.headers.get('Location','NONE')}")
r2 = s.get('http://127.0.0.1:5000/olympiad-test/start?grade=7', allow_redirects=True)
print(f"start url: {r2.url}")
print(f"start has olympiad_test_run: {'olympiad_test_run' in r2.text}")
print(f"page len: {len(r2.text)}")

# Find task-data in page
import re
# Look for data attributes or JSON in the page
for pat in ['data-task', 'task-uid', 'task_uid', 'taskUid', 'var task', 'const task',
            'task_data', 'taskData', 'currentTask', 'current_task']:
    if pat in r2.text:
        idx = r2.text.index(pat)
        print(f"FOUND '{pat}' at {idx}: {r2.text[idx:idx+120]}")

# Save page
with open('_task_page.html', 'w', encoding='utf-8') as f:
    f.write(r2.text)
print("SAVED _task_page.html")

# Look for the actual statement
# Check if task is passed to template
body = r2.text
# Find anything between body tags
bm = re.search(r'<body[^>]*>(.*)</body>', body, re.DOTALL)
if bm:
    # Check for the main content
    main = bm.group(1)
    # Find h1, h2, or any heading-like structure
    for tag in ['h1', 'h2', 'h3', 'class="task', 'task-text', 'problem-card', 'answer-form']:
        if tag in main:
            idx = main.index(tag)
            print(f"TAG '{tag}' at {idx}: ...{main[idx:idx+100]}...")
