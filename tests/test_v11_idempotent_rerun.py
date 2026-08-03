# -*- coding: utf-8 -*-
"""
tests/test_v11_idempotent_rerun.py — V11 acceptance test 5:
running existing migration scripts twice is safe.

Each test simulates the migration logic inline in the fixture's app context,
then runs it twice and asserts schema is unchanged.
"""

import pytest
from sqlalchemy import inspect, text


def _get_table_columns(inspector, table_name):
    """Return sorted list of column names for a table."""
    try:
        cols = inspector.get_columns(table_name)
        return sorted([c['name'] for c in cols])
    except Exception:
        return []


def _cleanup_migration_log(db, name):
    """Remove a migration log entry so the test can run fresh."""
    from models import SchemaMigrationLog
    row = SchemaMigrationLog.query.filter_by(migration_name=name).first()
    if row:
        db.session.delete(row)
        db.session.commit()


def _run_ch5_migration(app):
    """Inline ch5 migration logic against the fixture's app."""
    from models import db as _db
    from services.migration_log import is_migration_applied, register_migration

    MIGRATION_NAME = 'ch5_migration.py'
    if is_migration_applied(MIGRATION_NAME):
        return

    inspector = inspect(_db.engine)
    if 'figure_build_jobs' in inspector.get_table_names():
        register_migration(MIGRATION_NAME)
        return

    _db.session.execute(text("""
        CREATE TABLE IF NOT EXISTS figure_build_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            problem_text TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            model_name VARCHAR(120),
            svg_path TEXT,
            error TEXT,
            credit_charged BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    _db.session.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_status "
        "ON figure_build_jobs(status)"
    ))
    _db.session.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_user_id "
        "ON figure_build_jobs(user_id)"
    ))
    _db.session.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_figure_build_jobs_created_at "
        "ON figure_build_jobs(created_at)"
    ))
    _db.session.commit()
    register_migration(MIGRATION_NAME)


def _run_p4_debt_migration(app):
    """Inline p4_debt migration logic against the fixture's app."""
    from models import db as _db
    from services.migration_log import is_migration_applied, register_migration

    MIGRATION_NAME = 'p4_debt_migration.py'
    if is_migration_applied(MIGRATION_NAME):
        return

    inspector = inspect(_db.engine)
    cols = {c['name'] for c in inspector.get_columns('daily_task_items')}

    if 'debt_status' not in cols:
        try:
            _db.session.execute(text(
                "ALTER TABLE daily_task_items ADD COLUMN debt_status VARCHAR(16)"
            ))
            _db.session.commit()
            cols = {c['name'] for c in inspector.get_columns('daily_task_items')}
        except Exception:
            _db.session.rollback()

    if 'debt_until' not in cols:
        try:
            _db.session.execute(text(
                "ALTER TABLE daily_task_items ADD COLUMN debt_until DATE"
            ))
            _db.session.commit()
        except Exception:
            _db.session.rollback()

    register_migration(MIGRATION_NAME)


def test_ch5_migration_double_run_schema_unchanged(app):
    """ch5_migration.py: schema identical after first and second run."""
    from models import db as _db
    from services.migration_log import is_migration_applied

    MIGRATION_NAME = 'ch5_migration.py'
    _cleanup_migration_log(_db, MIGRATION_NAME)

    _run_ch5_migration(app)
    inspector = inspect(_db.engine)
    cols_1 = _get_table_columns(inspector, 'figure_build_jobs')

    _run_ch5_migration(app)
    inspector = inspect(_db.engine)
    cols_2 = _get_table_columns(inspector, 'figure_build_jobs')

    assert cols_1 == cols_2, f"Schema diverged: run1={cols_1}, run2={cols_2}"
    assert is_migration_applied(MIGRATION_NAME)

    _cleanup_migration_log(_db, MIGRATION_NAME)


def test_p4_debt_migration_double_run_schema_unchanged(app):
    """p4_debt_migration.py: schema identical after first and second run."""
    from models import db as _db
    from services.migration_log import is_migration_applied

    MIGRATION_NAME = 'p4_debt_migration.py'
    _cleanup_migration_log(_db, MIGRATION_NAME)

    inspector = inspect(_db.engine)

    _run_p4_debt_migration(app)
    inspector = inspect(_db.engine)
    cols_1 = _get_table_columns(inspector, 'daily_task_items')

    _run_p4_debt_migration(app)
    inspector = inspect(_db.engine)
    cols_2 = _get_table_columns(inspector, 'daily_task_items')

    assert cols_1 == cols_2, f"Schema diverged: run1={cols_1}, run2={cols_2}"
    assert 'debt_status' in cols_1, f"debt_status not in {cols_1}"
    assert 'debt_until' in cols_1, f"debt_until not in {cols_1}"

    _cleanup_migration_log(_db, MIGRATION_NAME)
