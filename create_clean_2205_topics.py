#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Создание чистой базы из 2205 задач (15 тем × 7 уровней × 21 задача)
"""

import sys
import codecs
import random

# Фикс кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from problems import PROBLEMS_DB

# 15 основных тем для раздела "Темы"
TARGET_TOPICS = [
    ('algebra', 'equations'),
    ('algebra', 'inequalities'),
    ('algebra', 'systems'),
    ('geometry', 'triangles'),
    ('geometry', 'circles'),
    ('geometry', 'areas'),
    ('number_theory', 'divisibility'),
    ('number_theory', 'primes'),
    ('number_theory', 'gcd_lcm'),
    ('combinatorics', 'counting'),
    ('combinatorics', 'dirichlet_and_graphs'),
    ('movement', 'movement_all'),
    ('knights_liars', 'logic_all'),
    ('other', 'word_problems'),
    ('other', 'other_algebra'),
]

def create_clean_database():
    """
    Создаёт чистую базу из 2205 задач
    """
    print("="*80)
    print("🔧 СОЗДАНИЕ ЧИСТОЙ БАЗЫ: 2205 ЗАДАЧ")
    print("="*80)
    
    print(f"\n📊 Текущая база: {len(PROBLEMS_DB)} задач")
    print(f"🎯 Целевая структура: 15 тем × 7 уровней × 21 задача = 2,205 задач\n")
    
    new_db = []
    next_id = 5001
    
    for subject, subtopic in TARGET_TOPICS:
        topic_name = f"{subject}_{subtopic}"
        print(f"📚 Обрабатываем тему: {topic_name}")
        
        for level in range(1, 8):
            # Находим задачи для этой ячейки
            matching = [p for p in PROBLEMS_DB
                       if p.get('subject') == subject
                       and p.get('subtopic') == subtopic
                       and p.get('difficulty') == level]
            
            # Берём 21 задачу (или сколько есть)
            if len(matching) >= 21:
                selected = random.sample(matching, 21)
            else:
                selected = matching
                print(f"   ⚠️  Уровень {level}: только {len(matching)} задач (нужно 21)")
            
            # Переназначаем ID и добавляем
            for task in selected:
                task_copy = task.copy()
                task_copy['id'] = next_id
                next_id += 1
                new_db.append(task_copy)
        
        print(f"   ✅ Добавлено задач: {len([t for t in new_db if t['subject']==subject and t['subtopic']==subtopic])}\n")
    
    print("="*80)
    print(f"✅ НОВАЯ БАЗА СОЗДАНА!")
    print(f"📊 Всего задач: {len(new_db)}")
    print("="*80)
    
    # Сохраняем
    print("\n💾 Сохранение в problems.py...")
    with open('problems.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write(f'# Baza zadach FORMYLA - {len(new_db)} zadach\n\n')
        f.write('PROBLEMS_DB = ')
        f.write(repr(new_db))
    
    print("✅ Файл problems.py успешно обновлён!")
    print(f"📚 Новое количество задач: {len(new_db)}")
    print("="*80)

if __name__ == '__main__':
    create_clean_database()
