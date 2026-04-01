# -*- coding: utf-8 -*-
"""
Поиск датасетов с задачами для старших классов (10-11)
"""
import sys
import codecs
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Поиск датасетов для 10-11 классов (сложная математика)")
print("="*70)

# Датасеты для проверки
DATASETS_TO_TRY = [
    # Сложная математика
    ("hendrycks_math", "MATH dataset - сложные задачи"),
    ("competition_math", "Математические соревнования"),
    ("deepmind/mathematics_dataset", "DeepMind математика"),
    ("EleutherAI/math_qa", "Math QA"),
    ("allenai/math_qa", "AllenAI Math QA"),
    ("math_dataset", "Математический датасет"),
    
    # Русские датасеты
    ("d0rj/russian_math_olympiad", "Русские олимпиады"),
    ("ai-forever/school_math_ru", "Школьная математика РФ"),
]

from datasets import load_dataset
import time

successful = []
failed = []

for dataset_name, description in DATASETS_TO_TRY:
    print(f"\nПроверка: {dataset_name}")
    print(f"  Описание: {description}")
    
    try:
        dataset = load_dataset(dataset_name, split="train[:3]")
        print(f"  ✓ ДОСТУПЕН!")
        if len(dataset) > 0:
            print(f"  Поля: {list(dataset[0].keys())}")
            print(f"  Пример: {str(dataset[0])[:200]}...")
            successful.append((dataset_name, description))
    except Exception as e:
        error = str(e)[:100]
        if "split" in error.lower():
            try:
                dataset = load_dataset(dataset_name, split="test[:3]")
                print(f"  ✓ ДОСТУПЕН (test split)!")
                if len(dataset) > 0:
                    print(f"  Поля: {list(dataset[0].keys())}")
                    successful.append((dataset_name, description))
            except:
                print(f"  ✗ Недоступен: {error}")
                failed.append(dataset_name)
        else:
            print(f"  ✗ Ошибка: {error}")
            failed.append(dataset_name)
    
    time.sleep(0.5)

print("\n" + "="*70)
print("РЕЗУЛЬТАТЫ")
print("="*70)
print(f"\n✓ Доступные: {len(successful)}")
for name, desc in successful:
    print(f"  - {name}: {desc}")

print(f"\n✗ Недоступные: {len(failed)}")
for name in failed:
    print(f"  - {name}")

if not successful:
    print("\n⚠️  Датасеты для 10-11 классов не найдены")
    print("Рекомендация: Перераспределить существующие задачи по всем классам")
