#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция: создание таблиц для модуля «Куратор» (AI-наставник).

Таблицы (5 шт.):
  - student_diagnostics   — результаты входного тестирования (профиль ученика)
  - learning_plans         — персональные учебные планы (roadmap)
  - task_attempts          — попытки решения задач (история)
  - progress_log           — лог прогресса (ежедневные/еженедельные срезы)
  - task_bank              — банк задач (верифицированные задачи с подсказками)

Запуск:
    python migrations/add_curator_tables.py

Также экспортирует _ensure_curator_tables(), которая вызывается из app.py
при регистрации blueprint (auto-migration на старте).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_sql_statements(dialect_name):
    """Сгенерировать DDL под конкретный SQL-диалект.

    dialect_name — SQLAlchemy engine.dialect.name (например 'sqlite', 'postgresql').
    """
    is_pg = dialect_name == "postgresql"
    pk = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    dt = "TIMESTAMP" if is_pg else "DATETIME"
    bool_false = "FALSE" if is_pg else "0"

    statements = [
        # ─── student_diagnostics ──────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS student_diagnostics (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            session_id      VARCHAR(64),
            grade           INTEGER,
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            -- profile: JSON-объект с результатами по каждой теме
            -- {{
            --   "algebra": {{"pct": 45, "level": 1, "tasks_correct": 3, "tasks_total": 5}},
            --   "geometry": {{"pct": 70, "level": 2, ...}},
            --   "combinatorics": ...,
            --   "number_theory": ...,
            --   "logic": ...
            -- }}
            profile_json    TEXT,
            -- Общий уровень (0-100)
            overall_pct     INTEGER NOT NULL DEFAULT 0,
            -- Количество вопросов в тесте
            total_questions INTEGER NOT NULL DEFAULT 0,
            -- Правильных ответов
            correct_answers INTEGER NOT NULL DEFAULT 0,
            -- Дата начала теста
            started_at      {dt},
            -- Дата завершения
            completed_at    {dt},
            -- JSON: история вопросов (id вопроса, ответ, правильность, время)
            question_log    TEXT,
            -- AI-рекомендация (текст от DeepSeek)
            ai_summary      TEXT,
            created_at      {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_sd_user_id    ON student_diagnostics(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_sd_session_id ON student_diagnostics(session_id)",
        "CREATE INDEX IF NOT EXISTS ix_sd_status     ON student_diagnostics(status)",

        # ─── learning_plans ───────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS learning_plans (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            -- Название плана (например "Подготовка к ВсОШ 9 класс")
            title           VARCHAR(255),
            -- Цель (например "Победитель муниципального этапа")
            goal            TEXT,
            -- Тип: 'diagnostic' (создан после диагностики), 'manual'
            plan_type       VARCHAR(32) NOT NULL DEFAULT 'diagnostic',
            -- JSON: начальный профиль (копия из student_diagnostics)
            baseline_profile TEXT,
            -- Дата начала
            start_date      DATE,
            -- Дата целевой олимпиады (дедлайн)
            target_date     DATE,
            -- Название целевой олимпиады
            target_olympiad VARCHAR(255),
            -- Этап олимпиады (школьный, муниципальный, региональный, заключительный)
            target_stage    VARCHAR(64),
            -- Статус: active, paused, completed, archived
            status          VARCHAR(32) NOT NULL DEFAULT 'active',
            -- JSON: roadmap по неделям
            -- [{{"week": 1, "topics": [...], "goal": "...", "tasks_count": 5}}, ...]
            roadmap_json    TEXT,
            -- Текущий профиль (обновляется по мере прогресса)
            current_profile TEXT,
            -- Количество недель в плане
            total_weeks     INTEGER NOT NULL DEFAULT 0,
            -- Текущая неделя
            current_week    INTEGER NOT NULL DEFAULT 0,
            -- Приоритеты тем (JSON: список topic_key от слабой к сильной)
            topic_priorities TEXT,
            -- Дата создания
            created_at      {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP,
            -- Дата последнего обновления
            updated_at      {dt},
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_lp_user_id ON learning_plans(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_lp_status  ON learning_plans(status)",

        # ─── task_attempts ────────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS task_attempts (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            -- ID задачи (из AdaptiveTask или другой таблицы)
            task_id         INTEGER,
            -- Источник задачи: 'adaptive', 'daily_task', 'curator_plan', 'manual'
            task_source     VARCHAR(32) NOT NULL DEFAULT 'curator_plan',
            -- Тип задачи: 'diagnostic', 'practice', 'test', 'hint'
            task_type       VARCHAR(32) NOT NULL DEFAULT 'practice',
            -- ID плана обучения (если задача из плана)
            plan_id         INTEGER,
            -- Тема задачи
            topic           VARCHAR(100),
            -- Уровень сложности (1-8)
            difficulty      INTEGER,
            -- Ответ ученика
            user_answer     TEXT,
            -- Правильный ответ
            correct_answer  TEXT,
            -- Правильно/неправильно
            is_correct      BOOLEAN,
            -- Количество попыток на эту задачу
            attempts_count  INTEGER NOT NULL DEFAULT 1,
            -- Время на решение (секунды)
            time_spent_sec  INTEGER,
            -- Использовал подсказки: true/false
            used_hints      BOOLEAN NOT NULL DEFAULT {bool_false},
            -- Количество показанных подсказок
            hints_shown     INTEGER NOT NULL DEFAULT 0,
            -- Количество различных подсказок, которые ученик открыл
            hints_used      INTEGER NOT NULL DEFAULT 0,
            -- AI-фидбек (JSON от tutor)
            ai_feedback     TEXT,
            -- Оценка метода (от AI)
            method_score    FLOAT,
            -- Дата попытки
            attempted_at    {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (plan_id) REFERENCES learning_plans(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_ta_user_id     ON task_attempts(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_ta_task_id     ON task_attempts(task_id)",
        "CREATE INDEX IF NOT EXISTS ix_ta_plan_id     ON task_attempts(plan_id)",
        "CREATE INDEX IF NOT EXISTS ix_ta_topic       ON task_attempts(topic)",
        "CREATE INDEX IF NOT EXISTS ix_ta_attempted_at ON task_attempts(attempted_at)",

        # ─── progress_log ────────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS progress_log (
            id              {pk},
            user_id         INTEGER  NOT NULL,
            plan_id         INTEGER,
            -- Дата среза
            log_date        DATE NOT NULL,
            -- Тип лога: 'daily', 'weekly', 'session'
            log_type        VARCHAR(16) NOT NULL DEFAULT 'daily',
            -- JSON: профиль на момент среза (темы -> pct)
            profile_snapshot TEXT,
            -- Количество решённых задач за период
            tasks_solved    INTEGER NOT NULL DEFAULT 0,
            -- Количество задач всего
            tasks_total     INTEGER NOT NULL DEFAULT 0,
            -- Процент правильных
            accuracy_pct    FLOAT,
            -- Общее время (минуты)
            minutes_spent   FLOAT,
            -- Серия (streak) подряд идущих дней
            streak_days     INTEGER NOT NULL DEFAULT 0,
            -- Максимальная серия
            max_streak      INTEGER NOT NULL DEFAULT 0,
            -- Текущая неделя плана
            plan_week       INTEGER,
            -- Флаг: были ли "застревания" (низкий прогресс 3+ дня)
            is_stuck        BOOLEAN NOT NULL DEFAULT {bool_false},
            -- AI-совет (краткий)
            ai_advice       TEXT,
            -- Дата создания записи
            created_at      {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (plan_id) REFERENCES learning_plans(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pl_user_id  ON progress_log(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_pl_plan_id  ON progress_log(plan_id)",
        "CREATE INDEX IF NOT EXISTS ix_pl_log_date ON progress_log(log_date)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_pl_user_date_type ON progress_log(user_id, log_date, log_type)",

        # ─── task_bank ─────────────────────────────────────────────────────────
        f"""
        CREATE TABLE IF NOT EXISTS task_bank (
            id              {pk},
            -- Тема (algebra, geometry, combinatorics, number_theory, logic)
            topic           VARCHAR(64) NOT NULL,
            -- Подтема (например 'quadratic_equations', 'triangles')
            subtopic        VARCHAR(128),
            -- Уровень сложности (1–10)
            difficulty      INTEGER NOT NULL DEFAULT 5,
            -- Условие задачи (с LaTeX-разметкой $...$)
            statement       TEXT NOT NULL,
            -- Правильный ответ
            answer          TEXT NOT NULL,
            -- Эталонное решение
            solution        TEXT,
            -- JSON-массив подсказок (3 уровня)
            hints           TEXT,
            -- Источник задачи (например 'vsosh_2024', 'formyla')
            source          VARCHAR(128),
            -- JSON-массив тегов
            tags            TEXT,
            -- Дата создания
            created_at      {dt} NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_tb_topic      ON task_bank(topic)",
        "CREATE INDEX IF NOT EXISTS ix_tb_subtopic   ON task_bank(subtopic)",
        "CREATE INDEX IF NOT EXISTS ix_tb_difficulty ON task_bank(difficulty)",
    ]
    return statements


def _ensure_curator_tables() -> bool:
    """Создаёт таблицы Куратора, если их нет. Идемпотентно.

    Вызывается из app.py при регистрации blueprint (auto-migration).
    Поддерживает SQLite (локально) и PostgreSQL (Render).
    """
    from app import app
    from models import db
    from sqlalchemy import text, inspect

    with app.app_context():
        dialect = db.engine.dialect.name
        print(f"  [curator migration] dialect = {dialect}")
        statements = _build_sql_statements(dialect)

        for stmt in statements:
            try:
                db.session.execute(text(stmt))
            except Exception as e:
                db.session.rollback()
                print(f"  ❌ curator migration: failed on stmt: {e}")
                raise
        db.session.commit()

        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        ok = True
        for expected in ("student_diagnostics", "learning_plans", "task_attempts", "progress_log", "task_bank"):
            if expected in tables:
                cols = [c["name"] for c in inspector.get_columns(expected)]
                print(f"  ✅ {expected}: {len(cols)} колонок")
            else:
                print(f"  ❌ {expected} НЕ создана!")
                ok = False

        return ok


def run_migration() -> bool:
    """Запуск миграции с подробным выводом."""
    print("=" * 70)
    print("МИГРАЦИЯ: Curator Tables")
    print("=" * 70)
    success = _ensure_curator_tables()
    if success:
        print("\n🎉 Миграция Куратора завершена успешно!")
    else:
        print("\n❌ Миграция Куратора завершилась с ошибками")
    return success


if __name__ == "__main__":
    sys.exit(0 if run_migration() else 1)
