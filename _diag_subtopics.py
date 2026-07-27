#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose what subtopics exist in the JSON file."""
import json

INPUT = r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_L3_completed.json'

with open(INPUT, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total tasks: {len(data)}")

# Collect all unique subtopics
subs = set()
themes = set()
for t in data:
    subs.add(t.get('subtopic', ''))
    themes.add(t.get('theme', ''))

print(f"\nUnique subtopics ({len(subs)}):")
for s in sorted(subs):
    print(f"  [{sum(1 for t in data if t.get('subtopic','')==s):4d}] {s}")

print(f"\nUnique themes ({len(themes)}):")
for th in sorted(themes):
    print(f"  [{sum(1 for t in data if t.get('theme','')==th):4d}] {th}")

# Check specific rename targets
print("\n\n=== RENAME TARGETS ===")
targets = [
    'Уравнения с модулем',
    'Площадь круга и его частей',
    'Тригонометрические уравнения с отбором корней',
    'Рациональные уравнения',
    'Прикладные задачи',
    'Алгоритмы и вычисления',
    'Метод замены в иррациональных уравнениях',
    'Иррациональные уравнения с одним корнем',
    'Иррациональные уравнения с несколькими корнями',
    'Скрещивающиеся прямые',
    'Неравенства Чебышева и Маркова',
    'Уравнения вида R(sin x, cos x) = 0 и подстановка Вейерштрасса',
    'Булевы функции и их минимизация',
]
for tgt in targets:
    cnt = sum(1 for t in data if t.get('subtopic','') == tgt)
    print(f"  '{tgt}': {cnt} tasks")

# Check theme targets
print("\n=== THEME TARGETS ===")
theme_targets = ['Комбинаторика и вероятность', 'Вероятность и комбинаторика']
for tgt in theme_targets:
    cnt = sum(1 for t in data if t.get('theme','') == tgt)
    print(f"  '{tgt}': {cnt} tasks")

# Check garbage (exact + partial)
print("\n=== GARBAGE SUBTOPICS ===")
garbage = ['Formula_Unity', 'Kurchatov', 'Ломоносов', 'Физтех', 'Эйлера']
for g in garbage:
    exact = sum(1 for t in data if t.get('subtopic','') == g)
    partial = sum(1 for t in data if g in t.get('subtopic',''))
    print(f"  '{g}': exact={exact}, partial_contains={partial}")
    if partial > 0:
        for t in data:
            s = t.get('subtopic','')
            if g in s and s != g:
                print(f"      -> \"{s}\"")
