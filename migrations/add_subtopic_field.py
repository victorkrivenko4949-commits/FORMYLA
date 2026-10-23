#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: Добавление поля subtopic в таблицу adaptive_tasks
и автоматическая классификация существующих задач по подтемам.

Запуск: python migrations/add_subtopic_field.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app
from models import db, AdaptiveTask
from sqlalchemy import text
from services.topic_taxonomy import SUBTOPICS, get_subtopics_for_topic
import random


def check_column_exists():
    """Проверяет, существует ли поле subtopic."""
    with app.app_context():
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('adaptive_tasks')]
        return 'subtopic' in columns


def add_subtopic_column():
    """Добавляет поле subtopic в таблицу adaptive_tasks."""
    with app.app_context():
        if check_column_exists():
            print("[INFO] Поле subtopic уже существует.")
            return True
        
        print("[INFO] Добавление поля subtopic...")
        try:
            db.session.execute(text(
                "ALTER TABLE adaptive_tasks ADD COLUMN subtopic VARCHAR(100)"
            ))
            db.session.commit()
            print("[OK] Поле subtopic добавлено!")
            return True
        except Exception as e:
            print(f"[ERROR] Ошибка: {e}")
            db.session.rollback()
            return False


def auto_classify_tasks():
    """
    Автоматически классифицирует задачи по подтемам.
    Использует детерминированное распределение на основе ID задачи.
    """
    with app.app_context():
        # Получаем задачи без subtopic
        tasks_without_subtopic = AdaptiveTask.query.filter(
            AdaptiveTask.subtopic == None
        ).all()
        
        print(f"\n[INFO] Задач без subtopic: {len(tasks_without_subtopic)}")
        
        if not tasks_without_subtopic:
            print("[OK] Все задачи уже имеют subtopic!")
            return
        
        classified = 0
        skipped = 0
        
        for task in tasks_without_subtopic:
            subtopics = get_subtopics_for_topic(task.topic)
            
            if not subtopics:
                skipped += 1
                continue
            
            # Детерминированное распределение: task.id % len(subtopics)
            # Это гарантирует равномерное распределение по подтемам
            subtopic_idx = task.id % len(subtopics)
            task.subtopic = subtopics[subtopic_idx]
            classified += 1
        
        db.session.commit()
        
        print(f"[OK] Классифицировано: {classified}")
        print(f"[SKIP] Пропущено (нет подтем): {skipped}")
        
        # Статистика по подтемам
        print("\n[STATS] Распределение по подтемам (топ-20):")
        from sqlalchemy import func
        subtopic_stats = db.session.query(
            AdaptiveTask.topic,
            AdaptiveTask.subtopic,
            func.count(AdaptiveTask.id)
        ).group_by(
            AdaptiveTask.topic,
            AdaptiveTask.subtopic
        ).order_by(
            AdaptiveTask.topic,
            AdaptiveTask.subtopic
        ).limit(20).all()
        
        for topic, subtopic, count in subtopic_stats:
            print(f"  {topic[:30]}.{subtopic}: {count}")


def verify_migration():
    """Проверяет результаты миграции."""
    with app.app_context():
        total = AdaptiveTask.query.count()
        with_subtopic = AdaptiveTask.query.filter(
            AdaptiveTask.subtopic != None
        ).count()
        without_subtopic = total - with_subtopic
        
        print(f"\n[VERIFY] Всего задач: {total}")
        print(f"[VERIFY] С subtopic: {with_subtopic} ({with_subtopic/total*100:.1f}%)")
        print(f"[VERIFY] Без subtopic: {without_subtopic}")
        
        # Проверка уникальности подтем в рамках темы
        from sqlalchemy import func
        unique_subtopics = db.session.query(
            AdaptiveTask.topic,
            func.count(AdaptiveTask.subtopic.distinct())
        ).group_by(AdaptiveTask.topic).all()
        
        print("\n[VERIFY] Уникальных подтем по темам:")
        for topic, count in unique_subtopics:
            print(f"  {topic[:40]}: {count} подтем")


def main():
    print("\n" + "="*70)
    print("МИГРАЦИЯ: Добавление поля subtopic в adaptive_tasks")
    print("="*70)
    
    # Шаг 1: Добавить колонку
    if not add_subtopic_column():
        print("[FATAL] Не удалось добавить колонку!")
        return
    
    # Шаг 2: Классифицировать задачи
    auto_classify_tasks()
    
    # Шаг 3: Проверить результаты
    verify_migration()
    
    print("\n" + "="*70)
    print("[DONE] Миграция завершена!")
    print("="*70)


if __name__ == "__main__":
    main()
