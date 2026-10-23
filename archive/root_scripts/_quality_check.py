#!/usr/bin/env python3
"""Quality check for all_methods_real_final.json"""
import json

d = json.load(open('all_methods_real_final.json', 'r', encoding='utf-8'))

real = 0
bad = []
for m in d:
    we = m.get('worked_example_md', '')
    has_z1 = '### Задача 1' in we
    has_source = '**Источник:**' in we
    has_thinking = '**Как думать' in we
    has_solution = '**Решение:**' in we
    has_answer = '**Ответ:**' in we
    has_main = '**Что было главным:**' in we
    if has_z1 and has_source and has_thinking and has_solution and has_answer and has_main:
        real += 1
    else:
        missing = []
        if not has_z1: missing.append('Задача_1')
        if not has_source: missing.append('Источник')
        if not has_thinking: missing.append('Как_думать')
        if not has_solution: missing.append('Решение')
        if not has_answer: missing.append('Ответ')
        if not has_main: missing.append('Главное')
        bad.append(f'{m["method_code"]}: {missing}')

with open('quality_check.txt', 'w', encoding='utf-8') as f:
    f.write(f'Total methods: {len(d)}\n')
    f.write(f'Fully compliant: {real}/{len(d)}\n')
    f.write(f'Issues ({len(bad)}):\n')
    for b in bad:
        f.write(f'  {b}\n')

print(f'Fully compliant: {real}/{len(d)}')
print(f'Issues: {len(bad)}')
for b in bad:
    print(f'  {b}')
