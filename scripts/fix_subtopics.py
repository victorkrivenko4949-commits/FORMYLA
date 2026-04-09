#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Скрипт для исправления подтем (subtopics) в базе задач"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from problems import PROBLEMS_DB

# Маппинг subject -> список подтем
SUBTOPIC_MAPPING = {
    'algebra': ['equations', 'inequalities', 'text_problems'],
    'geometry': ['basics', 'triangles', 'circles'],
    'number_theory': ['divisibility', 'primes_and_equations'],
    'combinatorics': ['counting', 'dirichlet_and_graphs', 'games_and_invariants'],
    'movement': ['linear', 'circular'],
    'knights_liars': ['basic_logic', 'complex_logic']
}

def fix_subtopics():
    """Перераспределить подтемы для всех задач"""
    
    print("=" * 60)
    print("FIXING SUBTOPICS IN PROBLEMS DATABASE")
    print("=" * 60)
    print()
    
    # Группируем задачи по subject
    by_subject = {}
    for problem in PROBLEMS_DB:
        subject = problem.get('subject', '')
        if subject not in by_subject:
            by_subject[subject] = []
        by_subject[subject].append(problem)
    
    print(f"Found {len(PROBLEMS_DB)} total problems")
    print(f"Subjects: {list(by_subject.keys())}")
    print()
    
    # Обновляем подтемы
    changes_count = 0
    
    for subject, problems in by_subject.items():
        if subject not in SUBTOPIC_MAPPING:
            print(f"[SKIP] Subject '{subject}' not in mapping")
            continue
        
        subtopics = SUBTOPIC_MAPPING[subject]
        num_subtopics = len(subtopics)
        problems_per_subtopic = len(problems) // num_subtopics
        
        print(f"[{subject.upper()}] {len(problems)} problems -> {num_subtopics} subtopics")
        print(f"  Distribution: ~{problems_per_subtopic} problems per subtopic")
        
        # Распределяем задачи по подтемам
        for i, problem in enumerate(problems):
            old_subtopic = problem.get('subtopic', '')
            
            # Определяем новую подтему
            subtopic_index = i // problems_per_subtopic
            if subtopic_index >= num_subtopics:
                subtopic_index = num_subtopics - 1
            
            new_subtopic = subtopics[subtopic_index]
            
            if old_subtopic != new_subtopic:
                problem['subtopic'] = new_subtopic
                changes_count += 1
        
        # Статистика по подтемам
        subtopic_counts = {}
        for problem in problems:
            st = problem.get('subtopic', '')
            subtopic_counts[st] = subtopic_counts.get(st, 0) + 1
        
        for st, count in subtopic_counts.items():
            print(f"    - {st}: {count} problems")
        print()
    
    print(f"Total changes: {changes_count}")
    print()
    
    # Записываем обновленную базу в problems.py
    print("Writing updated database to problems.py...")
    
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# База задач — 7 уровней сложности\n\n')
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
    print(f"COMPLETED: {changes_count} subtopics fixed")
    print("=" * 60)
    
    return changes_count

if __name__ == '__main__':
    try:
        changes = fix_subtopics()
        print(f"\n[OK] Script completed successfully. {changes} changes made.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Script failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
