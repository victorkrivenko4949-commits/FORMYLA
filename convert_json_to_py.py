#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Конвертация JSON в Python формат"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json

# Читаем как JSON
with open('problems.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Пробуем распарсить
try:
    data = json.loads(content)
    print(f"OK: JSON валиден: {len(data)} задач")
    print(f"Пример: subject='{data[0].get('subject')}', subtopic='{data[0].get('subtopic')}', difficulty={data[0].get('difficulty')}")
    
    # Сохраняем в правильном Python формате
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('PROBLEMS_DB = ')
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    
    print("OK: Сохранено в Python формате")
    
    # Проверяем импорт
    from problems import PROBLEMS_DB
    print(f"OK: Импорт успешен: {len(PROBLEMS_DB)} задач")
    print(f"OK: Первая задача: grade={PROBLEMS_DB[0].get('grade')}, difficulty={PROBLEMS_DB[0].get('difficulty')}")
    
except json.JSONDecodeError as e:
    print(f"ERROR: JSON ошибка: {e}")
except Exception as e:
    print(f"ERROR: {e}")
