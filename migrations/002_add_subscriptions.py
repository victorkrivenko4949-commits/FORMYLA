# -*- coding: utf-8 -*-
"""
Migration 002: Free/Premium subscription system
Creates tables: subscriptions, usage_daily
Adds columns to users: current_plan, plan_expires_at

IDEMPOTENT: safe to run multiple times.
BACKUP: created automatically before migration.

Run:
    python migrations/002_add_subscriptions.py

Rollback:
    python migrations/002_add_subscriptions.py --rollback
"""

import sys
import os
import shutil
from datetime import datetime

# Fix Windows console encoding for emoji/unicode output
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def backup_database(db_path: str) -> str:
    """Создаёт бэкап БД перед миграцией. Возвращает путь к бэкапу."""
    backups_dir = os.path.join(os.path.dirname(db_path), 'backups')
    os.makedirs(backups_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'formyla_before_subscriptions_{timestamp}.db'
    backup_path = os.path.join(backups_dir, backup_name)

    shutil.copy2(db_path, backup_path)
    print(f'✅ Бэкап создан: {backup_path}')
    return backup_path


def column_exists(conn, table: str, column: str) -> bool:
    """Проверяет существование колонки через PRAGMA table_info."""
    cursor = conn.execute(f'PRAGMA table_info({table})')
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def table_exists(conn, table: str) -> bool:
    """Проверяет существование таблицы."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def migrate(db_path: str = None):
    """Выполнить миграцию."""
    import sqlite3

    if db_path is None:
        # Ищем formyla.db в корне проекта
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, 'formyla.db')

    if not os.path.exists(db_path):
        print(f'❌ БД не найдена: {db_path}')
        sys.exit(1)

    print('=' * 60)
    print('🔄 Миграция 002: Система подписок Free/Premium')
    print(f'   БД: {db_path}')
    print('=' * 60)

    # 1. Бэкап
    backup_path = backup_database(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA journal_mode=WAL')  # Безопаснее для параллельного доступа
    conn.execute('PRAGMA foreign_keys=ON')

    try:
        # ── 2. Таблица subscriptions ──────────────────────────────────────
        if not table_exists(conn, 'subscriptions'):
            print('🔄 Создаём таблицу subscriptions...')
            conn.execute("""
                CREATE TABLE subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            """)
            print('✅ Таблица subscriptions создана')
        else:
            print('✅ Таблица subscriptions уже существует — пропускаем')

        # ── 3. Индексы на subscriptions ───────────────────────────────────
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sub_user
                ON subscriptions(user_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sub_status
                ON subscriptions(status)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sub_expires
                ON subscriptions(expires_at)
        """)
        print('✅ Индексы subscriptions готовы')

        # ── 4. Таблица usage_daily ────────────────────────────────────────
        if not table_exists(conn, 'usage_daily'):
            print('🔄 Создаём таблицу usage_daily...')
            conn.execute("""
                CREATE TABLE usage_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    tasks_completed INTEGER DEFAULT 0,
                    ai_explanations_used INTEGER DEFAULT 0,
                    tokens_consumed INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0,
                    UNIQUE(user_id, date),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            print('✅ Таблица usage_daily создана')
        else:
            print('✅ Таблица usage_daily уже существует — пропускаем')

        # ── 5. Индекс на usage_daily ──────────────────────────────────────
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_user_date
                ON usage_daily(user_id, date)
        """)
        print('✅ Индекс usage_daily готов')

        # ── 6. ALTER TABLE users: current_plan ────────────────────────────
        if not column_exists(conn, 'users', 'current_plan'):
            print('🔄 Добавляем колонку users.current_plan...')
            conn.execute(
                "ALTER TABLE users ADD COLUMN current_plan TEXT DEFAULT 'free'"
            )
            print('✅ Колонка current_plan добавлена')
        else:
            print('✅ Колонка current_plan уже существует — пропускаем')

        # ── 7. ALTER TABLE users: plan_expires_at ─────────────────────────
        if not column_exists(conn, 'users', 'plan_expires_at'):
            print('🔄 Добавляем колонку users.plan_expires_at...')
            conn.execute(
                'ALTER TABLE users ADD COLUMN plan_expires_at TIMESTAMP'
            )
            print('✅ Колонка plan_expires_at добавлена')
        else:
            print('✅ Колонка plan_expires_at уже существует — пропускаем')

        # ── 8. Инициализация Free-плана для существующих пользователей ────
        print('🔄 Инициализируем Free-план для существующих пользователей...')
        cursor = conn.execute("""
            INSERT OR IGNORE INTO subscriptions (user_id, plan, status, is_beta_access)
            SELECT id, 'free', 'active', 1 FROM users
            WHERE id NOT IN (SELECT user_id FROM subscriptions)
        """)
        inserted = cursor.rowcount
        print(f'✅ Добавлено Free-подписок: {inserted}')

        # ── 9. Обновить current_plan для существующих пользователей ───────
        conn.execute("""
            UPDATE users SET current_plan = 'free'
            WHERE current_plan IS NULL
        """)
        print('✅ current_plan обновлён для всех пользователей')

        conn.commit()
        print('=' * 60)
        print('✅ Миграция 002 завершена успешно!')
        print(f'   Бэкап сохранён: {backup_path}')
        print('=' * 60)

    except Exception as e:
        conn.rollback()
        print(f'❌ Ошибка миграции: {e}')
        print(f'   Бэкап доступен: {backup_path}')
        import traceback
        traceback.print_exc()
        raise
    finally:
        conn.close()


def rollback(db_path: str = None):
    """Откатить миграцию (удалить таблицы, колонки не удаляем — SQLite ограничение)."""
    import sqlite3

    if db_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(project_root, 'formyla.db')

    print('=' * 60)
    print('⚠️  ОТКАТ миграции 002: Система подписок')
    print('=' * 60)

    # Бэкап перед откатом тоже
    backup_database(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute('DROP TABLE IF EXISTS usage_daily')
        print('✅ Таблица usage_daily удалена')

        conn.execute('DROP TABLE IF EXISTS subscriptions')
        print('✅ Таблица subscriptions удалена')

        # Колонки current_plan и plan_expires_at из users удалить нельзя
        # в SQLite < 3.35. Они безвредны — просто обнуляем значения.
        conn.execute("UPDATE users SET current_plan = NULL, plan_expires_at = NULL")
        print('✅ Колонки current_plan/plan_expires_at обнулены (удалить нельзя в SQLite < 3.35)')

        conn.commit()
        print('✅ Откат завершён')
    except Exception as e:
        conn.rollback()
        print(f'❌ Ошибка отката: {e}')
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    # Parse db_path from args (first non-flag argument)
    _db_path = None
    for _arg in sys.argv[1:]:
        if not _arg.startswith('--'):
            _db_path = _arg
            break

    if '--rollback' in sys.argv:
        rollback(_db_path)
    else:
        migrate(_db_path)
