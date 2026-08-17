import json
from collections import Counter

tasks = []
seen = set()
with open('_all_tasks.jsonl', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get('level') not in (1, 2, 3, 4):
            continue
        if not d.get('task_text', '').strip():
            continue
        key = (d['grade'], d['topic'], d['level'], d.get('position', 0))
        if key in seen:
            continue
        seen.add(key)
        tasks.append(d)

tasks.sort(key=lambda t: (t['grade'], t['topic'], t['level'], t.get('position', 0)))

with open('_tasks_all_done.jsonl', 'w', encoding='utf-8') as f:
    for t in tasks:
        f.write(json.dumps(t, ensure_ascii=False) + '\n')

by_grade = Counter(t['grade'] for t in tasks)
by_level = Counter(t['level'] for t in tasks)

print(f'Total unique valid tasks (L1-L4): {len(tasks)}')
print('By grade:', dict(sorted(by_grade.items())))
print('By level:', dict(sorted(by_level.items())))
print('Saved to _tasks_all_done.jsonl')
