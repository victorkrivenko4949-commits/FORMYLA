#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Догенерация 20 недостающих задач для неполных ячеек
"""

import sys
import codecs
import time

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB
from ai.deepseek_client import DeepSeekClient
import json

# Список неполных ячеек из аудита
MISSING_CELLS = [
    {'subject': 'combinatorics', 'subtopic': 'dirichlet_and_graphs', 'grade': 5, 'difficulty': 1, 'need': 2},
    {'subject': 'combinatorics', 'subtopic': 'other_algebra', 'grade': 5, 'difficulty': 1, 'need': 3},
    {'subject': 'geometry', 'subtopic': 'other_algebra', 'grade': 5, 'difficulty': 1, 'need': 4},
    {'subject': 'geometry', 'subtopic': 'other_algebra', 'grade': 5, 'difficulty': 5, 'need': 4},
    {'subject': 'geometry', 'subtopic': 'triangles', 'grade': 5, 'difficulty': 1, 'need': 3},
    {'subject': 'geometry', 'subtopic': 'triangles', 'grade': 5, 'difficulty': 5, 'need': 3},
    {'subject': 'knights_liars', 'subtopic': 'other_algebra', 'grade': 5, 'difficulty': 4, 'need': 1},
]

TOPIC_NAMES = {
    'combinatorics_dirichlet_and_graphs': 'Комбинаторика (Принцип Дирихле и графы)',
    'combinatorics_other_algebra': 'Комбинаторика',
    'geometry_other_algebra': 'Геометрия',
    'geometry_triangles': 'Геометрия (Треугольники)',
    'knights_liars_other_algebra': 'Рыцари и лжецы',
}

SYSTEM_PROMPT = """Ты - генератор математических задач для школьников.

Сгенерируй задачи строго по заданным параметрам.

КРИТИЧЕСКИ ВАЖНО - ФОРМАТИРОВАНИЕ LaTeX:
1. ВСЕ математические выражения оборачивай в \\\\( ... \\\\) (ДВОЙНОЕ экранирование!)
2. Блочные формулы: \\\\[ ... \\\\]
3. Дроби: \\\\frac{a}{b}
4. Корни: \\\\sqrt{x}
5. Степени: x^2, x^{n+1}
6. Индексы: a_1, x_{n+1}

Верни ТОЛЬКО JSON-массив задач, без пояснений."""

def generate_tasks_for_cell(client, cell_info):
    """Генерирует задачи для одной ячейки"""
    
    subject = cell_info['subject']
    subtopic = cell_info['subtopic']
    grade = cell_info['grade']
    difficulty = cell_info['difficulty']
    count = cell_info['need']
    
    topic_key = f"{subject}_{subtopic}"
    topic_name = TOPIC_NAMES.get(topic_key, topic_key)
    
    prompt = f"""Сгенерируй {count} задач по математике для школьников {grade} класса.

Тема: {topic_name}
Уровень сложности: {difficulty} из 7 (1=элементарная, 7=олимпиадная)

Верни JSON-массив. Каждая задача:
{{
  "text": "Текст задачи с LaTeX: \\\\( x^2 + y^2 = z^2 \\\\)",
  "answer": "Ответ",
  "solution": "Решение с LaTeX"
}}

ВСЮ математику оборачивай в \\\\( ... \\\\) с ДВОЙНЫМ экранированием!"""
    
    try:
        response = client.generate(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=3000
        )
        
        # Парсим JSON
        response_text = response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        tasks = json.loads(response_text)
        
        # Добавляем метаданные
        for task in tasks:
            task['subject'] = subject
            task['subtopic'] = subtopic
            task['grade'] = grade
            task['difficulty'] = difficulty
            task['id'] = max([p.get('id', 0) for p in PROBLEMS_DB]) + 1
            PROBLEMS_DB.append(task)
        
        return len(tasks)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return 0

def main():
    print("="*80)
    print("🔧 ДОГЕНЕРАЦИЯ НЕДОСТАЮЩИХ ЗАДАЧ")
    print("="*80)
    
    client = DeepSeekClient()
    
    total_needed = sum(cell['need'] for cell in MISSING_CELLS)
    total_generated = 0
    
    print(f"\n📊 Нужно догенерировать: {total_needed} задач")
    print(f"📋 Неполных ячеек: {len(MISSING_CELLS)}\n")
    
    for i, cell in enumerate(MISSING_CELLS, 1):
        topic_key = f"{cell['subject']}_{cell['subtopic']}"
        topic_name = TOPIC_NAMES.get(topic_key, topic_key)
        
        print(f"[{i}/{len(MISSING_CELLS)}] {topic_name}, уровень {cell['difficulty']}, класс {cell['grade']}")
        print(f"   Нужно: {cell['need']} задач")
        
        generated = generate_tasks_for_cell(client, cell)
        total_generated += generated
        
        print(f"   ✅ Сгенерировано: {generated} задач\n")
        
        time.sleep(1)
    
    print("="*80)
    print(f"✅ ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"📊 Всего сгенерировано: {total_generated}/{total_needed}")
    print("="*80)
    
    # Сохраняем
    print("\n💾 Сохранение обновлённой базы данных...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write(f'# Baza zadach FORMYLA - {len(PROBLEMS_DB)} zadach\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(PROBLEMS_DB))
    
    print("✅ Файл problems.py успешно обновлён!")
    print(f"📚 Новое количество задач: {len(PROBLEMS_DB)}")
    print("="*80)

if __name__ == '__main__':
    main()
