#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Оборачивание математических выражений в LaTeX теги \\( ... \\)
ТОЛЬКО оборачивание, БЕЗ изменения содержимого!
"""

import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import json
import re
from problems import PROBLEMS_DB

def wrap_math_in_latex(text):
    """
    Оборачивает математические выражения в \\( ... \\)
    Использует регулярные выражения для поиска формул
    """
    if not text:
        return text
    
    # Если уже обернуто - не трогаем
    if '\\(' in text or '\\[' in text:
        return text
    
    # Паттерны для математических выражений
    patterns = [
        # Уравнения с переменными и операторами: x^2 + 5x = 0
        (r'([a-zA-Zа-яА-Я]\s*[\^_]?\s*\d*\s*[+\-*/=<>≤≥]\s*[a-zA-Zа-яА-Я0-9\^_+\-*/=<>≤≥\s()]+)', r'\\( \1 \\)'),
        # Отдельные переменные со степенями: x^2, a_n
        (r'([a-zA-Z][_^]\d+)', r'\\( \1 \\)'),
        # Дроби и корни (если есть)
        (r'(√\d+|√[a-zA-Z])', r'\\( \1 \\)'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result)
    
    return result

print("=" * 80)
print("ТЕСТ: Оборачивание формул в LaTeX теги (первые 5 задач)")
print("=" * 80)

# Тестируем на первых 5 задачах
test_tasks = PROBLEMS_DB[:5]

print("\n📝 ДО обработки:")
for i, task in enumerate(test_tasks):
    print(f"\nЗадача {i+1}:")
    print(f"  text: {task.get('text', '')[:100]}...")
    if task.get('answer'):
        print(f"  answer: {task.get('answer')[:50]}...")

print("\n" + "=" * 80)
print("🔄 ОБРАБОТКА...")
print("=" * 80)

# Обрабатываем
processed = []
for task in test_tasks:
    new_task = task.copy()
    new_task['text'] = wrap_math_in_latex(task.get('text', ''))
    if task.get('answer'):
        new_task['answer'] = wrap_math_in_latex(task.get('answer', ''))
    processed.append(new_task)

print("\n✅ ПОСЛЕ обработки:")
for i, task in enumerate(processed):
    print(f"\nЗадача {i+1}:")
    print(f"  text: {task.get('text', '')[:150]}...")
    if task.get('answer'):
        print(f"  answer: {task.get('answer')[:80]}...")

print("\n" + "=" * 80)
print("ТЕСТ ЗАВЕРШЕН")