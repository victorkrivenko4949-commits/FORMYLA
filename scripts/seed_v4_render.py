#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone VsOsh-9-2027 v4 seed script.

Connects DIRECTLY to the production PostgreSQL (via DATABASE_URL),
creates a minimal Flask app with SQLAlchemy, and runs the same
run_v4_force_import() logic that normally runs on boot.

Intended use cases
------------------
1. Render Shell:   DATABASE_URL=<...> python scripts/seed_v4_render.py
2. Local (tunnel): DATABASE_URL=postgresql://... python scripts/seed_v4_render.py

This script does NOT depend on app.py being up-to-date on the server.
It only needs the data/olympiads/ fixture files, which are committed to git.
"""

from __future__ import annotations

import os
import sys
import time

# ── Bootstrap: ensure we can import project modules ──────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


def _build_app(database_url: str | None = None) -> Flask:
    """Create a minimal Flask+SQLAlchemy app connected to the given DB."""
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL is not set (neither arg nor env).")
        print("   Usage: DATABASE_URL=postgresql://... python scripts/seed_v4_render.py")
        sys.exit(1)

    # Strip any existing +psycopg scheme — we add our own below
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 2,
        "max_overflow": 2,
        "pool_timeout": 10,
    }
    app.secret_key = "seed-script-local-only"  # not used but required by Flask

    # ── Import real db object and olympiad models ────────────────────────
    # models.py defines `db = SQLAlchemy()` at module level, and at the
    # bottom re-exports Probnik, OlympiadTask, TheoryBlock, ProbnikTheory.
    # We import AFTER creating `app` to avoid circular-init confusion, then
    # call db.init_app(app) to wire everything up.
    from models import db as _db

    _db.init_app(app)
    with app.app_context():
        _db.create_all()

    print(f"✅ Connected to DB: {url.split('@')[0]}@***")
    return app, _db


def seed_v4(database_url: str | None = None) -> None:
    """Build app, connect DB, run v4 force-import, report results."""
    app, db = _build_app(database_url)

    from services.olympiad_v4_force import run_v4_force_import

    t0 = time.time()
    print("\n🚀 Running run_v4_force_import() …")
    sys.stdout.flush()

    run_v4_force_import(app, db)

    dt = time.time() - t0
    print(f"\n✅ Seed completed in {dt:.1f}s")

    # Quick verification: count rows in DB
    with app.app_context():
        from models_olympiad import Probnik, OlympiadTask, TheoryBlock

        p_count = Probnik.query.count()
        t_count = OlympiadTask.query.count()
        th_count = TheoryBlock.query.count()
        print(f"\n📊 Verification:")
        print(f"   TheoryBlock:  {th_count} rows")
        print(f"   Probnik:      {p_count} rows")
        print(f"   OlympiadTask: {t_count} rows")

        # Check specifically for vsosh-9-2027 probniks
        vsosh_probniki = Probnik.query.filter(
            Probnik.competition == "ВсОШ",
            Probnik.grade == 9,
            Probnik.season_year == 2027,
        ).all()
        print(f"   VsOsh-9-2027 probniks: {len(vsosh_probniki)}")
        for p in vsosh_probniki:
            task_cnt = OlympiadTask.query.filter_by(probnik_id=p.id).count()
            print(f"     · {p.code}: {p.title} — {task_cnt} tasks, published={p.is_published}")


if __name__ == "__main__":
    # Allow passing DATABASE_URL as CLI argument
    url_from_arg = sys.argv[1] if len(sys.argv) > 1 else None
    seed_v4(url_from_arg)
