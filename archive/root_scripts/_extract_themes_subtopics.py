#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Извлечь все темы (theme) и подтемы (subtopic) из исходного baseline-файла.

Структура: 45 тем x 3 подтемы = 135 подтем (как указал пользователь).
Группировка по классам (grade 5-11).
"""
import json
import sys
from collections import OrderedDict

FILE = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'

with open(FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Перенаправляем вывод в файл
out = open('themes_subtopics_report.txt', 'w', encoding='utf-8')

def pr(*args, **kwargs):
    kwargs['file'] = out
    print(*args, **kwargs)

pr(f"Всего записей: {len(data)}")
pr()

# --- 1. Уникальные темы ---
themes = set()
for t in data:
    th = t.get('theme', '').strip()
    if th:
        themes.add(th)

themes_sorted = sorted(themes)
pr(f"Всего уникальных тем (theme): {len(themes_sorted)}")
pr()

# --- 2. Уникальные подтемы ---
subtopics = set()
for t in data:
    st = t.get('subtopic', '').strip()
    if st:
        subtopics.add(st)

subtopics_sorted = sorted(subtopics)
pr(f"Всего уникальных подтем (subtopic): {len(subtopics_sorted)}")
pr()

# --- 3. Подтемы, сгруппированные по темам ---
theme_to_subtopics = OrderedDict()
for th in themes_sorted:
    subs = set()
    for t in data:
        if t.get('theme', '').strip() == th:
            st = t.get('subtopic', '').strip()
            if st:
                subs.add(st)
    theme_to_subtopics[th] = sorted(subs)

pr("=" * 80)
pr("ПОДТЕМЫ, СГРУППИРОВАННЫЕ ПО ТЕМАМ")
pr("=" * 80)
for i, (th, subs) in enumerate(theme_to_subtopics.items(), 1):
    pr(f"\n{i:2d}. [{th}] -- {len(subs)} подтем(ы)")
    for j, st in enumerate(subs, 1):
        pr(f"       {j}. {st}")

# --- 4. Темы и подтемы, сгруппированные по классам ---
pr()
pr("=" * 80)
pr("ТЕМЫ И ПОДТЕМЫ ПО КЛАССАМ (grade)")
pr("=" * 80)

grades = sorted(set(t.get('grade') for t in data if t.get('grade') is not None))
for g in grades:
    grade_themes = set()
    grade_subtopics = set()
    for t in data:
        if t.get('grade') == g:
            th = t.get('theme', '').strip()
            st = t.get('subtopic', '').strip()
            if th:
                grade_themes.add(th)
            if st:
                grade_subtopics.add(st)
    
    pr(f"\n--- КЛАСС {g} ---")
    pr(f"  Тем: {len(grade_themes)}")
    pr(f"  Подтем: {len(grade_subtopics)}")
    for th in sorted(grade_themes):
        subs = []
        for t in data:
            if t.get('grade') == g and t.get('theme','').strip() == th:
                st = t.get('subtopic','').strip()
                if st:
                    subs.append(st)
        uniq_subs = sorted(set(subs))
        pr(f"    * {th} ({len(uniq_subs)} подтем)")
        for st in uniq_subs:
            pr(f"        - {st}")

# --- 5. Проверка: по 3 подтемы на тему? ---
pr()
pr("=" * 80)
pr("ПРОВЕРКА: темы, где не 3 подтемы")
pr("=" * 80)
non_three = [(th, subs) for th, subs in theme_to_subtopics.items() if len(subs) != 3]
if non_three:
    pr(f"Тем с количеством подтем != 3: {len(non_three)}")
    for th, subs in non_three:
        pr(f"  [{th}] -- {len(subs)} подтем: {', '.join(subs)}")
else:
    pr("ВСЕ темы имеют ровно по 3 подтемы!")

# --- 6. Сводная статистика ---
pr()
pr("=" * 80)
pr("СВОДНАЯ СТАТИСТИКА")
pr("=" * 80)
total_themes = len(themes)
total_subtopics = len(subtopics)
themes_with_3 = sum(1 for subs in theme_to_subtopics.values() if len(subs) == 3)
pr(f"  Всего тем (theme):          {total_themes}")
pr(f"  Всего подтем (subtopic):    {total_subtopics}")
pr(f"  Тем с 3 подтемами:          {themes_with_3}")
pr(f"  Ожидалось (45x3):           45 x 3 = 135")
pr(f"  Совпадает:                  {'ДА' if total_themes == 45 and total_subtopics == 135 else 'НЕТ'}")

out.close()
print(f"Report written to themes_subtopics_report.txt")
