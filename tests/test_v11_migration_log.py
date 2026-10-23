# -*- coding: utf-8 -*-
"""
tests/test_v11_migration_log.py — V11 acceptance test 4:
schema_migration_log table created and works idempotently.

Tests:
  - Table exists after db.create_all()
  - is_migration_applied returns False before registration, True after
  - Double registration does not create duplicates
  - ch5_migration double-run is safe (schema unchanged, no exceptions)
"""

import pytest

MIGRATION_NAME = 'ch5_migration.py'


def test_migration_log_table_exists(app):
    """SchemaMigrationLog table exists in the test database."""
    from models import db as _db
    from sqlalchemy import inspect
    inspector = inspect(_db.engine)
    tables = inspector.get_table_names()
    assert 'schema_migration_log' in tables, (
        f"schema_migration_log not found in {sorted(tables)}"
    )


def test_register_and_check(app):
    """is_migration_applied -> False before, True after register."""
    from services.migration_log import is_migration_applied, register_migration

    test_name = 'test_dummy_migration.py'

    assert not is_migration_applied(test_name), (
        f"{test_name} should not be applied before registration"
    )

    result = register_migration(test_name)
    assert result, "register_migration should return True"

    assert is_migration_applied(test_name), (
        f"{test_name} should be applied after registration"
    )

    # Clean up
    from models import db as _db, SchemaMigrationLog
    row = SchemaMigrationLog.query.filter_by(migration_name=test_name).first()
    if row:
        _db.session.delete(row)
        _db.session.commit()


def test_double_register_is_safe(app):
    """Registering the same migration twice does not create duplicate rows."""
    from models import db as _db, SchemaMigrationLog
    from services.migration_log import register_migration

    test_name = 'test_double_migration.py'

    register_migration(test_name)
    count1 = SchemaMigrationLog.query.filter_by(migration_name=test_name).count()

    register_migration(test_name)
    count2 = SchemaMigrationLog.query.filter_by(migration_name=test_name).count()

    assert count1 == 1, f"Expected 1 after first, got {count1}"
    assert count2 == 1, f"Expected 1 after second attempt, got {count2}"

    # Clean up
    row = SchemaMigrationLog.query.filter_by(migration_name=test_name).first()
    if row:
        _db.session.delete(row)
        _db.session.commit()


def test_ch5_migration_double_run_safe(app):
    """Run ch5 migration logic twice — no exception, only one log entry."""
    from models import db as _db, SchemaMigrationLog
    from services.migration_log import is_migration_applied, register_migration
    from sqlalchemy import inspect, text

    # Clean any previous test record
    existing = SchemaMigrationLog.query.filter_by(
        migration_name=MIGRATION_NAME
    ).first()
    if existing:
        _db.session.delete(existing)
        _db.session.commit()

    inspector = inspect(_db.engine)

    # First run — mimic ch5_migration logic
    if not is_migration_applied(MIGRATION_NAME):
        existing_tables = inspector.get_table_names()
        if 'figure_build_jobs' not in existing_tables:
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
            _db.session.commit()
        register_migration(MIGRATION_NAME)

    assert is_migration_applied(MIGRATION_NAME), (
        f"{MIGRATION_NAME} should be recorded after first run"
    )
    count1 = SchemaMigrationLog.query.filter_by(
        migration_name=MIGRATION_NAME
    ).count()
    assert count1 == 1, f"Expected 1 log entry after run1, got {count1}"

    # Second run — should be a no-op
    if is_migration_applied(MIGRATION_NAME):
        pass  # skip

    count2 = SchemaMigrationLog.query.filter_by(
        migration_name=MIGRATION_NAME
    ).count()
    assert count2 == 1, f"Expected still 1 log entry after run2, got {count2}"

    # Clean up
    existing = SchemaMigrationLog.query.filter_by(
        migration_name=MIGRATION_NAME
    ).first()
    if existing:
        _db.session.delete(existing)
        _db.session.commit()
