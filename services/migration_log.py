# -*- coding: utf-8 -*-
"""
services/migration_log.py — V11: Shared migration tracking for ad-hoc scripts.

Provides register_migration() and is_migration_applied() that every
ad-hoc migration script (scripts/*migration*.py) calls BEFORE executing
its SQL.  This ensures idempotent re-runs on both SQLite and PostgreSQL.

The SchemaMigrationLog table is declared in models.py and created via
Alembic or via db.create_all().  This module only reads/writes rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def is_migration_applied(migration_name: str) -> bool:
    """Return True if *migration_name* was already applied successfully.

    The name should be the exact filename of the migration script,
    e.g. ``'ch5_migration.py'`` or ``'d4_migration.py'``.
    """
    from models import SchemaMigrationLog

    try:
        existing = SchemaMigrationLog.query.filter_by(
            migration_name=migration_name
        ).first()
        return existing is not None
    except Exception:
        # Table may not exist yet during first-ever migration run.
        return False


def register_migration(migration_name: str) -> bool:
    """Record that *migration_name* has been applied.

    Returns True on success, False on failure (duplicate or error).
    """
    from models import db, SchemaMigrationLog

    try:
        entry = SchemaMigrationLog(
            migration_name=migration_name,
            applied_at=datetime.now(timezone.utc),
        )
        db.session.add(entry)
        db.session.commit()
        logger.info("[MIGRATION_LOG] registered %s", migration_name)
        return True
    except Exception:
        db.session.rollback()
        # If duplicate — it was already registered, treat as success.
        if is_migration_applied(migration_name):
            logger.info(
                "[MIGRATION_LOG] %s already registered (concurrent run?)",
                migration_name,
            )
            return True
        logger.exception("[MIGRATION_LOG] failed to register %s", migration_name)
        return False
