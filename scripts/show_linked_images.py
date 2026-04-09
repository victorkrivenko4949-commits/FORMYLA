#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Показать все привязанные изображения"""

import sys
sys.path.insert(0, '.')

from problem_images import IMAGE_MAP
from olympiads import OLYMPIADS_DB

print("="*70)
print("ПРИВЯЗАННЫЕ ИЗОБРАЖЕНИЯ К ЗАДАЧАМ")
print("="*70)

# Группируем по combo_id
combos_with_images = {}
for (combo_id, prob_num), filename in IMAGE_MAP.items():
    if combo_id not in combos_with_images:
        combos_with_images[combo_id] = []
    combos_with_images[combo_id].append((prob_num, filename))

print(f"\nВсего combo с картинками: {len(combos_with_images)}")
print(f"Всего привязок: {len(IMAGE_MAP)}\n")

# Показываем первые 20
for combo in OLYMPIADS_DB[:50]:
    combo_id = combo.get('id')
    if combo_id in combos_with_images:
        olympiad = combo.get('olympiad')
        year = combo.get('year')
        grade = combo.get('grade')
        round_title = combo.get('round_title', '')
        
        imgs = combos_with_images[combo_id]
        print(f"Combo {combo_id}: {olympiad} {year}, класс {grade}, {round_title}")
        print(f"  Картинок: {len(imgs)}")
        for prob_num, filename in sorted(imgs):
            print(f"    Задача {prob_num}: {filename}")
        print()

print("="*70)
print("Для просмотра всех привязок откройте problem_images.py")
print("="*70)
