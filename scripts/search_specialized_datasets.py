s# -*- coding: utf-8 -*-
"""
Поиск специализированных математических датасетов
Для геометрии, комбинаторики, теории чисел, движения, логики
"""
import sys
import codecs
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Поиск специализированных математических датасетов")
print("="*70)

# Расширенный список датасетов
DATASETS_TO_TRY = [
    # Геометрия
    ("geometry_qa", "Геометрия QA"),
    ("math_geometry", "Математическая геометрия"),
    ("euclidean_geometry", "Евклидова геометрия"),
    
    # Комбинаторика
    ("combinatorics_problems", "Задачи по комбинаторике"),
    ("discrete_math", "Дискретная математика"),
    
    # Теория чисел
    ("number_theory_problems", "Теория чисел"),
    ("prime_numbers", "Простые числа"),
    
    # Логика
    ("logic_puzzles", "Логические головоломки"),
    ("knights_and_knaves", "Рыцари и лжецы"),
    
    # Общие математические
    ("math_word_problems", "Текстовые задачи"),
    ("elementary_math", "Элементарная математика"),
    
    # Уже известные
    ("d0rj/ROMB-1.0", "Российские олимпиады"),
    ("d0rj/gsm8k-ru", "GSM8K русский"),
]

from datasets import load_dataset
import time

successful = []
failed = []

for dataset_name, description in DATASETS_TO_TRY:
    print(f"\nПроверка: {dataset_name}")
    
    try:
        dataset = load_dataset(dataset_name, split="train[:3]")
        print(f"  ✓ ДОСТУПЕН!")
        successful.append((dataset_name, description))
    except Exception as e:
        error = str(e)[:80]
        if "split" in error.lower():
            try:
                dataset = load_dataset(dataset_name, split="test[:3]")
                print(f"  ✓ ДОСТУПЕН (test)!")
                successful.append((dataset_name, description))
            except:
                print(f"  ✗ Недоступен")
                failed.append(dataset_name)
        else:
            print(f"  ✗ Недоступен")
            failed.append(dataset_name)
    
    time.sleep(0.3)

print("\n" + "="*70)
print("РЕЗУЛЬТАТЫ")
print("="*70)
print(f"\n✓ Доступные: {len(successful)}")
for name, desc in successful:
    print(f"  - {name}")

print(f"\n✗ Недоступные: {len(failed)}")

if len(successful) <= 2:
    print("\n⚠️  Специализированные датасеты не найдены")
    print("\nРЕКОМЕНДАЦИЯ:")
    print("Используйте генерацию задач через DeepSeek API")
    print("Или перераспределите существующие задачи")
