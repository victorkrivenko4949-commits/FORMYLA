#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Умная привязка изображений к задачам
Анализирует тексты задач и предлагает привязки
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
from olympiads import OLYMPIADS_DB
from problem_images import IMAGE_MAP
import re

IMAGES_DIR = Path("static/images/problems")

# Маппинг сокращений
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
    """Извлечь метаданные из имени"""
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


def find_tasks_with_images_mention():
    """Найти задачи, где упоминается рисунок/чертеж"""
    tasks_need_images = []
    
    for combo in OLYMPIADS_DB:
        combo_id = combo.get('id')
        olympiad = combo.get('olympiad')
        year = combo.get('year')
        grade = combo.get('grade')
        
        for problem in combo.get('problems', []):
            prob_num = problem.get('num')
            text = problem.get('text', '').lower()
            
            # Проверяем упоминание рисунка
            if any(word in text for word in ['рисунок', 'чертеж', 'схема', 'график', 'диаграмм']):
                # Проверяем, есть ли уже привязка
                if (combo_id, prob_num) not in IMAGE_MAP:
                    tasks_need_images.append({
                        'combo_id': combo_id,
                        'prob_num': prob_num,
                        'olympiad': olympiad,
                        'year': year,
                        'grade': grade,
                        'text_preview': text[:100]
                    })
    
    return tasks_need_images


def find_unlinked_images():
    """Найти изображения без привязок"""
    all_images = list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    linked_images = set(IMAGE_MAP.values())
    
    unlinked = []
    for img in all_images:
        if img.name not in linked_images:
            olympiad, year, grade = parse_image_filename(img)
            unlinked.append({
                'filename': img.name,
                'olympiad': olympiad,
                'year': year,
                'grade': grade
            })
    
    return unlinked


def suggest_links():
    """Предложить умные привязки"""
    print("="*70)
    print("УМНАЯ ПРИВЯЗКА ИЗОБРАЖЕНИЙ")
    print("="*70)
    
    # Находим свободные картинки
    unlinked = find_unlinked_images()
    print(f"\nСвободных картинок: {len(unlinked)}")
    
    # Находим задачи без картинок
    tasks_need = find_tasks_with_images_mention()
    print(f"Задач без картинок (с упоминанием рисунка): {len(tasks_need)}")
    
    # Группируем по олимпиаде/году/классу
    suggestions = []
    
    for img in unlinked:
        if not img['olympiad'] or not img['year']:
            continue
        
        olympiad_slug = OLYMPIAD_MAPPING.get(img['olympiad'])
        if not olympiad_slug:
            continue
        
        # Ищем подходящие задачи
        for task in tasks_need:
            if (task['olympiad'] == olympiad_slug and
                task['year'] == img['year'] and
                (img['grade'] == 0 or img['grade'] == task['grade'] or img['grade'] is None)):
                
                suggestions.append({
                    'image': img['filename'],
                    'combo_id': task['combo_id'],
                    'prob_num': task['prob_num'],
                    'olympiad': task['olympiad'],
                    'year': task['year'],
                    'grade': task['grade'],
                    'text': task['text_preview']
                })
    
    print(f"\nПредложено привязок: {len(suggestions)}")
    
    # Показываем первые 20
    print("\nПримеры предложенных привязок:\n")
    for i, sug in enumerate(suggestions[:20], 1):
        print(f"[{i}] {sug['image']}")
        print(f"    -> Combo {sug['combo_id']}, Задача {sug['prob_num']}")
        print(f"    {sug['olympiad']} {sug['year']}, класс {sug['grade']}")
        print(f"    Текст: {sug['text']}...")
        print()
    
    if len(suggestions) > 20:
        print(f"... и еще {len(suggestions) - 20} предложений")
    
    return suggestions


def save_suggestions_to_file(suggestions):
    """Сохранить предложения в файл"""
    with open('SMART_SUGGESTIONS.txt', 'w', encoding='utf-8') as f:
        f.write("# УМНЫЕ ПРЕДЛОЖЕНИЯ ПО ПРИВЯЗКЕ ИЗОБРАЖЕНИЙ\n")
        f.write("# Сгенерировано автоматически скриптом smart_linker.py\n")
        f.write("# Скопируйте нужные строки в problem_images.py\n\n")
        
        # Группируем по combo_id
        by_combo = {}
        for sug in suggestions:
            combo_id = sug['combo_id']
            if combo_id not in by_combo:
                by_combo[combo_id] = []
            by_combo[combo_id].append(sug)
        
        for combo_id, sugs in sorted(by_combo.items()):
            first = sugs[0]
            f.write(f"\n# Combo {combo_id}: {first['olympiad']} {first['year']}, класс {first['grade']}\n")
            
            for sug in sugs:
                f.write(f"# Задача {sug['prob_num']}: {sug['text'][:60]}...\n")
                f.write(f"IMAGE_MAP[({sug['combo_id']}, {sug['prob_num']})] = \"{sug['image']}\"\n")
            
            f.write("\n")
    
    print(f"\n[OK] Предложения сохранены в SMART_SUGGESTIONS.txt")


def main():
    """Главная функция"""
    suggestions = suggest_links()
    
    # Сохраняем в файл
    save_suggestions_to_file(suggestions)
    
    print("\n" + "="*70)
    print("ИТОГО")
    print("="*70)
    print(f"Свободных картинок: {len(find_unlinked_images())}")
    print(f"Задач без картинок: {len(find_tasks_with_images_mention())}")
    print(f"Предложено привязок: {len(suggestions)}")
    print("="*70)
    
    print("\nПредложения сохранены в SMART_SUGGESTIONS.txt")
    print("Скопируйте нужные строки в problem_images.py")


if __name__ == "__main__":
    main()
