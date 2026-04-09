#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Order Linker - умная привязка по порядку
Если в варианте N задач с рисунком и N картинок - привязываем по порядку
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
from olympiads import OLYMPIADS_DB
from problem_images import IMAGE_MAP
import re

IMAGES_DIR = Path("static/images/problems")

OLYMPIAD_MAPPING = {
    'fu': 'formula_unity',
    'lomonosov': 'lomonosov',
    'pvg': 'pvg',
    'phystech': 'phystech',
    'vysshaya_proba': 'vysshaya_proba',
    'vsosh': 'vsosh',
    'turgor': 'turgor',
    'kurchatov': 'kurchatov',
    'euler': 'euler',
}


def parse_image_filename(filename):
    """Извлечь метаданные"""
    parts = filename.stem.split('_')
    olympiad = parts[0] if parts else None
    year = None
    grade = None
    
    for part in parts:
        if re.match(r'20\d{2}', part):
            year = int(part)
        elif part.startswith('g') and part[1:].isdigit():
            grade = int(part[1:])
    
    return olympiad, year, grade


def find_tasks_with_images(combo):
    """Найти задачи с упоминанием рисунка"""
    tasks = []
    for problem in combo.get('problems', []):
        prob_num = problem.get('num')
        text = problem.get('text', '').lower()
        
        if any(word in text for word in ['рисунок', 'чертеж', 'схема', 'график', 'диаграмм']):
            tasks.append(prob_num)
    
    return sorted(tasks)


def find_images_for_combo(olympiad_slug, year, grade):
    """Найти изображения для конкретного варианта"""
    # Получаем короткое имя олимпиады
    short_name = None
    for short, full in OLYMPIAD_MAPPING.items():
        if full == olympiad_slug:
            short_name = short
            break
    
    if not short_name:
        return []
    
    # Ищем изображения
    images = []
    for img_path in IMAGES_DIR.glob("*.png"):
        img_olympiad, img_year, img_grade = parse_image_filename(img_path)
        
        if (img_olympiad == short_name and
            img_year == year and
            (img_grade == grade or img_grade == 0)):  # g0 = все классы
            images.append(img_path.name)
    
    return sorted(images)


def main():
    """Главная функция"""
    print("="*70)
    print("ORDER LINKER - УМНАЯ ПРИВЯЗКА ПО ПОРЯДКУ")
    print("="*70)
    
    confident_matches = []
    
    # Проходим по всем combo
    for combo in OLYMPIADS_DB:
        combo_id = combo.get('id')
        olympiad = combo.get('olympiad')
        year = combo.get('year')
        grade = combo.get('grade')
        
        # Находим задачи с рисунками
        tasks_with_images = find_tasks_with_images(combo)
        
        if not tasks_with_images:
            continue
        
        # Находим доступные картинки
        available_images = find_images_for_combo(olympiad, year, grade)
        
        if not available_images:
            continue
        
        # ЛОГИКА ПОРЯДКА: Если количество совпадает - привязываем по порядку
        if len(tasks_with_images) == len(available_images):
            print(f"\n[MATCH] Combo {combo_id}: {olympiad} {year}, класс {grade}")
            print(f"  Задач с рисунком: {len(tasks_with_images)}")
            print(f"  Картинок: {len(available_images)}")
            
            for task_num, img_name in zip(tasks_with_images, available_images):
                # Проверяем, нет ли уже привязки
                if (combo_id, task_num) not in IMAGE_MAP:
                    confident_matches.append((combo_id, task_num, img_name))
                    print(f"    Задача {task_num} -> {img_name}")
    
    print("\n" + "="*70)
    print(f"НАЙДЕНО УВЕРЕННЫХ СОВПАДЕНИЙ: {len(confident_matches)}")
    print("="*70)
    
    if confident_matches:
        print("\nДобавляю привязки в problem_images.py...")
        
        with open('problem_images.py', 'a', encoding='utf-8') as f:
            f.write("\n# Order Linker - уверенные совпадения по порядку\n")
            for combo_id, prob_num, img_name in confident_matches:
                f.write(f"IMAGE_MAP[({combo_id}, {prob_num})] = \"{img_name}\"\n")
        
        print(f"[OK] Добавлено {len(confident_matches)} новых привязок")
        print("\nПерезапустите Flask-сервер для применения изменений")
    else:
        print("\n[INFO] Уверенных совпадений не найдено")


if __name__ == "__main__":
    main()
