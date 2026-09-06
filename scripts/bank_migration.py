# -*- coding: utf-8 -*-
"""
scripts/bank_migration.py — создать таблицы daily_task_bank и bank_issues.

Банк задач дня наполняет человек заранее (132 подтемы x 4 уровня x 35 задач
= 18480 строк). Этот скрипт только создаёт пустую схему — никаких INSERT.

DDL переносимый: без PRAGMA, без AUTOINCREMENT, совместим с SQLite и
PostgreSQL. Идемпотентен: повторный запуск не падает и не дублирует объекты.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(ROOT, "instance", "formyla.db")
DEFAULT_URI = "sqlite:///" + DEFAULT_DB_PATH.replace("\\", "/")

TABLES = ("daily_task_bank", "bank_issues")

DDL_STATEMENTS = [
    # ── daily_task_bank: ровно 13 колонок ─────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS daily_task_bank (
        id INTEGER PRIMARY KEY,
        subtopic VARCHAR(200) NOT NULL,
        section VARCHAR(50) NOT NULL,
        level INTEGER NOT NULL,
        statement TEXT NOT NULL,
        answer TEXT,
        solution TEXT,
        svg_path VARCHAR(300),
        svg_aux_path VARCHAR(300),
        needs_figure BOOLEAN NOT NULL DEFAULT FALSE,
        source_model VARCHAR(50),
        position INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_daily_task_bank_subtopic_level ON daily_task_bank (subtopic, level)",
    "CREATE INDEX IF NOT EXISTS ix_daily_task_bank_level ON daily_task_bank (level)",
    "CREATE INDEX IF NOT EXISTS ix_daily_task_bank_needs_figure ON daily_task_bank (needs_figure)",
    # ── bank_issues ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS bank_issues (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        task_id INTEGER NOT NULL REFERENCES daily_task_bank(id),
        subtopic VARCHAR(200) NOT NULL,
        level INTEGER NOT NULL,
        issued_date DATE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT uq_bank_issue_user_task UNIQUE (user_id, task_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_bank_issues_user_issued_date ON bank_issues (user_id, issued_date)",
]


def _resolve_uri() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_URI)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _index_names(conn, dialect: str, table: str):
    """Список имён индексов/уникальных ограничений для таблицы."""
    if dialect == "postgresql":
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = :t ORDER BY indexname"),
            {"t": table},
        ).fetchall()
    else:
        # PRAGMA index_list returns (seq, name, unique, origin, partial).
        rows = conn.execute(text(f"PRAGMA index_list('{table}')")).fetchall()
        return [row[1] for row in rows]


def main() -> None:
    uri = _resolve_uri()
    engine = create_engine(uri)
    dialect = engine.dialect.name

    with engine.begin() as conn:
        for stmt in DDL_STATEMENTS:
            conn.execute(text(stmt))

    with engine.connect() as conn:
        print("=== bank_migration ===")
        print(f"dialect: {dialect}")
        for table in TABLES:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"table: {table}")
            print(f"  rows: {count}")
            print(f"  indexes: {_index_names(conn, dialect, table)}")
    engine.dispose()
    print("=== done ===")


if __name__ == "__main__":
    main()
