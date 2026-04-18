"""
Объединение всех генераций для 8-11 классов
"""

import json
import os

# Проверяем все доступные файлы
for grade in [8, 9, 10, 11]:
    print(f"\n{'='*80}")
    print(f"КЛАСС {grade}")
    print(f"{'='*80}")
    
    all_tasks = []
    seen_signatures = set()
    
    # Список всех возможных файлов для этого класса
    possible_files = [
        f"adaptive_150_tasks_grade{grade}.json",
        f"adaptive_150_tasks_grade{grade}_COMPLETE.json",
        f"adaptive_150_tasks_grade{grade}_FINAL.json"
    ]
    
    for filename in possible_files:
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    tasks = json.load(f)
                
                print(f"  {filename}: {len(tasks)} задач")
                
                # Добавляем уникальные задачи
                for task in tasks:
                    # Создаем сигнатуру задачи (тема + уровень)
                    signature = (task.get("topic", ""), task.get("difficulty_level", 0))
                    
                    if signature not in seen_signatures:
                        seen_signatures.add(signature)
                        all_tasks.append(task)
                
            except Exception as e:
                print(f"  {filename}: ОШИБКА - {e}")
    
    print(f"\nУникальных задач: {len(all_tasks)}")
    
    # Сортируем по номеру вопроса
    all_tasks.sort(key=lambda x: x.get("question_number", 0))
    
    # Перенумеруем
    for i, task in enumerate(all_tasks, 1):
        task["question_number"] = i
    
    # Сохраняем
    output_file = f"adaptive_150_tasks_grade{grade}_MERGED.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_tasks, f, ensure_ascii=False, indent=2)
    
    print(f"Сохранено в {output_file}")

print(f"\n{'='*80}")
print("ОБЪЕДИНЕНИЕ ЗАВЕРШЕНО")
print(f"{'='*80}\n")
