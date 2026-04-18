#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ВТОРОЙ ПРОХОД: Агрессивное исправление LaTeX форматирования
Находит ВСЮ голую математику и оборачивает в \\( ... \\)
"""

import sys
import re
import codecs

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB

def needs_latex_wrapping(text):
    """
    Проверяет, нужно ли оборачивать текст в LaTeX
    """
    if not isinstance(text, str):
        return False
    
    # Уже обернуто
    if '\\(' in text or '\\[' in text:
        return False
    
    # Есть математические символы/переменные
    math_indicators = [
        r'[a-z]\s*[+\-*/=<>]',  # переменная с операцией
        r'[+\-*/=<>]\s*[a-z]',  # операция с переменной
        r'\^',  # степень
        r'[a-z]_',  # индекс
        r'√',  # корень
        r'≥|≤|≠|±|·|×',  # математические знаки
        r'\|[a-z]',  # модуль
        r'C\([a-z]',  # комбинаторика
        r'[a-z]{2,}',  # несколько переменных подряд (xy, ab)
    ]
    
    for pattern in math_indicators:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False

def wrap_aggressive(text):
    """
    Агрессивно оборачивает математику в \\( ... \\)
    """
    if not isinstance(text, str):
        text = str(text) if text is not None else ''
        return text, False
    
    if not text:
        return text, False
    
    # Уже обернуто - не трогаем
    if '\\(' in text:
        return text, False
    
    original = text
    modified = False
    
    # 1. Заменяем юникод-символы на LaTeX
    replacements = {
        '√': '\\\\sqrt',
        '≥': '\\\\ge',
        '≤': '\\\\le',
        '≠': '\\\\ne',
        '±': '\\\\pm',
        '×': '\\\\times',
        '÷': '\\\\div',
    }
    
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
            modified = True
    
    # 2. Находим математические выражения и оборачиваем
    # Паттерн: переменные с операциями, уравнения, неравенства
    patterns = [
        # Уравнения и неравенства (x + 5 = 12, 2a - 3 > 5)
        (r'([a-zA-Z0-9\s\+\-\*/\(\)·]+)\s*([=<>]|\\\\ge|\\\\le|\\\\ne)\s*([a-zA-Z0-9\s\+\-\*/\(\)·]+)', r'\\( \1 \2 \3 \\)'),
        
        # Выражения со степенями (x^2, a^{n+1})
        (r'([a-zA-Z])\^(\{[^}]+\}|[0-9]+)', r'\\( \1^\2 \\)'),
        
        # Выражения с индексами (a_1, x_n, a_{n+1})
        (r'([a-zA-Z])_(\{[^}]+\}|[0-9a-zA-Z]+)', r'\\( \1_\2 \\)'),
        
        # Дроби через слеш (a/b, (x+1)/2)
        (r'([a-zA-Z0-9\(\)]+)/([a-zA-Z0-9\(\)]+)', r'\\( \\frac{\1}{\2} \\)'),
        
        # Модуль (|x|, |a - b|)
        (r'\|([a-zA-Z0-9\s\+\-\*/]+)\|', r'\\( |\1| \\)'),
        
        # Произведения переменных (xy, ab, 2a, 3x)
        (r'(\d+)([a-zA-Z])', r'\\( \1\2 \\)'),
        (r'([a-zA-Z])([a-zA-Z])', r'\\( \1\2 \\)'),
        
        # Комбинаторика (C(n,k), P(n), A(n,k))
        (r'([CPA])\(([a-zA-Z0-9,\s]+)\)', r'\\( \1(\2) \\)'),
        
        # Корни (sqrt{x}, sqrt(x))
        (r'\\\\sqrt\{([^}]+)\}', r'\\( \\sqrt{\1} \\)'),
        (r'\\\\sqrt\(([^)]+)\)', r'\\( \\sqrt{\1} \\)'),
    ]
    
    for pattern, replacement in patterns:
        if re.search(pattern, text):
            text = re.sub(pattern, replacement, text)
            modified = True
    
    # 3. Очистка: убираем двойные обёртки \\( \\( ... \\) \\)
    text = re.sub(r'\\\\\(\s*\\\\\(', r'\\(', text)
    text = re.sub(r'\\\\\)\s*\\\\\)', r'\\)', text)
    
    # 4. Убираем обёртку вокруг обычных слов (если случайно обернули)
    # Например, \\( где \\) -> где
    text = re.sub(r'\\\\\(\s*([а-яА-ЯёЁ]+)\s*\\\\\)', r'\1', text)
    
    return text, modified

def fix_all_tasks_v2():
    """
    ВТОРОЙ ПРОХОД: Агрессивное исправление
    """
    print("="*80)
    print("🔧 ВТОРОЙ ПРОХОД: АГРЕССИВНОЕ ИСПРАВЛЕНИЕ LATEX")
    print("="*80)
    
    total_tasks = len(PROBLEMS_DB)
    fixed_count = 0
    examples = []
    
    print(f"\n📊 Всего задач в базе: {total_tasks}")
    print(f"🔄 Ищем задачи без LaTeX обёртки...\n")
    
    for i, task in enumerate(PROBLEMS_DB):
        task_id = task.get('id', i)
        text = task.get('text', '')
        answer = task.get('answer', '')
        solution = task.get('solution', '')
        
        # Исправляем текст задачи
        if needs_latex_wrapping(text):
            new_text, text_modified = wrap_aggressive(text)
            if text_modified:
                task['text'] = new_text
                fixed_count += 1
                
                # Сохраняем примеры
                if len(examples) < 5:
                    examples.append({
                        'id': task_id,
                        'before': text,
                        'after': new_text,
                        'field': 'text'
                    })
        
        # Исправляем ответ
        if needs_latex_wrapping(str(answer)):
            new_answer, answer_modified = wrap_aggressive(str(answer))
            if answer_modified:
                task['answer'] = new_answer
                fixed_count += 1
        
        # Исправляем решение (если есть)
        if solution and needs_latex_wrapping(solution):
            new_solution, solution_modified = wrap_aggressive(solution)
            if solution_modified:
                task['solution'] = new_solution
                fixed_count += 1
        
        # Прогресс
        if (i + 1) % 500 == 0:
            print(f"✓ Обработано {i + 1}/{total_tasks} задач...")
    
    print(f"\n{'='*80}")
    print(f"✅ ВТОРОЙ ПРОХОД ЗАВЕРШЁН!")
    print(f"{'='*80}")
    print(f"📊 Всего задач проверено: {total_tasks}")
    print(f"🔧 Дополнительно исправлено: {fixed_count}")
    print(f"{'='*80}\n")
    
    # Показываем примеры
    if examples:
        print("📝 ПРИМЕРЫ ИСПРАВЛЕНИЙ (До / После):\n")
        for idx, ex in enumerate(examples, 1):
            print(f"[ПРИМЕР {idx}] Задача ID: {ex['id']}")
            print(f"❌ ДО:  {ex['before'][:150]}")
            print(f"✅ ПОСЛЕ: {ex['after'][:150]}")
            print("-"*80 + "\n")
    else:
        print("✅ Все задачи уже имеют правильное LaTeX форматирование!")
        print("="*80)
        return
    
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
    fix_all_tasks_v2()
