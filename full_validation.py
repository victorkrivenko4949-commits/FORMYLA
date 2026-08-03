#!/usr/bin/env python3
"""Full validation of all_methods_real_final.json"""
import json, re, sys

with open('all_methods_real_final.json', 'r', encoding='utf-8') as f:
    methods = json.load(f)

print(f'JSON valid: YES, methods: {len(methods)}')
print()

total_issues = 0
code_order = [m['method_code'] for m in methods]

for m in methods:
    code = m['method_code']
    we = m.get('worked_example_md','')
    tasks = we.split('### Задача')
    n = len(tasks)-1
    
    missing = []
    for i in range(1, len(tasks)):
        if '**Ответ:**' not in tasks[i]:
            missing.append(f'T{i}:no_answer')
        if '**Что было главным:**' not in tasks[i]:
            missing.append(f'T{i}:no_main')
    
    # First task is training?
    training = False
    if len(tasks) > 1:
        sm = re.search(r'\*\*Источник:\*\*\s*(.+?)(?:\n|$)', tasks[1])
        src = sm.group(1).strip() if sm else ''
        training = 'тренировочная' in src.lower() or 'классическая задача' in src.lower()
    elif n == 0:
        training = True  # no tasks at all
    
    if missing or training:
        total_issues += 1
        print(f'ISSUE [{code}]: n_tasks={n} missing={missing} training_first={training}')
    else:
        pass  # OK

print(f'\nTotal methods with issues: {total_issues}/{len(methods)}')

if total_issues == 0:
    print('ALL CHECKS PASSED!')
else:
    print('REMAINING ISSUES TO FIX')
    sys.exit(1)
