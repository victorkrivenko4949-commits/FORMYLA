import json

# Загружаем из JSON
data = json.load(open('../../Downloads/problems_all_2205.json', 'r', encoding='utf-8'))

# Исправляем задачу 2019
task = next(p for p in data if p.get('id')==2019)
task['text'] = r'Докажи, что уравнение \( x^4 + 4x^2 + 5 = 0 \) не имеет вещественных корней, и найди все комплексные корни.'

# Сохраняем правильно
with open('problems.py', 'w', encoding='utf-8') as f:
    f.write('# -*- coding: utf-8 -*-\n')
    f.write('# Baza zadach FORMYLA - 2205 zadach\n\n')
    f.write('PROBLEMS_DB = ')
    f.write(repr(data))

print(f'Zagruzheno: {len(data)} zadach')
print('Ispravlena zadacha ID=2019')
print('Sohraneno v problems.py')
