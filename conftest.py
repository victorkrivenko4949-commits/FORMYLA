# -*- coding: utf-8 -*-
"""
Root conftest.py — FORMYLA test isolation layer (V10).

Pytest loads this conftest.py BEFORE collecting test files.
It creates a temp copy of the real database so tests never touch
instance/formyla.db.  The copy is deleted automatically when the
pytest process exits.

Each pytest session gets its own temp database.  No two test
files can contaminate each other.
"""

import atexit
import os
import shutil
import tempfile

import pytest

_TEMP_DB_PATH = None


def pytest_configure(config):
    """Create temp database copy and point DATABASE_URL at it.

    Runs BEFORE test modules are imported, so ``import app``
    inside test fixtures picks up the temp path.
    """
    global _TEMP_DB_PATH

    root = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(root, 'instance', 'formyla.db')

    if not os.path.exists(src):
        # No real database — tests will start with an empty one.
        # db.create_all() inside app startup handles schema creation.
        _TEMP_DB_PATH = os.path.join(
            tempfile.gettempdir(),
            f'formyla_test_{os.getpid()}.db'
        )
        os.environ['DATABASE_URL'] = 'sqlite:///' + _TEMP_DB_PATH.replace('\\', '/')
        print(f'[conftest] No real DB found — starting with empty DB: {_TEMP_DB_PATH}')
        return

    _TEMP_DB_PATH = os.path.join(
        tempfile.gettempdir(),
        f'formyla_test_{os.getpid()}.db'
    )
    shutil.copy2(src, _TEMP_DB_PATH)
    os.environ['DATABASE_URL'] = 'sqlite:///' + _TEMP_DB_PATH.replace('\\', '/')
    print(f'[conftest] Test DB copy created: {_TEMP_DB_PATH}')

    # Also copy WAL/SHM if they exist (SQLite journal files).
    for ext in ('-wal', '-shm'):
        wal_src = src + ext
        if os.path.exists(wal_src):
            try:
                shutil.copy2(wal_src, _TEMP_DB_PATH + ext)
            except OSError:
                pass


def _cleanup_temp_db():
    """Remove temp database and journal files."""
    global _TEMP_DB_PATH
    if _TEMP_DB_PATH:
        for path in (_TEMP_DB_PATH, _TEMP_DB_PATH + '-wal', _TEMP_DB_PATH + '-shm'):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


atexit.register(_cleanup_temp_db)


def pytest_unconfigure(config):
    """Clean up temp database when pytest finishes."""
    _cleanup_temp_db()
