#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Очистка сгенерированных задач для 6 класса
Вход: grade6_olympiad_RAW.jsonl
Выход: grade6_olympiad_CLEAN.jsonl

Удаляет:
- Дубликаты по тексту задачи
- Задачи с пустыми полями
- Юникод-мусор и невалидные символы
"""

import json
import re
from typing import List, Dict, Any


def clean_text(text: str) -> str:
    """Очищает текст от юникод-мусора."""
    if not text:
        return ""
    
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def is_valid_task(task: Dict[str, Any]) -> bool:
    """Проверяет валидность задачи."""
    required_fields = ['question', 'answer', 'explanation', 'grade', 'topic', 'level']
    
    # Проверка наличия всех полей
    if not all(field in task for field in required_fields):
        return False
    
    # Проверка на пустые значения
    if not task['question'] or not task['answer'] or not task['explanation']:
        return False
    
    # Проверка минимальной длины
    if len(task['question']) < 20 or len(task['explanation']) < 50:
        return False
    
    return True


def clean_grade6_tasks(input_file='grade6_olympiad_RAW.jsonl', output_file='grade6_olympiad_CLEAN.jsonl'):
    """
    Очищает задачи для 6 класса.
    """
    print("\n" + "="*70)
    print("ОЧИСТКА ЗАДАЧ ДЛЯ 6 КЛАССА")
    print("="*70)
    print(f"[INPUT] {input_file}")
    print(f"[OUTPUT] {output_file}")
    print("="*70 + "\n")
    
    tasks = []
    seen_questions = set()
    
    # Читаем задачи
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    task = json.loads(line)
                    tasks.append(task)
                except json.JSONDecodeError as e:
                    print(f"[WARN] Строка {line_num}: Невалидный JSON - {e}")
    except FileNotFoundError:
        print(f"[ERROR] Файл {input_file} не найден!")
        return
    
    print(f"[INFO] Прочитано задач: {len(tasks)}")
    
    # Фильтрация
    valid_tasks = []
    duplicates = 0
    invalid = 0
    
    for task in tasks:
        # Проверка валидности
        if not is_valid_task(task):
            invalid += 1
            continue
        
        # Очистка текстов
        task['question'] = clean_text(task['question'])
        task['answer'] = clean_text(task['answer'])
        task['explanation'] = clean_text(task['explanation'])
        
        # Проверка на дубликаты
        question_key = task['question'].lower()[:100]  # Первые 100 символов
        if question_key in seen_questions:
            duplicates += 1
            continue
        
        seen_questions.add(question_key)
        valid_tasks.append(task)
    
    # Сохраняем очищенные задачи
    with open(output_file, 'w', encoding='utf-8') as f:
        for task in valid_tasks:
            json.dump(task, f, ensure_ascii=False)
            f.write('\n')
    
    print(f"\n{'='*70}")
    print("РЕЗУЛЬТАТЫ ОЧИСТКИ")
    print("="*70)
    print(f"[OK] Валидных задач: {len(valid_tasks)}")
    print(f"[REMOVED] Дубликатов: {duplicates}")
    print(f"[REMOVED] Невалидных: {invalid}")
    print(f"[TOTAL] Удалено: {duplicates + invalid}")
    print(f"[FILE] Сохранено в: {output_file}")
    print("="*70 + "\n")
    
    # Статистика по темам
    topics_count = {}
    for task in valid_tasks:
        topic = task['topic']
        topics_count[topic] = topics_count.get(topic, 0) + 1
    
    print("Распределение по темам:")
    for topic, count in sorted(topics_count.items()):
        print(f"  - {topic}: {count} задач")


if __name__ == "__main__":
    clean_grade6_tasks()
