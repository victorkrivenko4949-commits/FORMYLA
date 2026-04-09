#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическая привязка изображений к задачам
Сканирует static/images/problems/, находит соответствующие combo_id и обновляет problem_images.py
"""

import re
from pathlib import Path

# Импортируем базу олимпиад
import sys
sys.path.insert(0, '.')
from olympiads import OLYMPIADS_DB

# Настройки
IMAGES_DIR = Path("static/images/problems")

# Маппинг сокращений олимпиад
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
    """Извлечь метаданные из имени файла изображения"""
    # Паттерн: {olympiad}_{year}_g{grade}_fig{num}.png
    # Или: {olympiad}_{year}_g{grade}_p{page}_i{img}.png
    
    parts = filename.stem.split('_')
    
    olympiad = parts[0] if parts else None
    year = None
    grade = None
    fig_num = None
    
    # Ищем год
    for part in parts:
        if re.match(r'20\d{2}', part):
            year = int(part)
            break
    
    # Ищем класс
    for part in parts:
        if part.startswith('g') and part[1:].isdigit():
            grade = int(part[1:])
            break
    
    # Ищем номер рисунка
    for part in parts:
        if part.startswith('fig') and part[3:].isdigit():
            fig_num = int(part[3:])
            break
        elif part.startswith('i') and part[1:].isdigit():
            fig_num = int(part[1:])
            break
    
    return olympiad, year, grade, fig_num


def find_combo_id(olympiad_slug, year, grade):
    """Найти combo_id в OLYMPIADS_DB"""
    for combo in OLYMPIADS_DB:
        if (combo.get('olympiad') == olympiad_slug and
            combo.get('year') == year and
            combo.get('grade') == grade):
            return combo.get('id')
    return None


def main():
    """Главная функция"""
    print("="*70)
    print("АВТОМАТИЧЕСКАЯ ПРИВЯЗКА ИЗОБРАЖЕНИЙ К ЗАДАЧАМ")
    print("="*70)
    
    # Сканируем изображения
    image_files = list(IMAGES_DIR.glob("*.png")) + list(IMAGES_DIR.glob("*.jpg"))
    print(f"\nНайдено изображений: {len(image_files)}")
    
    # Создаем новый IMAGE_MAP
    new_mappings = {}
    skipped = 0
    
    for img_path in image_files:
        olympiad_short, year, grade, fig_num = parse_image_filename(img_path)
        
        if not all([olympiad_short, year, grade]):
            skipped += 1
            continue
        
        # Получаем полное имя олимпиады
        olympiad_slug = OLYMPIAD_MAPPING.get(olympiad_short)
        if not olympiad_slug:
            skipped += 1
            continue
        
        # Находим combo_id
        combo_id = find_combo_id(olympiad_slug, year, grade)
        if not combo_id:
            print(f"  [!] Не найден combo для: {olympiad_slug} {year} класс {grade}")
            skipped += 1
            continue
        
        # Определяем номер задачи (по умолчанию 1, если не указан)
        problem_num = fig_num if fig_num else 1
        
        # Добавляем в маппинг
        key = (combo_id, problem_num)
        new_mappings[key] = img_path.name
        print(f"  [OK] ({combo_id}, {problem_num}) -> {img_path.name}")
    
    print(f"\nСоздано привязок: {len(new_mappings)}")
    print(f"Пропущено файлов: {skipped}")
    
    # Генерируем новый problem_images.py
    print("\nГенерирую problem_images.py...")
    
    content = '# -*- coding: utf-8 -*-\n'
    content += '# Автоматически сгенерированный маппинг изображений\n\n'
    content += 'IMAGE_MAP = {\n'
    
    for (combo_id, prob_num), filename in sorted(new_mappings.items()):
        content += f'    ({combo_id}, {prob_num}): "{filename}",\n'
    
    content += '}\n'
    
    # Сохраняем
    with open('problem_images.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"[OK] Сохранено в problem_images.py")
    print(f"[OK] Всего привязок: {len(new_mappings)}")
    
    print("\n" + "="*70)
    print("ГОТОВО! Перезапустите Flask-сервер для применения изменений")
    print("="*70)


if __name__ == "__main__":
    main()
