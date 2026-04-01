# -*- coding: utf-8 -*-
"""
Аудит базы данных задач
Проверяет заполненность каждой ячейки (раздел -> подтема -> класс -> уровень)
Цель: РОВНО 5 задач в каждой ячейке
Учитывает ограничения по классам (например, "8-11" для неравенств)
Игнорирует подтемы "other_..."
"""
import sys
import os
import json
import codecs
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB
from app import SUBJECTS, SUBTOPICS, GRADES

def parse_grade_restriction(subtopic_title):
    """
    Извлекает ограничение по классам из названия подтемы.
    Например: "Неравенства и оценки (8-11)" -> (8, 11)
    Возвращает (min_grade, max_grade) или (None, None) если ограничений нет
    """
    match = re.search(r'\((\d+)-(\d+)\)', subtopic_title)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (None, None)

def is_grade_allowed(grade, subtopic_title):
    """
    Проверяет, разрешен ли класс для данной подтемы
    """
    min_grade, max_grade = parse_grade_restriction(subtopic_title)
    if min_grade is None:
        return True
    return min_grade <= grade <= max_grade

print("="*70)
print("Аудит базы данных задач FORMYLA")
print("="*70)
print(f"Всего задач в базе: {len(PROBLEMS_DB)}")

# Структура для хранения недостающих задач
missing_tasks = []
overfilled_cells = []
perfect_cells = []
skipped_cells = []

# Проверяем каждую комбинацию
for subject_key, subject_title in SUBJECTS.items():
    if subject_key == "other":  # Пропускаем "Другие темы"
        continue
    
    subtopics = SUBTOPICS.get(subject_key, {})
    
    for subtopic_key, subtopic_title in subtopics.items():
        # Пропускаем подтемы "other_..."
        if subtopic_key.startswith("other_"):
            print(f"⏭️  Пропускаем: {subject_key} -> {subtopic_key}")
            continue
        
        for grade in GRADES:
            # Проверяем ограничения по классам
            if not is_grade_allowed(grade, subtopic_title):
                skipped_cells.append({
                    "subject": subject_key,
                    "subtopic": subtopic_key,
                    "grade": grade,
                    "reason": f"Класс {grade} не входит в диапазон для '{subtopic_title}'"
                })
                continue
            
            for level in range(1, 8):  # Уровни 1-7
                # Считаем задачи для этой ячейки
                tasks = [
                    p for p in PROBLEMS_DB
                    if p.get('subject') == subject_key
                    and p.get('subtopic') == subtopic_key
                    and p.get('grade') == grade
                    and p.get('difficulty') == level
                ]
                
                count = len(tasks)
                
                if count < 5:
                    missing_tasks.append({
                        "subject": subject_key,
                        "subject_title": subject_title,
                        "subtopic": subtopic_key,
                        "subtopic_title": subtopic_title,
                        "grade": grade,
                        "level": level,
                        "current": count,
                        "needed": 5 - count
                    })
                elif count > 5:
                    overfilled_cells.append({
                        "subject": subject_key,
                        "subtopic": subtopic_key,
                        "grade": grade,
                        "level": level,
                        "count": count
                    })
                else:
                    perfect_cells.append({
                        "subject": subject_key,
                        "subtopic": subtopic_key,
                        "grade": grade,
                        "level": level
                    })

# Статистика
print(f"\n📊 Общая статистика:")
print(f"  Идеальных ячеек (ровно 5 задач): {len(perfect_cells)}")
print(f"  Неполных ячеек (< 5 задач): {len(missing_tasks)}")
print(f"  Переполненных ячеек (> 5 задач): {len(overfilled_cells)}")
print(f"  Пропущенных ячеек (ограничения по классам): {len(skipped_cells)}")

total_cells = len(perfect_cells) + len(missing_tasks) + len(overfilled_cells)
print(f"  Всего активных ячеек: {total_cells}")

# Подсчет недостающих задач
total_needed = sum(task['needed'] for task in missing_tasks)
total_current = sum(task['current'] for task in missing_tasks)
print(f"\n📝 Задач в неполных ячейках:")
print(f"  Текущее количество: {total_current}")
print(f"  Нужно добавить: {total_needed}")
print(f"  Будет после заполнения: {total_current + total_needed}")

# Сохраняем отчет
print("\n💾 Сохранение отчета...")
os.makedirs("data", exist_ok=True)

report = {
    "summary": {
        "perfect_cells": len(perfect_cells),
        "incomplete_cells": len(missing_tasks),
        "overfilled_cells": len(overfilled_cells),
        "skipped_cells": len(skipped_cells),
        "total_cells": total_cells,
        "total_tasks_needed": total_needed,
        "total_current_in_incomplete": total_current
    },
    "missing_tasks": missing_tasks,  # Все недостающие задачи
    "overfilled_cells": overfilled_cells,
    "skipped_cells": skipped_cells[:20]  # Примеры пропущенных
}

with open("data/missing_tasks.json", 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("✓ Отчет сохранен: data/missing_tasks.json")

# Показываем примеры
print("\n" + "="*70)
print("Примеры неполных ячеек (первые 10):")
print("="*70)

for i, task in enumerate(missing_tasks[:10], 1):
    print(f"\n{i}. {task['subject_title']} → {task['subtopic_title']}")
    print(f"   {task['grade']} класс, Уровень {task['level']}")
    print(f"   Есть: {task['current']} задач, Нужно: {task['needed']} задач")

print("\n" + "="*70)
print("✅ АУДИТ ЗАВЕРШЕН")
print("="*70)
print(f"\nИтого:")
print(f"  Неполных ячеек: {len(missing_tasks)}")
print(f"  Нужно создать задач: {total_needed}")
print(f"\nОтчет сохранен в: data/missing_tasks.json")
