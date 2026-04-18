import json

for grade in [8, 9, 10, 11]:
    filename = f'adaptive_150_tasks_grade{grade}_FINAL.json'
    data = json.load(open(filename, encoding='utf-8'))
    
    seen = set()
    unique = []
    
    for t in data:
        sig = (t['topic'], t['difficulty_level'])
        if sig not in seen:
            seen.add(sig)
            unique.append(t)
    
    json.dump(unique, open(filename, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'Grade {grade}: {len(data)} -> {len(unique)}')

print('\nFinal counts:')
total = 0
for grade in [8, 9, 10, 11]:
    data = json.load(open(f'adaptive_150_tasks_grade{grade}_FINAL.json', encoding='utf-8'))
    print(f'  Grade {grade}: {len(data)}/150')
    total += len(data)

print(f'\nTOTAL: {total}/600')
