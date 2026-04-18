#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для исправления LaTeX форматирования в разделе "Темы" (2205 задач)
Оборачивает математические выражения в \\( ... \\) для корректного рендеринга
"""

import sys
import re
import codecs

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB

def wrap_math_expression(text):
    """
    Оборачивает математические выражения в \\( ... \\)
    """
    # Конвертируем в строку, если это число
    if not isinstance(text, str):
        text = str(text) if text is not None else ''
    
    if not text or '\\(' in text:  # Уже обернуто
        return text, False
    
    original = text
    modified = False
    
    # 1. Заменяем одинарные слеши на двойные
    if text.count('\\') > 0 and '\\\\' not in text:
        text = text.replace('\\(', '\\\\(').replace('\\)', '\\\\)')
        text = text.replace('\\[', '\\\\[').replace('\\]', '\\\\]')
        modified = True
    
    # 2. Оборачиваем выражения с делением через слеш (x/6, (a+b)/2)
    # Паттерн: переменная или выражение в скобках, затем /, затем число или выражение
    pattern_division = r'([a-zA-Zа-яА-Я0-9()]+)/([a-zA-Zа-яА-Я0-9()]+)'
    if re.search(pattern_division, text) and '\\(' not in text:
        # Проверяем, что это математика, а не просто текст
        if re.search(r'[xy]/', text) or re.search(r'\d+/', text):
            text = re.sub(pattern_division, r'\\( \\frac{\1}{\2} \\)', text)
            modified = True
    
    # 3. Оборачиваем выражения со степенями (x^2, a^{10})
    pattern_power = r'([a-zA-Zа-яА-Я])(\^)(\{?[0-9a-zA-Z+\-]+\}?)'
    if re.search(pattern_power, text) and '\\(' not in text:
        # Оборачиваем всё выражение со степенью
        text = re.sub(r'([a-zA-Zа-яА-Я]\^[0-9]+)', r'\\( \1 \\)', text)
        text = re.sub(r'([a-zA-Zа-яА-Я]\^\{[^}]+\})', r'\\( \1 \\)', text)
        modified = True
    
    # 4. Оборачиваем уравнения (содержат = и переменные)
    pattern_equation = r'([a-zA-Zа-яА-Я0-9\s\+\-\*/\(\)]+)\s*=\s*([a-zA-Zа-яА-Я0-9\s\+\-\*/\(\)]+)'
    if re.search(pattern_equation, text) and '\\(' not in text:
        # Проверяем, что это математическое уравнение
        if re.search(r'[xy]\s*[+\-*/]?\s*\d+\s*=', text):
            # Оборачиваем уравнение
            text = re.sub(pattern_equation, r'\\( \1 = \2 \\)', text)
            modified = True
    
    # 5. Заменяем >= на \ge, <= на \le, != на \ne
    if '>=' in text:
        text = text.replace('>=', '\\\\ge')
        modified = True
    if '<=' in text:
        text = text.replace('<=', '\\\\le')
        modified = True
    if '!=' in text:
        text = text.replace('!=', '\\\\ne')
        modified = True
    
    # 6. Заменяем sqrt(...) на \\sqrt{...}
    pattern_sqrt = r'sqrt\(([^)]+)\)'
    if re.search(pattern_sqrt, text):
        text = re.sub(pattern_sqrt, r'\\\\sqrt{\1}', text)
        modified = True
    
    # 7. Убираем маркдаун ```json
    if '```json' in text or '```' in text:
        text = text.replace('```json', '').replace('```', '')
        modified = True
    
    return text, modified

def fix_all_tasks():
    """
    Проходит по всем задачам и исправляет LaTeX форматирование
    """
    print("="*80)
    print("🔧 ИСПРАВЛЕНИЕ LATEX В РАЗДЕЛЕ 'ТЕМЫ'")
    print("="*80)
    
    total_tasks = len(PROBLEMS_DB)
    fixed_count = 0
    examples = []
    
    print(f"\n📊 Всего задач в базе: {total_tasks}")
    print(f"🔄 Начинаем обработку...\n")
    
    for i, task in enumerate(PROBLEMS_DB):
        task_id = task.get('id', i)
        text = task.get('text', '')
        answer = task.get('answer', '')
        solution = task.get('solution', '')
        
        # Исправляем текст задачи
        new_text, text_modified = wrap_math_expression(text)
        if text_modified:
            task['text'] = new_text
            fixed_count += 1
            
            # Сохраняем примеры
            if len(examples) < 3:
                examples.append({
                    'id': task_id,
                    'before': text,
                    'after': new_text,
                    'field': 'text'
                })
        
        # Исправляем ответ
        new_answer, answer_modified = wrap_math_expression(answer)
        if answer_modified:
            task['answer'] = new_answer
            fixed_count += 1
        
        # Исправляем решение (если есть)
        if solution:
            new_solution, solution_modified = wrap_math_expression(solution)
            if solution_modified:
                task['solution'] = new_solution
                fixed_count += 1
        
        # Прогресс
        if (i + 1) % 500 == 0:
            print(f"✓ Обработано {i + 1}/{total_tasks} задач...")
    
    print(f"\n{'='*80}")
    print(f"✅ ОБРАБОТКА ЗАВЕРШЕНА!")
    print(f"{'='*80}")
    print(f"📊 Всего задач проверено: {total_tasks}")
    print(f"🔧 Внесено исправлений: {fixed_count}")
    print(f"{'='*80}\n")
    
    # Показываем примеры
    if examples:
        print("📝 ПРИМЕРЫ ИСПРАВЛЕНИЙ (До / После):\n")
        for idx, ex in enumerate(examples, 1):
            print(f"[ПРИМЕР {idx}] Задача ID: {ex['id']}")
            print(f"❌ ДО:  {ex['before']}")
            print(f"✅ ПОСЛЕ: {ex['after']}")
            print("-"*80 + "\n")
    
    # Сохраняем обратно в файл
    print("💾 Сохранение исправленной базы данных...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza zadach FORMYLA - 2205 zadach\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(PROBLEMS_DB))
    
    print("✅ Файл problems.py успешно обновлён!")
    print("="*80)

if __name__ == '__main__':
    fix_all_tasks()
