with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '    print(f"Начинаем модификацию задач через AI...")'
new = '''    # Применяем fix_latex к каждой задаче перед возвратом
    try:
        from services.task_validator import fix_latex
        for p in selected:
            if p.get('text'):
                p['text'] = fix_latex(p['text'])
    except Exception as e:
        print(f"fix_latex error: {e}")
    print(f"Начинаем модификацию задач через AI...")'''

if old in content:
    content = content.replace(old, new, 1)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK: fix_latex applied to generate_variant')
else:
    print('NOT FOUND')
    idx = content.find('Начинаем модификацию')
    print(f'Found at {idx}')
    print(repr(content[idx-50:idx+100]))
