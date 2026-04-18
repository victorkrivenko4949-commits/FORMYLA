"""
Добавление якорных задач к сгенерированным для создания полных файлов по 175 задач
"""

import json

# Маппинг файлов
anchor_files = {
    8: "anchor_grade8.json",
    9: "anchor_grade9.json",
    10: "grade10_anchor.json",
    11: "grade11_anchor.json"
}

for grade in [8, 9, 10, 11]:
    print(f"\n{'='*80}")
    print(f"КЛАСС {grade}")
    print(f"{'='*80}")
    
    # Загружаем якорные задачи
    anchor_file = anchor_files[grade]
    try:
        with open(anchor_file, 'r', encoding='utf-8') as f:
            anchors = json.load(f)
        print(f"Загружено {len(anchors)} якорных задач из {anchor_file}")
    except FileNotFoundError:
        print(f"ОШИБКА: Файл {anchor_file} не найден!")
        continue
    
    # Загружаем сгенерированные задачи
    generated_file = f"adaptive_150_tasks_grade{grade}_FINAL.json"
    try:
        with open(generated_file, 'r', encoding='utf-8') as f:
            generated = json.load(f)
        print(f"Загружено {len(generated)} сгенерированных задач из {generated_file}")
    except FileNotFoundError:
        print(f"ОШИБКА: Файл {generated_file} не найден!")
        continue
    
    # Объединяем: сначала якорные (уровень 3), потом сгенерированные (уровни 1,2,4,5,6,7)
    combined = anchors + generated
    
    print(f"Итого: {len(combined)} задач ({len(anchors)} якорных + {len(generated)} сгенерированных)")
    
    # Сохраняем финальный файл
    output_file = f"adaptive_175_tasks_grade{grade}_COMPLETE.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    
    print(f"Сохранено в {output_file}")

print(f"\n{'='*80}")
print("ФИНАЛЬНАЯ СТАТИСТИКА")
print(f"{'='*80}")

total = 0
for grade in [8, 9, 10, 11]:
    output_file = f"adaptive_175_tasks_grade{grade}_COMPLETE.json"
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        count = len(data)
        total += count
        print(f"  Класс {grade}: {count}/175 задач")
    except FileNotFoundError:
        print(f"  Класс {grade}: файл не найден")

print(f"\nВСЕГО: {total}/700 задач")
print(f"{'='*80}\n")
