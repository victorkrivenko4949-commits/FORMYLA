#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix ALL remaining work-rate/non-movement tasks in subject='movement'."""
import sys, os, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from problems import PROBLEMS_DB

# Real movement keywords — if a task has these, it IS movement
real_movement_re = re.compile(
    r'скорост\w+\s+\d|км/ч|м/с|навстречу|вдогонку|обгон\w*|догнал|'
    r'выехал|отправил\w+\s+из|из\s+пункта|из\s+города|'
    r'расстояни\w+\s+между|весь\s+путь|половин\w+\s+пути|'
    r'по\s+течени|против\s+течени|собственн\w+\s+скорост|'
    r'поезд\w*\s+\w*\s*выех|автомобил\w*\s+\w*\s*выех|'
    r'велосипедист|пешеход|мотоциклист|автобус\w*\s+\w*\s*выех|'
    r'катер\w*\s+\w*\s*плыв|лодк\w*\s+\w*\s*плыв|'
    r'проехал\s+\d|прошёл\s+\d|пролетел\s+\d|'
    r'движ\w+\s+навстречу|движ\w+\s+в\s+одном\s+направлен|'
    r'встретил\w+\s+через|время\s+в\s+пути',
    re.IGNORECASE
)

fixed = 0
for p in PROBLEMS_DB:
    if p.get('subject') != 'movement':
        continue
    text = p.get('text', '')
    
    # If it does NOT match real movement keywords → reclassify
    if not real_movement_re.search(text):
        old_sub = p['subtopic']
        p['subject'] = 'algebra'
        p['subtopic'] = 'text_problems'
        fixed += 1
        print(f"  Fixed ID={p['id']}, grade={p['grade']}: movement/{old_sub} → algebra/text_problems")
        print(f"    {text[:120]}")
        print()

print(f"\nTotal fixed: {fixed}")

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
    try:
        compile(open('problems.py', 'r', encoding='utf-8').read(), 'problems.py', 'exec')
        print("✅ Syntax check PASSED")
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
    
    # Final stats
    exec_globals = {}
    exec(compile(open('problems.py', 'r', encoding='utf-8').read(), 'problems.py', 'exec'), exec_globals)
    db = exec_globals['PROBLEMS_DB']
    mov = sum(1 for p in db if p.get('subject') == 'movement')
    alg = sum(1 for p in db if p.get('subject') == 'algebra')
    print(f"✅ Movement: {mov}, Algebra: {alg}, Total: {len(db)}")
