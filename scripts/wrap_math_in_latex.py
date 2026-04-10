#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для обертывания математики в LaTeX разметку ($...$)"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

def wrap_math_in_latex(text):
    """Оборачивает математические выражения в $ ... $"""
    if not text or not isinstance(text, str):
        return text
    
    # Если уже есть LaTeX разметка, не трогаем
    if '$' in text or '\\(' in text:
        return text
    
    # 1. Заменяем sqrt(...) на \sqrt{...}
    text = re.sub(r'sqrt\(([^)]+)\)', r'\\sqrt{\1}', text)
    
    # 2. Оборачиваем математические выражения в $...$
    # Паттерн: переменные с операциями (x^2 + 5, a = b, etc)
    # Ищем: буква/цифра, затем операторы +, -, *, /, =, <, >, ^
    math_pattern = r'([a-zA-Z]\d*(?:\^\d+)?(?:\s*[\+\-\*\/=<>≤≥≠]\s*[a-zA-Z0-9\^\(\)]+)+)'
    text = re.sub(math_pattern, r'$\1$', text)
    
    # 3. Изолированные степени x^2, a^n
    text = re.sub(r'(?<![a-zA-Z$])([a-zA-Z]\^\d+)(?![a-zA-Z$])', r'$\1$', text)
    
    # 4. Изолированные переменные в математическом контексте
    # x = 5, y > 0
    text = re.sub(r'(?<![a-zA-Z])([a-zA-Z])\s*([=<>≤≥≠])\s*([0-9\-]+)', r'$\1 \2 \3$', text)
    
    # 5. Специальные символы ±
    text = re.sub(r'(±[a-zA-Z0-9\*\\]+)', r'$\1$', text)
    
    # Убираем двойные доллары $$
    text = text.replace('$$', '$')
    
    return text

def process_database():
    """Обработать всю базу данных"""
    print("=" * 60)
    print("WRAPPING MATH IN LATEX")
    print("=" * 60)
    print()
    
    print(f"Total problems: {len(PROBLEMS_DB)}")
    
    changes_count = 0
    
    for problem in PROBLEMS_DB:
        # Обрабатываем text
        old_text = problem.get('text', '')
        new_text = wrap_math_in_latex(old_text)
        if old_text != new_text:
            problem['text'] = new_text
            changes_count += 1
        
        # Обрабатываем answer
        old_answer = problem.get('answer', '')
        new_answer = wrap_math_in_latex(old_answer)
        if old_answer != new_answer:
            problem['answer'] = new_answer
            changes_count += 1
        
        # Обрабатываем solution
        old_solution = problem.get('solution', '')
        new_solution = wrap_math_in_latex(old_solution)
        if old_solution != new_solution:
            problem['solution'] = new_solution
            changes_count += 1
    
    print(f"Changes made: {changes_count}")
    print()
    
    # Сохраняем
    print("Writing to problems.py...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# База задач с LaTeX разметкой\n\n')
        f.write('PROBLEMS_DB = [\n')
        
        for i, problem in enumerate(PROBLEMS_DB):
            f.write(str(problem))
            if i < len(PROBLEMS_DB) - 1:
                f.write(',\n')
            else:
                f.write('\n')
        
        f.write(']\n')
    
    print("[SUCCESS] problems.py updated!")
    print()
    print("=" * 60)
    print(f"COMPLETED: {changes_count} fields wrapped in LaTeX")
    print("=" * 60)

if __name__ == '__main__':
    try:
        process_database()
        print("\n[OK] Script completed successfully")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Script failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
