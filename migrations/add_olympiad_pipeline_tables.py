#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблиц olympiad_variants и olympiad_tasks.

Запуск:
    python migrations/add_olympiad_pipeline_tables.py

Таблицы для нового 6-этапного пайплайна генерации олимпиадных задач:
- olympiad_variants — сгенерированный вариант (набор из 5 задач)
- olympiad_tasks    — одна задача в варианте

SQL (для ручного применения, если нужно):

    CREATE TABLE IF NOT EXISTS olympiad_variants (
        id              VARCHAR(36)  PRIMARY KEY,
        olympiad_slug   VARCHAR(100) NOT NULL,
        olympiad_title  VARCHAR(200),
        round_key       VARCHAR(50),
        round_title     VARCHAR(200),
        grade           INTEGER      NOT NULL,
        user_id         INTEGER      REFERENCES users(id),
        created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS ix_olympiad_variants_olympiad_slug
        ON olympiad_variants(olympiad_slug);
    CREATE INDEX IF NOT EXISTS ix_olympiad_variants_grade
        ON olympiad_variants(grade);
    CREATE INDEX IF NOT EXISTS ix_olympiad_variants_user_id
        ON olympiad_variants(user_id);

    CREATE TABLE IF NOT EXISTS olympiad_tasks (
        id              INTEGER      PRIMARY KEY AUTOINCREMENT,
        variant_id      VARCHAR(36)  NOT NULL
                        REFERENCES olympiad_variants(id) ON DELETE CASCADE,
        position        INTEGER      NOT NULL,
        text            TEXT         NOT NULL,
        original_text   TEXT,
        solution        TEXT,
        answer          VARCHAR(500),
        topic           VARCHAR(100),
        source_year     INTEGER,
        source_problem  INTEGER,
        author          VARCHAR(200),
        pipeline_version VARCHAR(10) DEFAULT '1.0',
        validated_at    DATETIME
    );

    CREATE INDEX IF NOT EXISTS ix_olympiad_tasks_variant_id
        ON olympiad_tasks(variant_id);
    CREATE INDEX IF NOT EXISTS ix_olympiad_tasks_topic
        ON olympiad_tasks(topic);
"""

import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_migration():
    """Создаёт таблицы olympiad_variants и olympiad_tasks если их нет."""
    from app import app
    from models import db, OlympiadVariant, OlympiadTask

    with app.app_context():
        # db.create_all() создаёт только отсутствующие таблицы
        db.create_all()

        # Проверяем что таблицы созданы
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        if 'olympiad_variants' in tables:
            cols = [c['name'] for c in inspector.get_columns('olympiad_variants')]
            print(f"✅ Таблица olympiad_variants создана. Колонки: {cols}")
        else:
            print("❌ Таблица olympiad_variants НЕ создана!")
            return False

        if 'olympiad_tasks' in tables:
            cols = [c['name'] for c in inspector.get_columns('olympiad_tasks')]
            print(f"✅ Таблица olympiad_tasks создана. Колонки: {cols}")
        else:
            print("❌ Таблица olympiad_tasks НЕ создана!")
            return False

        # Проверяем что OlympiadGenerationLog не пострадала
        if 'olympiad_generation_log' in tables:
            print("✅ Таблица olympiad_generation_log на месте (не тронута)")
        else:
            print("⚠️  Таблица olympiad_generation_log отсутствует (не наша проблема)")

        print("\n🎉 Миграция завершена успешно!")
        return True


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
