# -*- coding: utf-8 -*-
"""
Поиск математических датасетов на HuggingFace
"""
import sys
import codecs
if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

print("="*70)
print("Поиск математических датасетов на HuggingFace")
print("="*70)

# Список потенциальных датасетов для проверки
DATASETS_TO_TRY = [
    # Русские математические датасеты
    ("d0rj/ROMB-1.0", "Российские олимпиады (уже загружен)"),
    ("Vikhrmodels/russian_math", "Русская математика (требует авторизации)"),
    ("IlyaGusev/ru_turbo_alpaca", "Русский обучающий датасет"),
    ("d0rj/gsm8k-ru", "GSM8K переведенный на русский"),
    ("ai-forever/MERA", "Русский бенчмарк"),
    
    # Английские математические датасеты (можно перевести)
    ("lighteval/MATH", "Математические задачи MATH"),
    ("gsm8k", "Grade School Math 8K"),
    ("competition_math", "Математические соревнования"),
    ("math_qa", "Math Question Answering"),
    ("aqua_rat", "Algebra Question Answering"),
    ("hendrycks/math", "MATH dataset"),
]

print("\nПопытка загрузки датасетов...\n")

from datasets import load_dataset
import time

successful_datasets = []
failed_datasets = []

for dataset_name, description in DATASETS_TO_TRY:
    print(f"Проверка: {dataset_name}")
    print(f"  Описание: {description}")
    
    try:
        # Пробуем загрузить первые 5 примеров
        dataset = load_dataset(dataset_name, split="train[:5]")
        print(f"  ✓ ДОСТУПЕН! Примеров в train: загружено 5")
        
        # Показываем структуру
        if len(dataset) > 0:
            print(f"  Поля: {list(dataset[0].keys())}")
            successful_datasets.append((dataset_name, description, dataset))
        
    except Exception as e:
        error_msg = str(e)
        if "gated" in error_msg.lower() or "auth" in error_msg.lower():
            print(f"  ✗ Требует авторизации")
        elif "split" in error_msg.lower():
            # Попробуем другой split
            try:
                dataset = load_dataset(dataset_name, split="test[:5]")
                print(f"  ✓ ДОСТУПЕН (test split)! Загружено 5 примеров")
                if len(dataset) > 0:
                    print(f"  Поля: {list(dataset[0].keys())}")
                    successful_datasets.append((dataset_name, description, dataset))
            except:
                print(f"  ✗ Недоступен")
                failed_datasets.append((dataset_name, error_msg))
        else:
            print(f"  ✗ Ошибка: {error_msg[:100]}")
            failed_datasets.append((dataset_name, error_msg))
    
    print()
    time.sleep(0.5)  # Небольшая пауза между запросами

print("="*70)
print("РЕЗУЛЬТАТЫ")
print("="*70)

print(f"\n✓ Доступные датасеты ({len(successful_datasets)}):")
for name, desc, _ in successful_datasets:
    print(f"  - {name}")
    print(f"    {desc}")

print(f"\n✗ Недоступные датасеты ({len(failed_datasets)}):")
for name, _ in failed_datasets:
    print(f"  - {name}")

if successful_datasets:
    print("\n" + "="*70)
    print("ПРИМЕРЫ ИЗ ДОСТУПНЫХ ДАТАСЕТОВ")
    print("="*70)
    
    for name, desc, dataset in successful_datasets[:3]:  # Показываем первые 3
        print(f"\n{name}:")
        print(f"Пример задачи:")
        if len(dataset) > 0:
            example = dataset[0]
            for key, value in example.items():
                value_str = str(value)[:200] + "..." if len(str(value)) > 200 else str(value)
                print(f"  {key}: {value_str}")

print("\n" + "="*70)
print("Следующий шаг: Выберите датасет для загрузки")
print("="*70)
