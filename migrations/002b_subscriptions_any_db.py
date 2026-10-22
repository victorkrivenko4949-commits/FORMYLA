#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Миграция 002b: таблицы subscriptions + usage_daily (и колонки users) —
для ЛЮБОЙ БД (SQLite и PostgreSQL). Идемпотентна: повторный запуск безопасен.

Зачем: migrations/002_add_subscriptions.py написан под sqlite3 (PRAGMA,
sqlite_master, путь formyla.db) и на PostgreSQL НЕ работает. Для PG это
единственный предусмотренный путь создать таблицы подписок.

Как выбирается БД: переменная окружения DATABASE_URL (как в app.py).
По умолчанию — SQLite <корень проекта>/instance/formyla.db (тот же путь,
что использует app.py).

Запуск:
    DATABASE_URL='postgresql+psycopg://user:pass@host/db' \
        python migrations/002b_subscriptions_any_db.py
    # или просто: python migrations/002b_subscriptions_any_db.py  (SQLite)

Проверено на: SQLite 3 и PostgreSQL 16 (psycopg3).
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import sqlalchemy as sa


def _database_url() -> str:
    """Та же нормализация и тот же дефолт, что в app.py:
    DATABASE_URL или <корень>/instance/formyla.db (НЕ <корень>/formyla.db —
    приложение ищет БД в instance/)."""
    default = 'sqlite:///' + os.path.join(
        PROJECT_ROOT, 'instance', 'formyla.db').replace('\\', '/')
    url = os.environ.get('DATABASE_URL', default)
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif url.startswith('postgresql://') and '+psycopg' not in url:
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    return url


def _table_exists(conn: sa.Connection, name: str) -> bool:
    return sa.inspect(conn).has_table(name)


def _columns(conn: sa.Connection, table: str) -> set[str]:
    try:
        return {c['name'] for c in sa.inspect(conn).get_columns(table)}
    except Exception:  # noqa: BLE001
        return set()


def migrate() -> int:
    url = _database_url()
    engine = sa.create_engine(url)
    is_pg = engine.dialect.name == 'postgresql'
    print('=' * 60)
    print(' Миграция 002b: subscriptions + usage_daily (любая БД)')
    print(f'   БД: {url.split("@")[-1] if is_pg else url}')
    print('=' * 60)

    with engine.begin() as conn:
        # ПРЕДПОСЫЛКА: таблица users должна существовать (в БД FORMYLA она
        # есть всегда; на пустой тестовой БД без users миграция завершится
        # ошибкой FK — это ожидаемо и честно, схему не ослабляем).
        # ── 1. Таблица subscriptions ────────────────────────────────────
        if not _table_exists(conn, 'subscriptions'):
            pk = ('id SERIAL PRIMARY KEY' if is_pg
                  else 'id INTEGER PRIMARY KEY AUTOINCREMENT')
            conn.execute(sa.text(f"""
                CREATE TABLE subscriptions (
                    {pk},
                    user_id INTEGER NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    payment_method TEXT,
                    payment_id TEXT,
                    amount_rub INTEGER,
                    is_trial INTEGER DEFAULT 0,
                    is_beta_access INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            print('[OK] Таблица subscriptions создана')
        else:
            print('[OK] Таблица subscriptions уже существует — пропускаем')

        # ── 2. Индексы subscriptions ────────────────────────────────────
        for ddl in (
            'CREATE INDEX IF NOT EXISTS idx_sub_user ON subscriptions(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_sub_status ON subscriptions(status)',
            'CREATE INDEX IF NOT EXISTS idx_sub_expires ON subscriptions(expires_at)',
        ):
            conn.execute(sa.text(ddl))
        print('[OK] Индексы subscriptions готовы')

        # ── 3. Таблица usage_daily ──────────────────────────────────────
        if not _table_exists(conn, 'usage_daily'):
            pk = ('id SERIAL PRIMARY KEY' if is_pg
                  else 'id INTEGER PRIMARY KEY AUTOINCREMENT')
            conn.execute(sa.text(f"""
                CREATE TABLE usage_daily (
                    {pk},
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    tasks_completed INTEGER DEFAULT 0,
                    ai_explanations_used INTEGER DEFAULT 0,
                    tokens_consumed INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    UNIQUE(user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            print('[OK] Таблица usage_daily создана')
        else:
            print('[OK] Таблица usage_daily уже существует — пропускаем')

        conn.execute(sa.text(
            'CREATE INDEX IF NOT EXISTS idx_usage_user_date '
            'ON usage_daily(user_id, date)'))
        print('[OK] Индекс usage_daily готов')

        # ── 4. Колонки users (только если таблица users существует) ────
        if _table_exists(conn, 'users'):
            cols = _columns(conn, 'users')
            if 'current_plan' not in cols:
                conn.execute(sa.text(
                    "ALTER TABLE users ADD COLUMN current_plan TEXT DEFAULT 'free'"))
                print('[OK] Колонка users.current_plan добавлена')
            else:
                print('[OK] users.current_plan уже есть')
            if 'plan_expires_at' not in cols:
                conn.execute(sa.text(
                    'ALTER TABLE users ADD COLUMN plan_expires_at TIMESTAMP'))
                print('[OK] Колонка users.plan_expires_at добавлена')
            else:
                print('[OK] users.plan_expires_at уже есть')
        else:
            print('[i] Таблицы users нет — колонки пропускаем')

    print('[OK] Миграция 002b завершена')
    return 0


if __name__ == '__main__':
    sys.exit(migrate())
