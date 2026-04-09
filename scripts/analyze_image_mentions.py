#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Анализ упоминаний рисунков в задачах"""

import sys
sys.path.insert(0, '.')
from olympiads import OLYMPIADS_DB

keywords = ['рисунок', 'чертеж', 'схема', 'график', 'диаграмм', 'см. рис', 'на рисунке', 'ниже']

tasks_with_images = 0
total_tasks = 0

for combo in OLYMPIADS_DB:
    for problem in combo.get('problems', []):
        total_tasks += 1
        text = problem.get('text', '').lower()
        if any(word in text for word in keywords):
            tasks_with_images += 1

print(f'Всего задач: {total_tasks}')
print(f'С упоминанием рисунка: {tasks_with_images}')
print(f'Процент: {tasks_with_images/total_tasks*100:.1f}%')
