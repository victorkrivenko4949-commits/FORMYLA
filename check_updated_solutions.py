#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Проверка обновлённых решений
"""

import sys
import codecs
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from olympiads_with_original_solutions import OLYMPIADS_DB
import re

def check_latex_quality(solution):
    """Проверить качество LaTeX форматирования"""
    if not solution:
        return False, {}
    
    checks = {
        'has_inline_latex': bool(re.search(r'\\\(.*?\\\)', solution)),
        'has_frac': bool(re.search(r'\\frac\{', solution)),
        'no_unicode_superscript': '²' not in solution and '³' not in solution,
        'no_unicode_sqrt': '√' not in solution,
        'no_unicode_inequality': '≥' not in solution and '≤' not in solution,
    }
    return all(checks.values()), checks

print("="*80)
print("📊 АНАЛИЗ ОБНОВЛЁННЫХ РЕШЕНИЙ")
print("="*80)

total_problems = 0
problems_with_solutions = 0
perfect_latex = 0
has_inline_latex = 0

# Собираем первые 5 примеров для демонстрации
examples = []

for olympiad in OLYMPIADS_DB[:20]:  # Проверяем первые 20 олимпиад (где были обновления)
    for problem in olympiad.get('problems', []):
        total_problems += 1
        solution = problem.get('solution', '')
        
        if solution and len(solution) > 100:
            problems_with_solutions += 1
            is_perfect, checks = check_latex_quality(solution)
            
            if checks.get('has_inline_latex'):
                has_inline_latex += 1
            
            if is_perfect:
                perfect_latex += 1
            
            # Собираем примеры
            if len(examples) < 3 and checks.get('has_inline_latex'):
                examples.append({
                    'olympiad': olympiad.get('olympiad_title', ''),
                    'year': olympiad.get('year', ''),
                    'grade': olympiad.get('grade', ''),
                    'num': problem.get('num', ''),
                    'solution': solution[:500],
                    'checks': checks
                })

print(f"\n📈 СТАТИСТИКА:")
print(f"  Всего задач проверено: {total_problems}")
print(f"  Задач с решениями: {problems_with_solutions}")
print(f"  С LaTeX форматированием: {has_inline_latex}")
print(f"  С идеальным LaTeX: {perfect_latex}")

if has_inline_latex > 0:
    print(f"  Качество LaTeX: {100*perfect_latex//has_inline_latex}%")

print(f"\n{'='*80}")
print("📝 ПРИМЕРЫ ОБНОВЛЁННЫХ РЕШЕНИЙ:")
print("="*80)

for i, example in enumerate(examples, 1):
    print(f"\n[ПРИМЕР {i}]")
    print(f"Олимпиада: {example['olympiad']} {example['year']}, {example['grade']} класс, Задача #{example['num']}")
    print(f"\nРешение (первые 500 символов):")
    print("-"*80)
    print(example['solution'])
    print("-"*80)
    print(f"Проверка LaTeX:")
    for check, result in example['checks'].items():
        status = "✅" if result else "❌"
        print(f"  {status} {check}")

print(f"\n{'='*80}")
