#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Замена sqrt(...) на √(...) для читаемости"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

def replace_sqrt(text):
    """Заменяет sqrt(...) на √(...)"""
    if not text or not isinstance(text, str):
        return text
    
    # sqrt(ab) → √(ab)
    # sqrt(2) → √(2)
    text = text.replace('sqrt(', '√(')
    
    return text

def process_database():
    """Обработать всю базу"""
    print("=" * 60)
    print("REPLACING sqrt WITH root SYMBOL")
    print("=" * 60)
    print()
    
    changes_count = 0
    
    for problem in PROBLEMS_DB:
        # Обрабатываем text
        old_text = problem.get('text', '')
        new_text = replace_sqrt(old_text)
        if old_text != new_text:
            problem['text'] = new_text
            changes_count += 1
        
        # Обрабатываем answer
        old_answer = problem.get('answer', '')
        new_answer = replace_sqrt(old_answer)
        if old_answer != new_answer:
            problem['answer'] = new_answer
            changes_count += 1
        
        # Обрабатываем solution
        old_solution = problem.get('solution', '')
        new_solution = replace_sqrt(old_solution)
        if old_solution != new_solution:
            problem['solution'] = new_solution
            changes_count += 1
    
    print(f"Total problems: {len(PROBLEMS_DB)}")
    print(f"Changes made: {changes_count}")
    print()
    
    # Сохраняем
    print("Writing to problems.py...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# База задач с символом √\n\n')
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
    print(f"COMPLETED: {changes_count} sqrt replaced with √")
    print("=" * 60)

if __name__ == '__main__':
    try:
        process_database()
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
