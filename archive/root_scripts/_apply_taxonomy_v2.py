#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Apply taxonomy v2 to curated_bank_L1_L5_fixed.json:
  1. Rename 13 subtopics
  2. Rename 2 themes
  3. Remove tasks with 5 garbage subtopics
Output: curated_bank_L1_L5_taxonomy_v2.json
"""
import json
import sys
from collections import Counter

INPUT  = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'
OUTPUT = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_formyla_taxonomy.json'

# --- Subtopics to rename (old -> new) ---
SUBTOPIC_RENAMES = {
    'Уравнения с модулем':
        'Решение уравнений с модулем (раскрытие по случаям)',
    'Площадь круга и его частей':
        'Площадь многоугольников (через разбиение и дополнение)',
    'Тригонометрические уравнения с отбором корней':
        'Универсальная тригонометрическая подстановка и метод вспомогательного угла',
    'Рациональные уравнения':
        'Целые рациональные уравнения (линейные и квадратные)',
    'Прикладные задачи':
        'Задачи на составление уравнений по условию',
    'Алгоритмы и вычисления':
        'Системы счисления и запись чисел',
    'Метод замены в иррациональных уравнениях':
        'Иррациональные уравнения: метод возведения в степень',
    'Иррациональные уравнения с одним корнем':
        'Уравнения с одним радикалом',
    'Иррациональные уравнения с несколькими корнями':
        'Уравнения с двумя и более радикалами',
    'Скрещивающиеся прямые':
        'Параллельность прямых и плоскостей',
    'Неравенства Чебышева и Маркова':
        'Неравенство Чебышева для числовых наборов',
    'Уравнения вида R(sin x, cos x) = 0 и подстановка Вейерштрасса':
        'Универсальная тригонометрическая подстановка и метод вспомогательного угла',
    'Булевы функции и их минимизация':
        'Высказывания и предикаты',
}

# --- Themes to rename (old -> new) ---
THEME_RENAMES = {
    'Комбинаторика и вероятность':
        'Комбинаторика: счётные техники',
    'Вероятность и комбинаторика':
        'Теория вероятностей: классическая модель',
}

# --- Garbage subtopics to remove ---
GARBAGE_SUBTOPICS = {
    'Formula_Unity',
    'Formula of Unity',
    'Kurchatov',
    'Ломоносов',
    'Lomonosov',
    'Физтех',
    'Эйлера',
}

def main():
    print(f"Loading {INPUT} ...")
    with open(INPUT, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Loaded {len(data)} tasks.")

    stats = {
        'total_before': len(data),
        'subtopic_renames': Counter(),
        'theme_renames': Counter(),
        'garbage_removed': 0,
        'garbage_by_value': Counter(),
        'already_new_subtopic': 0,
        'already_new_theme': 0,
    }

    kept = []
    for task in data:
        old_sub = task.get('subtopic', '').strip()
        old_theme = task.get('theme', '').strip()

        # 1. Check if garbage -> skip
        if any(g in old_sub for g in GARBAGE_SUBTOPICS):
            stats['garbage_removed'] += 1
            # Track which garbage keyword matched
            for g in GARBAGE_SUBTOPICS:
                if g in old_sub:
                    stats['garbage_by_value'][f"{g} -> '{old_sub}'"] += 1
                    break
            continue

        # 2. Rename subtopic
        if old_sub in SUBTOPIC_RENAMES:
            new_sub = SUBTOPIC_RENAMES[old_sub]
            task['subtopic'] = new_sub
            stats['subtopic_renames'][f"{old_sub} -> {new_sub}"] += 1
        elif old_sub in SUBTOPIC_RENAMES.values():
            stats['already_new_subtopic'] += 1

        # 3. Rename theme
        if old_theme in THEME_RENAMES:
            new_theme = THEME_RENAMES[old_theme]
            task['theme'] = new_theme
            stats['theme_renames'][f"{old_theme} -> {new_theme}"] += 1
        elif old_theme in THEME_RENAMES.values():
            stats['already_new_theme'] += 1

        kept.append(task)

    stats['total_after'] = len(kept)
    stats['removed_total'] = stats['total_before'] - stats['total_after']

    print(f"\n{'='*60}")
    print("TAXONOMY V2 — APPLICATION REPORT")
    print(f"{'='*60}")
    print(f"Tasks before: {stats['total_before']}")
    print(f"Tasks after:  {stats['total_after']}")
    print(f"Removed:      {stats['removed_total']} (garbage subtopics)")
    print()

    print("--- Subtopics renamed ---")
    for k, v in sorted(stats['subtopic_renames'].items()):
        print(f"  {v:4d}x  {k}")
    print(f"  (already had new name: {stats['already_new_subtopic']} tasks)")
    print()

    print("--- Themes renamed ---")
    for k, v in sorted(stats['theme_renames'].items()):
        print(f"  {v:4d}x  {k}")
    print(f"  (already had new name: {stats['already_new_theme']} tasks)")
    print()

    print("--- Garbage subtopics removed ---")
    for k, v in sorted(stats['garbage_by_value'].items()):
        print(f"  {v:4d}x  '{k}'")
    print()

    # Save
    print(f"Saving to {OUTPUT} ...")
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)
    print("Done.")

    # Print final taxonomy summary
    print(f"\n{'='*60}")
    print("FINAL TAXONOMY: themes & subtopic counts")
    print(f"{'='*60}")
    from collections import defaultdict
    theme_subs = defaultdict(set)
    for task in kept:
        th = task.get('theme', '').strip()
        sub = task.get('subtopic', '').strip()
        if th and sub:
            theme_subs[th].add(sub)
    for th in sorted(theme_subs.keys()):
        subs = sorted(theme_subs[th])
        print(f"  [{len(subs):2d}]  {th}")
        for s in subs:
            print(f"         * {s}")

if __name__ == '__main__':
    main()
