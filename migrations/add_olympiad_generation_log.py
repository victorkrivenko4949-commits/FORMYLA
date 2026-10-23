#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблицы olympiad_generation_log.

Запуск:
    python migrations/add_olympiad_generation_log.py

Таблица хранит лог каждой генерации олимпиадной задачи для аналитики:
- Сколько задач прошло с первой попытки
- Сколько перегенерировано
- Сколько отклонено
- По каким олимпиадам/этапам/классам чаще всего генерируют

Аналитический запрос после 100+ генераций:
    SELECT
        olympiad_slug,
        round_key,
        class_level,
        COUNT(*) as total,
        SUM(success) as successful,
        ROUND(SUM(success) * 100.0 / COUNT(*), 1) as success_rate_pct,
        ROUND(AVG(attempts), 2) as avg_attempts
    FROM olympiad_generation_log
    GROUP BY olympiad_slug, round_key, class_level
    ORDER BY total DESC;
"""

import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    """Создаёт таблицу olympiad_generation_log если её нет."""
    from app import app
    from models import db, OlympiadGenerationLog

    with app.app_context():
        # db.create_all() создаёт только отсутствующие таблицы
        db.create_all()

        # Проверяем что таблица создана
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        if 'olympiad_generation_log' in tables:
            print("[OK] Таблица olympiad_generation_log создана (или уже существовала)")
            cols = [c['name'] for c in inspector.get_columns('olympiad_generation_log')]
            print(f"   Колонки: {', '.join(cols)}")
        else:
            print("[ERROR] Ошибка: таблица olympiad_generation_log не создана")
            sys.exit(1)


if __name__ == '__main__':
    print(" Запуск миграции: add_olympiad_generation_log")
    run_migration()
    print("[OK] Миграция завершена")
