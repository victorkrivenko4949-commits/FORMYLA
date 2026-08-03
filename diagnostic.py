#!/usr/bin/env python3
"""Diagnostic: check all methods for issues"""
import json, re

with open('all_methods_real_final.json', 'r', encoding='utf-8') as f:
    methods = json.load(f)

print(f'Total methods: {len(methods)}')
print()

problem1_codes = ['E8','E12','E14','E15','F3']
problem2_codes = ['G1','G2','G3','G4','G5','G7','H3','H5','E5a','F14','F15','F16','F17']

print('=== ALL METHODS STATUS ===')
total_issues = 0
for m in methods:
    code = m['method_code']
    we = m.get('worked_example_md','')
    tasks = we.split('### Задача')
    num = len(tasks)-1

    issues = []
    for i in range(1, len(tasks)):
        t = tasks[i]
        if '**Ответ:**' not in t:
            issues.append(f'T{i}:no_answer')
        if '**Что было главным:**' not in t:
            issues.append(f'T{i}:no_main')

    training = False
    if len(tasks) > 1:
        src_m = re.search(r'\*\*Источник:\*\*\s*(.+?)(?:\n|$)', tasks[1])
        src = src_m.group(1) if src_m else ''
        training = 'тренировочная' in src.lower() or 'классическая задача' in src.lower()

    status = 'OK' if not issues and not training else '!!!'
    extra = ''
    if code in problem1_codes:
        extra += ' [P1]'
    if code in problem2_codes:
        extra += ' [P2]'

    if issues or training:
        total_issues += 1
        print(f'{status} [{code}] tasks={num} issues={issues} training_first={training}{extra}')
    else:
        print(f'OK [{code}] {num} tasks')

print(f'\nTotal methods with issues: {total_issues}')

# Specific check for Problem 1 codes
print('\n=== PROBLEM 1 DETAIL ===')
for code in problem1_codes:
    m = next((x for x in methods if x['method_code'] == code), None)
    if not m:
        print(f'  {code}: NOT FOUND')
        continue
    we = m.get('worked_example_md','')
    tasks = we.split('### Задача')
    last = tasks[-1]
    has_a = '**Ответ:**' in last
    has_m = '**Что было главным:**' in last
    print(f'  {code}: last_task has_answer={has_a} has_main={has_m}')
    print(f'    Last 300 chars: {last[-300:]}')

# Specific check for Problem 2 codes
print('\n=== PROBLEM 2 DETAIL ===')
for code in problem2_codes:
    m = next((x for x in methods if x['method_code'] == code), None)
    if not m:
        print(f'  {code}: NOT FOUND')
        continue
    we = m.get('worked_example_md','')
    tasks = we.split('### Задача')
    if len(tasks) > 1:
        src_m = re.search(r'\*\*Источник:\*\*\s*(.+?)(?:\n|$)', tasks[1])
        src = src_m.group(1) if src_m else 'NOT FOUND'
        training = 'тренировочная' in src.lower() or 'классическая задача' in src.lower()
        print(f'  {code}: source={src[:80]} training={training}')
    else:
        print(f'  {code}: NO TASKS')
