#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Сокращение длинных ответов в базе задач"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

MAX_ANSWER_LENGTH = 40

def fix_long_answer(task):
    """Сократить длинный ответ"""
    answer = task.get('answer', '')
    text = task.get('text', '')
    
    if len(answer) <= MAX_ANSWER_LENGTH:
        return answer  # Ответ нормальный
    
    # Проверяем, это задача на доказательство?
    proof_keywords = ['докажи', 'докажите', 'доказать', 'покажите', 'покажи', 'обоснуй']
    is_proof = any(keyword in text.lower() for keyword in proof_keywords)
    
    if is_proof:
        return "Доказано"
    
    # Ищем "Ответ:" в тексте ответа
    if 'ответ:' in answer.lower():
        match = re.search(r'ответ:\s*([^.]+)', answer, re.IGNORECASE)
        if match:
            short_answer = match.group(1).strip()
            if len(short_answer) <= MAX_ANSWER_LENGTH:
                return short_answer
    
    # Если ничего не помогло
    return "Смотри решение"

def process_database():
    """Обработать всю базу"""
    print("=" * 60)
    print("FIXING LONG ANSWERS")
    print("=" * 60)
    print()
    
    long_answers = []
    changes_count = 0
    
    for i, task in enumerate(PROBLEMS_DB):
        answer = task.get('answer', '')
        
        # Конвертируем в строку если это число
        if not isinstance(answer, str):
            answer = str(answer)
            task['answer'] = answer
        
        if len(answer) > MAX_ANSWER_LENGTH:
            old_answer = answer
            new_answer = fix_long_answer(task)
            
            if old_answer != new_answer:
                task['answer'] = new_answer
                changes_count += 1
                long_answers.append({
                    'id': task.get('id', i),
                    'old_len': len(old_answer),
                    'new': new_answer
                })
    
    print(f"Total problems: {len(PROBLEMS_DB)}")
    print(f"Long answers found: {len(long_answers)}")
    print(f"Changes made: {changes_count}")
    print()
    
    if long_answers:
        print("Examples of changes:")
        for ex in long_answers[:5]:
            try:
                print(f"  ID {ex['id']}: {ex['old_len']} chars -> [shortened]")
            except:
                pass
        print()
    
    # Сохраняем
    print("Writing to problems.py...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# База задач с короткими ответами\n\n')
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
    print(f"COMPLETED: {changes_count} long answers fixed")
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
