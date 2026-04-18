import json

for grade in [8, 9, 10, 11]:
    filename = f'adaptive_150_tasks_grade{grade}_FINAL.json'
    data = json.load(open(filename, encoding='utf-8'))
    
    # Удаляем все задачи уровня 3 (это якорные задачи)
    filtered = [t for t in data if t['difficulty_level'] != 3]
    
    print(f'Grade {grade}: {len(data)} -> {len(filtered)} (removed {len(data) - len(filtered)} level-3 tasks)')
    
    json.dump(filtered, open(filename, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

print('\nFinal counts:')
total = 0
for grade in [8, 9, 10, 11]:
    data = json.load(open(f'adaptive_150_tasks_grade{grade}_FINAL.json', encoding='utf-8'))
    print(f'  Grade {grade}: {len(data)}/150')
    total += len(data)

print(f'\nTOTAL: {total}/600')
