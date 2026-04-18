import json
from collections import Counter

for grade in [8, 10]:
    data = json.load(open(f'adaptive_150_tasks_grade{grade}_FINAL.json', encoding='utf-8'))
    topics = Counter([t['topic'] for t in data])
    
    print(f'\nGrade {grade}: {len(data)} tasks')
    bad = {k:v for k,v in topics.items() if v != 6}
    
    if bad:
        print('Topics with != 6 tasks:')
        for k, v in sorted(bad.items()):
            print(f'  {k}: {v}')
            
            # Показать уровни для этой темы
            levels = [t['difficulty_level'] for t in data if t['topic'] == k]
            print(f'    Levels: {sorted(levels)}')
