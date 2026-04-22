#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт олимпиадных задач для 6 класса в БД
Вход: grade6_olympiad_CLEAN.jsonl
Таблица: adaptive_tasks (class_level=6)
"""

import json
from app import app
from models import db, AdaptiveTask


def import_grade6_tasks(input_file='grade6_olympiad_CLEAN.jsonl'):
    """
    Импортирует задачи для 6 класса в БД.
    """
    print("\n" + "="*70)
    print("ИМПОРТ ЗАДАЧ ДЛЯ 6 КЛАССА В БД")
    print("="*70)
    print(f"[INPUT] {input_file}")
    print("="*70 + "\n")
    
    with app.app_context():
        # Читаем задачи
        tasks = []
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                for line in f:
                    tasks.append(json.loads(line))
        except FileNotFoundError:
            print(f"[ERROR] Файл {input_file} не найден!")
            print("Сначала запустите clean_grade6.py")
            return
        
        print(f"[INFO] Прочитано задач: {len(tasks)}")
        
        # Проверяем существующие задачи для 6 класса
        existing_count = AdaptiveTask.query.filter_by(class_level=6).count()
        print(f"[INFO] Существующих задач для 6 класса в БД: {existing_count}")
        
        if existing_count > 0:
            response = input(f"\nВ БД уже есть {existing_count} задач для 6 класса. Удалить и импортировать заново? (yes/no): ")
            if response.lower() != 'yes':
                print("[STOP] Импорт отменен")
                return
            
            # Удаляем старые задачи
            AdaptiveTask.query.filter_by(class_level=6).delete()
            db.session.commit()
            print(f"[OK] Удалено {existing_count} старых задач")
        
        # Импортируем задачи
        imported = 0
        skipped = 0
        
        for task_data in tasks:
            try:
                # Проверка на дубликаты по тексту задачи
                existing = AdaptiveTask.query.filter_by(
                    class_level=6,
                    task_text=task_data['question']
                ).first()
                
                if existing:
                    skipped += 1
                    continue
                
                # Создаем новую задачу
                task = AdaptiveTask(
                    class_level=6,
                    difficulty_level=task_data['level'],
                    topic=task_data['topic'],
                    task_text=task_data['question'],
                    solution=task_data['explanation'],
                    correct_answer=task_data['answer'],
                    # Критерии оценивания (заглушки, можно улучшить)
                    criteria_1_point="Частичное решение или правильная идея",
                    criteria_2_points="Полное правильное решение"
                )
                
                db.session.add(task)
                imported += 1
                
                # Коммитим каждые 50 задач
                if imported % 50 == 0:
                    db.session.commit()
                    print(f"[PROGRESS] Импортировано: {imported}")
                
            except Exception as e:
                print(f"[ERROR] Ошибка при импорте задачи: {e}")
                print(f"         Тема: {task_data.get('topic')}, Уровень: {task_data.get('level')}")
                skipped += 1
        
        # Финальный коммит
        db.session.commit()
        
        print(f"\n{'='*70}")
        print("РЕЗУЛЬТАТЫ ИМПОРТА")
        print("="*70)
        print(f"[OK] Успешно импортировано: {imported}")
        print(f"[SKIP] Пропущено (дубликаты/ошибки): {skipped}")
        print(f"[TOTAL] Всего задач для 6 класса в БД: {AdaptiveTask.query.filter_by(class_level=6).count()}")
        print("="*70 + "\n")
        
        # Статистика по темам
        topics = db.session.query(
            AdaptiveTask.topic,
            db.func.count(AdaptiveTask.id)
        ).filter_by(class_level=6).group_by(AdaptiveTask.topic).all()
        
        print("Распределение по темам:")
        for topic, count in topics:
            print(f"  - {topic}: {count} задач")
        
        # Статистика по уровням
        levels = db.session.query(
            AdaptiveTask.difficulty_level,
            db.func.count(AdaptiveTask.id)
        ).filter_by(class_level=6).group_by(AdaptiveTask.difficulty_level).all()
        
        print("\nРаспределение по уровням:")
        for level, count in sorted(levels):
            print(f"  - Уровень {level}: {count} задач")


if __name__ == "__main__":
    import_grade6_tasks()
