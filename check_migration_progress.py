#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки прогресса и качества миграции олимпиад в LaTeX
"""

import json
import os
import random
import sys

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def check_progress():
    """Проверить прогресс миграции"""
    
    if not os.path.exists('olympiads_latex.json'):
        print("❌ Файл olympiads_latex.json не найден")
        print("Миграция еще не начата или файл не создан")
        return
    
    print("=" * 80)
    print("ПРОВЕРКА ПРОГРЕССА МИГРАЦИИ")
    print("=" * 80)
    
    # Load migrated data
    with open('olympiads_latex.json', 'r', encoding='utf-8') as f:
        migrated_data = json.load(f)
    
    # Load original data
    from olympiads import OLYMPIADS_DB
    
    total_original = len(OLYMPIADS_DB)
    total_migrated = len(migrated_data)
    progress_percent = (total_migrated / total_original) * 100
    
    print(f"\n📊 ОБЩИЙ ПРОГРЕСС:")
    print(f"   Всего олимпиад: {total_original}")
    print(f"   Обработано: {total_migrated}")
    print(f"   Осталось: {total_original - total_migrated}")
    print(f"   Прогресс: {progress_percent:.1f}%")
    
    # Progress bar
    bar_length = 50
    filled = int(bar_length * total_migrated / total_original)
    bar = '█' * filled + '░' * (bar_length - filled)
    print(f"   [{bar}] {progress_percent:.1f}%")
    
    # Count problems
    total_problems = 0
    problems_with_latex = 0
    
    for olympiad in migrated_data:
        for problem in olympiad.get('problems', []):
            total_problems += 1
            if 'text_latex' in problem or 'solution_latex' in problem:
                problems_with_latex += 1
    
    print(f"\n📝 ЗАДАЧИ:")
    print(f"   Всего задач обработано: {total_problems}")
    print(f"   С LaTeX-разметкой: {problems_with_latex}")
    
    # File size
    file_size = os.path.getsize('olympiads_latex.json')
    file_size_mb = file_size / (1024 * 1024)
    print(f"\n💾 РАЗМЕР ФАЙЛА:")
    print(f"   {file_size_mb:.2f} МБ ({file_size:,} байт)")
    
    print("\n" + "=" * 80)


def check_quality(num_samples=3):
    """Проверить качество миграции на случайных примерах"""
    
    if not os.path.exists('olympiads_latex.json'):
        print("❌ Файл olympiads_latex.json не найден")
        return
    
    print("\n" + "=" * 80)
    print(f"ПРОВЕРКА КАЧЕСТВА (случайные {num_samples} задачи)")
    print("=" * 80)
    
    with open('olympiads_latex.json', 'r', encoding='utf-8') as f:
        migrated_data = json.load(f)
    
    # Collect all problems
    all_problems = []
    for olympiad in migrated_data:
        for problem in olympiad.get('problems', []):
            all_problems.append({
                'olympiad': olympiad.get('olympiad_title', 'Unknown'),
                'year': olympiad.get('year', '?'),
                'grade': olympiad.get('grade', '?'),
                'problem': problem
            })
    
    if not all_problems:
        print("❌ Нет обработанных задач")
        return
    
    # Select random samples
    samples = random.sample(all_problems, min(num_samples, len(all_problems)))
    
    for i, sample in enumerate(samples, 1):
        print(f"\n{'=' * 80}")
        print(f"ПРИМЕР {i}/{num_samples}")
        print(f"Олимпиада: {sample['olympiad']}, {sample['year']}, {sample['grade']} класс")
        print(f"Задача №{sample['problem'].get('num', '?')}")
        print("=" * 80)
        
        problem = sample['problem']
        
        # Check text
        if 'text_latex' in problem:
            original = problem.get('text', '')
            latex = problem.get('text_latex', '')
            
            print("\n📄 УСЛОВИЕ (первые 300 символов):")
            print("-" * 80)
            print("ОРИГИНАЛ:")
            print(original[:300] + ('...' if len(original) > 300 else ''))
            print("\nLATEX:")
            print(latex[:300] + ('...' if len(latex) > 300 else ''))
            
            # Analysis
            has_dollars = '$' in latex
            latex_commands = ['\\frac', '\\sqrt', '\\cdot', '_', '^', '\\geq', '\\leq']
            found_commands = [cmd for cmd in latex_commands if cmd in latex]
            
            print("\n🔍 АНАЛИЗ:")
            print(f"   Знаки $: {'✅ ДА' if has_dollars else '❌ НЕТ'}")
            if found_commands:
                print(f"   LaTeX команды: {', '.join(found_commands)}")
        
        # Check solution
        if 'solution_latex' in problem:
            solution_latex = problem.get('solution_latex', '')
            has_dollars_sol = '$' in solution_latex
            found_commands_sol = [cmd for cmd in latex_commands if cmd in solution_latex]
            
            print(f"\n💡 РЕШЕНИЕ:")
            print(f"   Знаки $: {'✅ ДА' if has_dollars_sol else '❌ НЕТ'}")
            if found_commands_sol:
                print(f"   LaTeX команды: {', '.join(found_commands_sol)}")
    
    print("\n" + "=" * 80)


def main():
    """Main entry point"""
    check_progress()
    
    # Ask if user wants to see quality samples
    print("\n💡 Хотите проверить качество на случайных примерах? (y/n): ", end='')
    try:
        response = input().strip().lower()
        if response in ['y', 'yes', 'д', 'да']:
            check_quality(num_samples=3)
    except:
        pass


if __name__ == "__main__":
    main()
