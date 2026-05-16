# -*- coding: utf-8 -*-
"""Миграция: создание таблиц раздела «Олимпиады» (/olympiads/*).

Создаёт 6 таблиц:
    * olympiad_probniks
    * olympiad_tasks
    * olympiad_theory
    * olympiad_probnik_theory
    * olympiad_task_attempts
    * olympiad_stage_attempts

Принцип ровно тот же, что у остальных миграций в этой папке
(см. `add_prep_plans.py`): импортируем модели + Flask-app, открываем
`app_context()` и зовём `db.create_all()`.  Метод идемпотентен — таблицы
не пересоздаются, если уже существуют.

Запуск:
    python migrations/add_olympiad_section.py

Возвращает exit-код 0 при успехе и 1 при ошибке (для CI / Render-команд).
"""

import os
import sys

# Делаем корень проекта импортируемым, когда скрипт вызывают
# `python migrations/add_olympiad_section.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Сначала загружаем основной набор моделей (User, …) — он создаёт `db`.
# Потом импортируем модели раздела «Олимпиады», чтобы они зарегистрировались
# в этом же `db.metadata` до вызова `create_all()`.
from models import db  # noqa: E402
from models_olympiad import (  # noqa: E402  (regs new models on import)
    Probnik,
    OlympiadTask,
    TheoryBlock,
    ProbnikTheory,
    TaskAttempt,
    StageAttempt,
)
from app import app  # noqa: E402

# Список имён таблиц для финальной проверки.
EXPECTED_TABLES = [
    Probnik.__tablename__,
    OlympiadTask.__tablename__,
    TheoryBlock.__tablename__,
    ProbnikTheory.__tablename__,
    TaskAttempt.__tablename__,
    StageAttempt.__tablename__,
]


def migrate() -> int:
    """Создать таблицы раздела «Олимпиады». Возвращает 0/1 как exit-код."""
    with app.app_context():
        print("🔄 Миграция: создание таблиц раздела «Олимпиады»…")
        try:
            db.create_all()
        except Exception as exc:  # pragma: no cover - инфраструктурное
            print(f"❌ Ошибка create_all(): {exc!r}")
            db.session.rollback()
            return 1

        # Контрольная проверка: SQLAlchemy создал все ожидаемые таблицы.
        inspector = db.inspect(db.engine)
        existing = set(inspector.get_table_names())
        missing = [t for t in EXPECTED_TABLES if t not in existing]
        if missing:
            print(f"❌ Таблицы НЕ созданы: {missing}")
            return 1

        print("✅ Все таблицы раздела «Олимпиады» на месте:")
        for t in EXPECTED_TABLES:
            print(f"   • {t}")
        return 0


if __name__ == '__main__':
    sys.exit(migrate())
