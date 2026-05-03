#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix tasks about pipes/pools/escalators that are wrongly classified as 'movement'.
These are 'work rate' problems, not motion problems."""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

# Keywords that indicate work-rate problems (NOT movement)
work_rate_re = re.compile(
    r'труб\w+\s+наполн|наполн\w+\s+бассейн|бассейн\w*\s+за\s+\d|'
    r'опустош\w+\s+бассейн|слив\w+\s+труб|наполнительн\w+\s+труб|'
    r'эскалатор|ступен\w+\s+эскалатор',
    re.IGNORECASE
)

# Real movement keywords
movement_re = re.compile(
    r'движен|скорост|км/ч|м/с|навстречу|поезд|велосипед|автомобил|'
    r'пешеход|катер|лодк|течени|вдогонку|обгон|догнал|выехал',
    re.IGNORECASE
)

fixed = 0
for p in PROBLEMS_DB:
    if p.get('subject') != 'movement':
        continue
    text = p.get('text', '')
    
    # If it matches work-rate keywords and NOT real movement keywords
    if work_rate_re.search(text) and not movement_re.search(text):
        old_sub = p['subtopic']
        p['subject'] = 'algebra'
        p['subtopic'] = 'text_problems'
        fixed += 1
        print(f"  Fixed ID={p['id']}: movement/{old_sub} → algebra/text_problems")
        print(f"    {text[:100]}")
        print()

print(f"\nTotal fixed: {fixed}")

# Write back
if fixed > 0:
    print("\nWriting corrected problems.py...")
    lines = ['PROBLEMS_DB = [\n']
    for i, task in enumerate(PROBLEMS_DB):
        text_escaped = task['text'].replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        answer_escaped = str(task['answer']).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        
        entry = (
            f'    {{\n'
            f'        "id": {task["id"]},\n'
            f'        "subject": "{task["subject"]}",\n'
            f'        "subtopic": "{task["subtopic"]}",\n'
            f'        "grade": {task["grade"]},\n'
            f'        "difficulty": {task["difficulty"]},\n'
            f'        "text": "{text_escaped}",\n'
            f'        "answer": "{answer_escaped}"\n'
            f'    }}'
        )
        if i < len(PROBLEMS_DB) - 1:
            entry += ','
        lines.append(entry + '\n')
    lines.append(']\n')

    with open('problems.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)

    # Verify
    try:
        compile(open('problems.py', 'r', encoding='utf-8').read(), 'problems.py', 'exec')
        print("✅ Syntax check PASSED")
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")

    # Final stats
    exec_globals = {}
    exec(compile(open('problems.py', 'r', encoding='utf-8').read(), 'problems.py', 'exec'), exec_globals)
    db = exec_globals['PROBLEMS_DB']
    movement_count = sum(1 for p in db if p.get('subject') == 'movement')
    algebra_count = sum(1 for p in db if p.get('subject') == 'algebra')
    print(f"✅ Movement tasks now: {movement_count}")
    print(f"✅ Algebra tasks now: {algebra_count}")
    print(f"✅ Total: {len(db)}")
