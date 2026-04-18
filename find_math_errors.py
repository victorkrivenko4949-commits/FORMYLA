#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Поиск потенциальных ошибок в математической нотации
"""
import sqlite3
import re
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'instance/formyla.db'

def find_potential_errors():
    """Найти задачи с потенциальными ошибками в математике"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Получаем все записи
    cursor.execute('SELECT id, class_level, topic, task_text, solution FROM adaptive_tasks')
    records = cursor.fetchall()
    
    print(f"📊 Всего записей в adaptive_tasks: {len(records)}\n")
    
    # Паттерны для поиска ошибок
    patterns = {
        'скобка_число': r'\)[2-9]',  # )2, )3, etc
        'переменная_число': r'[a-z][0-9]',  # a1, x2, etc (может быть индекс или степень)
        'единицы_измерения': r'(см|м|км|дм|мм)[2-3](?!\^)',  # см2, м3 без степени
        'sqrt_без_скобок': r'\\sqrt\s*[a-zA-Z0-9](?![{])',  # \sqrt x вместо \sqrt{x}
    }
    
    found_tasks = []
    
    for record_id, class_level, topic, task_text, solution in records:
        combined_text = (task_text or '') + ' ' + (solution or '')
        if not combined_text.strip():
            continue
            
        matches = {}
        for pattern_name, pattern in patterns.items():
            found = re.findall(pattern, combined_text)
            if found:
                matches[pattern_name] = found
        
        if matches:
            found_tasks.append({
                'id': record_id,
                'class_level': class_level,
                'topic': topic,
                'task_text': task_text,
                'solution': solution,
                'matches': matches
            })
    
    print(f"✅ Найдено задач с потенциальными ошибками: {len(found_tasks)}\n")
    
    # Показываем первые 10 примеров
    for i, task in enumerate(found_tasks[:10], 1):
        print(f"{'='*80}")
        print(f"Задача #{i} (ID: {task['id']})")
        print(f"Класс: {task['class_level']}, Тема: {task['topic'][:50]}")
        print(f"\nНайденные паттерны:")
        for pattern_name, matches in task['matches'].items():
            print(f"  - {pattern_name}: {matches[:5]}")  # Первые 5 совпадений
        
        # Показываем фрагмент с ошибкой
        print(f"\nФрагмент задачи (первые 300 символов):")
        print((task['task_text'] or '')[:300])
        print()
    
    conn.close()
    return found_tasks

if __name__ == '__main__':
    found_tasks = find_potential_errors()
    print(f"\n{'='*80}")
    print(f"📊 ИТОГО: Найдено {len(found_tasks)} задач с потенциальными ошибками")
    print(f"{'='*80}")
