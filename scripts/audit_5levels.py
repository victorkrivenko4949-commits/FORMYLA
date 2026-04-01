# -*- coding: utf-8 -*-
"""
Аудит базы с 5 уровнями
Показывает ячейки с недостаточным количеством задач
"""
import sys
import os
import codecs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

from problems import PROBLEMS_DB
from app import SUBJECTS, SUBTOPICS, GRADES

print("="*70)
print("Аудит базы данных (5 уровней)")
print("="*70)

incomplete_cells = []

# Проверяем каждую ячейку
for subject_key in SUBJECTS.keys():
    if subject_key == "other":
        continue
    
    subtopics = SUBTOPICS.get(subject_key, {})
    
    for subtopic_key in subtopics.keys():
        for grade in GRADES:
            for level in range(1, 6):  # Уровни 1-5
                tasks = [
                    p for p in PROBLEMS_DB
                    if p.get('subject') == subject_key
                    and p.get('subtopic') == subtopic_key
                    and p.get('grade') == grade
                    and p.get('difficulty') == level
                ]
                
                count = len(tasks)
                
                if count < 5:
                    incomplete_cells.append({
                        "subject": subject_key,
                        "subtopic": subtopic_key,
                        "grade": grade,
                        "level": level,
                        "count": count,
                        "needed": 5 - count
                    })

# Сортируем по количеству (самые пустые сначала)
incomplete_cells.sort(key=lambda x: x['count'])

print(f"\n📊 Статистика:")
print(f"  Неполных ячеек (< 5 задач): {len(incomplete_cells)}")
print(f"  Нужно создать задач: {sum(c['needed'] for c in incomplete_cells)}")

# Показываем самые пустые
print("\n" + "="*70)
print("Самые пустые ячейки (первые 20):")
print("="*70)

for i, cell in enumerate(incomplete_cells[:20], 1):
    print(f"\n{i}. {cell['subject']} → {cell['subtopic']}")
    print(f"   {cell['grade']} класс, Уровень {cell['level']}")
    print(f"   Есть: {cell['count']} задач, Нужно: {cell['needed']} задач")

# Группируем по разделам
from collections import Counter
by_subject = Counter(c['subject'] for c in incomplete_cells)

print("\n" + "="*70)
print("Неполные ячейки по разделам:")
print("="*70)
for subject, count in by_subject.most_common():
    print(f"  {subject}: {count} неполных ячеек")

print("\n✅ Аудит завершен")
