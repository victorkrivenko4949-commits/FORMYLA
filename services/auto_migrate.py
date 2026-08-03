# -*- coding: utf-8 -*-
"""Auto-migration: ensure database schema matches SQLAlchemy models.

Runs after all models have been imported and registered.
Compares the actual database schema (via SQLAlchemy inspector) with
the expected schema from SQLAlchemy model metadata, and:

1. Creates missing tables via ``db.create_all()``.
2. Adds missing columns to existing tables via ``ALTER TABLE ADD COLUMN``.
3. Never drops a table or column, never changes a column type.
4. Idempotent — safe to run on every application start.

Called from ``app.py`` after all blueprints and models are loaded.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def _column_type_for_dialect(col, dialect_name: str) -> str:
    """Convert a SQLAlchemy Column type to a dialect-specific SQL type string.

    Returns a string suitable for ``ALTER TABLE ... ADD COLUMN col TYPE``.
    """
    try:
        compiled = col.type.compile(dialect=getattr(col.type, 'dialect', None))
        return str(compiled)
    except Exception:
        pass

    # Fallback: use the Python type's __visit_name__ for common types.
    type_obj = col.type
    type_name = getattr(type_obj, '__visit_name__', None)

    if type_name is None:
        type_name = type(type_obj).__name__.lower()

    # Map common SQLAlchemy types to SQLite-compatible strings.
    type_map: Dict[str, str] = {
        'integer': 'INTEGER',
        'biginteger': 'INTEGER',
        'smallinteger': 'INTEGER',
        'bigint': 'INTEGER',
        'float': 'REAL',
        'numeric': 'REAL',
        'double': 'REAL',
        'double_precision': 'REAL',
        'string': 'VARCHAR',
        'text': 'TEXT',
        'unicode': 'VARCHAR',
        'unicodetext': 'TEXT',
        'boolean': 'BOOLEAN',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'time': 'TIME',
        'json': 'TEXT',
        'jsonb': 'TEXT',
        'interval': 'TEXT',
        'pickletype': 'TEXT',
        'largebinary': 'BLOB',
        'binary': 'BLOB',
        'enum': 'VARCHAR(255)',
    }

    result = type_map.get(type_name, 'TEXT')

    # Append length for String/VARCHAR types.
    if type_name in ('string', 'unicode'):
        length = getattr(type_obj, 'length', None)
        if length:
            result = f'VARCHAR({length})'

    # Append NOT NULL if the column is not nullable.
    if not col.nullable and col.default is None and not col.server_default and not col.primary_key:
        result += ' NOT NULL'

    # Append DEFAULT if there is a server_default.
    if col.server_default is not None:
        sd = col.server_default
        if hasattr(sd, 'arg'):
            arg = sd.arg
            if isinstance(arg, str):
                result += f" DEFAULT {arg}"
            elif isinstance(arg, (int, float)):
                result += f" DEFAULT {arg}"
            else:
                result += f" DEFAULT '{arg}'"

    return result


def _get_model_tables(db) -> Set[str]:
    """Return the set of table names defined in SQLAlchemy metadata."""
    return set(db.metadata.tables.keys())


def auto_migrate(app, db) -> Tuple[List[str], List[str]]:
    """Run automatic schema migration.

    Parameters
    ----------
    app : Flask app instance
    db : SQLAlchemy instance (flask_sqlalchemy.SQLAlchemy)

    Returns
    -------
    Tuple[List[str], List[str]]
        (created_tables, added_columns) lists for reporting.
    """
    created_tables: List[str] = []
    added_columns: List[str] = []

    with app.app_context():
        dialect_name = db.engine.dialect.name
        inspector = inspect(db.engine)
        existing_tables: Set[str] = set(inspector.get_table_names())

        # Step 1: Create missing tables.
        model_tables = _get_model_tables(db)
        missing_tables = model_tables - existing_tables
        if missing_tables:
            try:
                db.create_all()
                print(f"[AUTO-MIGRATE] Created missing tables: {sorted(missing_tables)}")
                created_tables.extend(sorted(missing_tables))
            except Exception as e:
                print(f"[AUTO-MIGRATE] create_all failed: {e}")
                return created_tables, added_columns

        # Step 2: Add missing columns to existing tables.
        # Re-read existing tables after possible create_all.
        existing_tables = set(inspector.get_table_names())

        for table_name in sorted(model_tables):
            if table_name not in existing_tables:
                # Should have been created above; skip if not.
                continue

            try:
                db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
            except Exception:
                continue

            model_table = db.metadata.tables.get(table_name)
            if model_table is None:
                continue

            for col in model_table.columns:
                col_name = str(col.name)

                if col_name in db_columns:
                    # Column exists — do NOT modify type.
                    continue

                # Column missing — add it.
                col_type_str = _column_type_for_dialect(col, dialect_name)

                # Build ALTER TABLE statement.
                if dialect_name == 'postgresql':
                    sql = (
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN IF NOT EXISTS {col_name} {col_type_str}"
                    )
                else:
                    sql = (
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {col_name} {col_type_str}"
                    )

                try:
                    db.session.execute(text(sql))
                    db.session.commit()
                    msg = f"{table_name}.{col_name} ({col_type_str})"
                    print(f"[AUTO-MIGRATE] + {msg}")
                    added_columns.append(msg)
                except Exception as e:
                    db.session.rollback()
                    print(f"[AUTO-MIGRATE] SKIP {table_name}.{col_name}: {e}")

    return created_tables, added_columns
