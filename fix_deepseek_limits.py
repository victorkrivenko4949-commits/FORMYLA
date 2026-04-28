# -*- coding: utf-8 -*-
"""Fix DeepSeek max_tokens limits in app.py"""

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

fixes = [
    (
        'max_tokens=1500  # Увеличено для детального разбора с LaTeX (timeout=90 уже в классе)',
        'max_tokens=4096  # Достаточно для детального разбора с LaTeX (timeout=90 уже в классе)',
        'adaptive checker 1500->4096'
    ),
    (
        'ai_feedback = client.generate(prompt, max_tokens=200)',
        'ai_feedback = client.generate(prompt, max_tokens=1000)',
        'ai_feedback 200->1000'
    ),
    (
        'ai_summary = client.generate(prompt, max_tokens=200)',
        'ai_summary = client.generate(prompt, max_tokens=1000)',
        'ai_summary 200->1000'
    ),
]

changed = 0
for old, new, label in fixes:
    if old in content:
        content = content.replace(old, new, 1)
        print(f'FIXED: {label}')
        changed += 1
    else:
        print(f'NOT FOUND: {label}')

if changed > 0:
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'\nSaved app.py with {changed} fixes')
else:
    print('\nNo changes needed')
