#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual Linker - ручная привязка изображений под контролем пользователя
"""

import sys
sys.path.insert(0, '.')

from olympiads import OLYMPIADS_DB
from pathlib import Path

IMAGES_DIR = Path("static/images/problems")


def find_tasks_needing_images():
    """Найти задачи с упоминанием рисунка"""
    tasks = []
    
    for combo in OLYMPIADS_DB:
        combo_id = combo.get('id')
        olympiad = combo.get('olympiad_title', combo.get('olympiad'))
        year = combo.get('year')
        grade = combo.get('grade')
        round_title = combo.get('round_title', '')
        
        for problem in combo.get('problems', []):
            prob_num = problem.get('num')
            text = problem.get('text', '')
            
            if any(word in text.lower() for word in ['рисунок', 'чертеж', 'схема', 'график', 'диаграмм']):
                tasks.append({
                    'combo_id': combo_id,
                    'prob_num': prob_num,
                    'olympiad': olympiad,
                    'year': year,
                    'grade': grade,
                    'round': round_title,
                    'text': text
                })
    
    return tasks


def main():
    """Главная функция"""
    print("="*70)
    print("MANUAL LINKER - РУЧНАЯ ПРИВЯЗКА ИЗОБРАЖЕНИЙ")
    print("="*70)
    
    tasks = find_tasks_needing_images()
    print(f"\nНайдено задач с упоминанием рисунка: {len(tasks)}")
    print("\nНачинаем ручную привязку...\n")
    
    added = 0
    
    for i, task in enumerate(tasks, 1):
        print("="*70)
        print(f"ЗАДАЧА {i} из {len(tasks)}")
        print("="*70)
        print(f"Олимпиада: {task['olympiad']}")
        print(f"Год: {task['year']}, Класс: {task['grade']}")
        print(f"Этап: {task['round']}")
        print(f"Задача №{task['prob_num']}")
        print(f"\nТЕКСТ ЗАДАЧИ:")
        print(task['text'])
        print("\n" + "-"*70)
        
        filename = f"task_{task['combo_id']}_{task['prob_num']}.png"
        print(f"\nПОЛОЖИТЕ правильную картинку в папку:")
        print(f"  static/images/problems/{filename}")
        print(f"\nПосле этого нажмите Enter для продолжения...")
        print(f"Или введите 'skip' для пропуска этой задачи")
        print(f"Или введите 'quit' для выхода")
        
        choice = input("\n> ").strip().lower()
        
        if choice == 'quit':
            print("\nВыход...")
            break
        elif choice == 'skip':
            print("Пропущено")
            continue
        
        # Проверяем наличие файла
        img_path = IMAGES_DIR / filename
        if img_path.exists():
            # Добавляем в problem_images.py
            with open('problem_images.py', 'a', encoding='utf-8') as f:
                f.write(f"IMAGE_MAP[({task['combo_id']}, {task['prob_num']})] = \"{filename}\"\n")
            
            print(f"[OK] Привязка добавлена!")
            added += 1
        else:
            print(f"[!] Файл {filename} не найден. Пропускаю...")
    
    print("\n" + "="*70)
    print(f"ИТОГО ДОБАВЛЕНО ПРИВЯЗОК: {added}")
    print("="*70)
    
    if added > 0:
        print("\nПерезапустите Flask-сервер для применения изменений")


if __name__ == "__main__":
    main()
