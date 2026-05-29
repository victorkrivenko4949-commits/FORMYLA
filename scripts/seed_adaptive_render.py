#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seed adaptive_tasks on Render PostgreSQL with the clean 8389-task dataset.

Connects DIRECTLY to the production PostgreSQL (via DATABASE_URL),
creates a minimal Flask app with SQLAlchemy, and re-imports all tasks
from adaptive_data/final/formyla_adaptive_final_polished.json.

This script does NOT depend on app.py being up-to-date on the server.
It only needs the JSON file, which is committed to git.

Usage
-----
    # Render Shell:
    python scripts/seed_adaptive_render.py --apply

    # Dry-run (only validate JSON, no DB writes):
    python scripts/seed_adaptive_render.py

    # Local with tunnel:
    DATABASE_URL=postgresql://user:pass@host/db python scripts/seed_adaptive_render.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# ── Paths ────────────────────────────────────────────────────────────────────
JSON_PATH = os.path.join(
    _PROJECT_ROOT, "adaptive_data", "final", "formyla_adaptive_final_polished.json"
)
# NOTE: dataset was re-cleaned 2026-05; 5 broken tasks dropped (8394 -> 8389).
EXPECTED_TOTAL = 8389

ALLOWED_SUBJECTS = {
    "algebra", "geometry", "number_theory", "combinatorics",
    "logic", "set_theory",
}
ALLOWED_GRADES = {5, 6, 7, 8, 9, 10, 11}
ALLOWED_LEVELS = {1, 2, 3, 4, 5, 6, 7, 8}

CRITERIA_1_PLACEHOLDER = (
    "Частичный прогресс: верно найден ключевой подход или промежуточный "
    "шаг, но решение не доведено до окончательного ответа."
)
CRITERIA_2_PLACEHOLDER = (
    "Полное решение с правильным ответом и обоснованием всех ключевых "
    "шагов."
)


# ── Flask + SQLAlchemy bootstrap ─────────────────────────────────────────────

def _build_app(database_url: str | None = None) -> tuple[Flask, SQLAlchemy]:
    """Create a minimal Flask+SQLAlchemy app connected to the given DB."""
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        print("❌ DATABASE_URL is not set (neither arg nor env).")
        print("   Usage: DATABASE_URL=postgresql://... python scripts/seed_adaptive_render.py")
        sys.exit(1)

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
    app.secret_key = "seed-script-local-only"

    from models import db as _db
    _db.init_app(app)
    with app.app_context():
        _db.create_all()

    print(f"✅ Connected to DB: {url.split('@')[0]}@***")
    return app, _db


# ── JSON loading & validation (same as import_polished_8394.py) ──────────────

def load_tasks() -> list[dict]:
    print(f"[load] {JSON_PATH}")
    with open(JSON_PATH, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and "tasks" in data:
        tasks = data["tasks"]
    elif isinstance(data, list):
        tasks = data
    else:
        raise ValueError("Unsupported JSON top-level type: " + type(data).__name__)
    if len(tasks) != EXPECTED_TOTAL:
        raise ValueError(
            f"Expected {EXPECTED_TOTAL} tasks, got {len(tasks)}"
        )
    print(f"[load] {len(tasks)} tasks read")
    return tasks


def validate_task(t: dict, idx: int) -> None:
    """Strict validation. Raises ValueError on first problem."""
    if not isinstance(t, dict):
        raise ValueError(f"#{idx}: not a dict")
    tid = t.get("id")
    for field in ("id", "grade", "level", "subject", "diagnostic_section",
                  "statement", "answer", "solution"):
        if field not in t:
            raise ValueError(f"#{idx} id={tid!r}: missing field {field!r}")
    if t.get("subject") not in ALLOWED_SUBJECTS:
        raise ValueError(
            f"#{idx} id={tid!r}: subject={t.get('subject')!r} "
            f"not in allowed {sorted(ALLOWED_SUBJECTS)}"
        )
    if t.get("grade") not in ALLOWED_GRADES:
        raise ValueError(
            f"#{idx} id={tid!r}: grade={t.get('grade')!r} "
            f"not in allowed {sorted(ALLOWED_GRADES)}"
        )
    if t.get("level") not in ALLOWED_LEVELS:
        raise ValueError(
            f"#{idx} id={tid!r}: level={t.get('level')!r} "
            f"not in allowed {sorted(ALLOWED_LEVELS)}"
        )
    if "domain" in t and t["domain"] != t["subject"]:
        raise ValueError(
            f"#{idx} id={tid!r}: subject={t.get('subject')!r} "
            f"!= domain={t.get('domain')!r}"
        )
    if t.get("topic") and t.get("topic") != t.get("diagnostic_section"):
        raise ValueError(f"#{idx} id={tid!r}: topic != diagnostic_section")
    for field in ("statement", "answer", "solution"):
        val = t.get(field)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"#{idx} id={tid!r}: empty {field}")


# ── DB operations (PostgreSQL via SQLAlchemy) ────────────────────────────────

def clear_old_rows(db: SQLAlchemy) -> int:
    """Delete all rows from task_solutions (FK) then adaptive_tasks."""
    models_module = sys.modules.get("models")
    AdaptiveTask = getattr(models_module, "AdaptiveTask", None)
    TaskSolution = getattr(models_module, "TaskSolution", None)

    n_sol = 0
    n_task = 0

    if TaskSolution is not None:
        n_sol = db.session.query(TaskSolution).count()
        if n_sol:
            print(f"[clear] task_solutions has {n_sol} rows -> deleting (FK)")
            db.session.query(TaskSolution).delete()
            db.session.commit()

    if AdaptiveTask is not None:
        n_task = db.session.query(AdaptiveTask).count()
        db.session.query(AdaptiveTask).delete()
        db.session.commit()

    # Reset PostgreSQL sequence for adaptive_tasks id
    db.session.execute(text("ALTER SEQUENCE adaptive_tasks_id_seq RESTART WITH 1"))
    db.session.commit()

    print(f"[clear] removed {n_task} old rows from adaptive_tasks")
    return n_task


def insert_new_rows(db: SQLAlchemy, tasks: list[dict]) -> int:
    """Bulk-insert all tasks using SQLAlchemy ORM mappings."""
    from models import AdaptiveTask

    now = datetime.utcnow()
    BATCH_SIZE = 500
    inserted = 0
    total = len(tasks)

    for start_idx in range(0, total, BATCH_SIZE):
        batch = tasks[start_idx:start_idx + BATCH_SIZE]
        mappings = []
        for t in batch:
            mappings.append({
                "class_level": int(t["grade"]),
                "difficulty_level": int(t["level"]),
                "topic": (t.get("diagnostic_section") or t.get("topic") or "").strip(),
                "subtopic": None,
                "task_text": t["statement"],
                "solution": t["solution"],
                "criteria_1_point": CRITERIA_1_PLACEHOLDER,
                "criteria_2_points": CRITERIA_2_PLACEHOLDER,
                "correct_answer": t["answer"],
                "is_flagged": False,
                "reports_count": 0,
                "flagged_reason": None,
                "attempts_count": 0,
                "solves_count": 0,
                "actual_solve_rate": None,
                "suggested_level": None,
                "needs_reclassification": False,
                "last_calibrated_at": None,
                "created_at": now,
                "subject": t["subject"],
                "source_id": t["id"],
                "needs_review": False,
            })

        db.session.bulk_insert_mappings(AdaptiveTask, mappings)
        db.session.commit()
        inserted += len(batch)
        if inserted % 2000 == 0 or inserted == total:
            print(f"[insert] {inserted}/{total}")

    print(f"[insert] done — {inserted} rows inserted")
    return inserted


def verify_db(db: SQLAlchemy) -> None:
    """Verify row counts, unique source_ids, subject/grade/level distributions."""
    from models import AdaptiveTask

    total = db.session.query(AdaptiveTask).count()
    print(f"[verify] total: {total} (expected {EXPECTED_TOTAL})")
    assert total == EXPECTED_TOTAL, f"Expected {EXPECTED_TOTAL}, got {total}"

    # Unique source_id count via raw SQL for efficiency
    row = db.session.execute(
        text("SELECT COUNT(DISTINCT source_id) FROM adaptive_tasks")
    ).scalar()
    print(f"[verify] unique source_id: {row}")
    assert row == EXPECTED_TOTAL, "source_id duplicates!"

    # Subject distribution
    rows = db.session.execute(
        text("SELECT subject, COUNT(*) FROM adaptive_tasks GROUP BY subject")
    ).fetchall()
    print("[verify] by subject:")
    seen_subjects = set()
    for s, n in rows:
        print(f"    {s!r}: {n}")
        seen_subjects.add(s)
    assert seen_subjects.issubset(ALLOWED_SUBJECTS), (
        f"Unexpected subject(s): {seen_subjects - ALLOWED_SUBJECTS}"
    )

    # Grade distribution
    rows = db.session.execute(
        text("SELECT class_level, COUNT(*) FROM adaptive_tasks "
             "GROUP BY class_level ORDER BY class_level")
    ).fetchall()
    print("[verify] by class_level:")
    seen_grades = set()
    for g, n in rows:
        print(f"    {g}: {n}")
        seen_grades.add(g)
    assert seen_grades == ALLOWED_GRADES, (
        f"Grade mismatch: got {seen_grades}"
    )

    # Level distribution
    rows = db.session.execute(
        text("SELECT difficulty_level, COUNT(*) FROM adaptive_tasks "
             "GROUP BY difficulty_level ORDER BY difficulty_level")
    ).fetchall()
    print("[verify] by difficulty_level:")
    seen_levels = set()
    for lv, n in rows:
        print(f"    {lv}: {n}")
        seen_levels.add(lv)
    assert seen_levels == ALLOWED_LEVELS, (
        f"Level mismatch: got {seen_levels}"
    )

    # Empty text fields check
    bad = db.session.execute(
        text("SELECT COUNT(*) FROM adaptive_tasks "
             "WHERE task_text IS NULL OR task_text='' "
             "   OR solution IS NULL OR solution='' "
             "   OR correct_answer IS NULL OR correct_answer=''")
    ).scalar()
    print(f"[verify] rows with empty text fields: {bad}")
    assert bad == 0, "Empty text fields in DB"

    print("[verify] ALL CHECKS PASSED ✅")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Seed adaptive_tasks on Render PostgreSQL with clean 8389 tasks."
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="Actually wipe the table and insert. Without this flag, "
             "only pre-validate the JSON (dry-run, no DB writes)."
    )
    args = ap.parse_args()

    print("=" * 70)
    print("FORMYLA adaptive_tasks PostgreSQL seed (8389 tasks)")
    print(f"  source: {JSON_PATH}")
    print(f"  mode:   {'APPLY (writes to DB)' if args.apply else 'DRY-RUN (no DB writes)'}")
    print("=" * 70)

    # Phase 1: Load & validate JSON
    tasks = load_tasks()

    print("[validate] pre-validating every task...")
    for idx, t in enumerate(tasks):
        validate_task(t, idx)
    print(f"[validate] all {len(tasks)} tasks OK")

    if not args.apply:
        print("\n[dry-run] JSON is valid and would import cleanly.")
        print("[dry-run] To actually import: rerun with --apply")
        return

    # Phase 2: Connect to DB and apply
    app, db = _build_app()
    t0 = time.time()

    with app.app_context():
        clear_old_rows(db)
        insert_new_rows(db, tasks)
        verify_db(db)

    dt = time.time() - t0
    print(f"\n{'=' * 70}")
    print(f"✅ IMPORT COMPLETE in {dt:.1f}s")
    print(f"   {EXPECTED_TOTAL} tasks written to PostgreSQL")
    print("=" * 70)


if __name__ == "__main__":
    main()
