# -*- coding: utf-8 -*-
"""Importer for the «Olympiads» section data files.

Reads three JSON files, validates them with Pydantic, and upserts the rows
into the database under a single transaction.

Usage:
    python scripts/import_olympiad.py \\
        --probniks data/olympiads/vsosh_9_2027_probniks.json \\
        --tasks    data/olympiads/vsosh_9_2027_tasks.json \\
        --theory   data/olympiads/vsosh_9_2027_theory.json

Optional flags:
    --reset --confirm  Delete ALL data from the 6 olympiad tables first.
    --dry-run          Validate JSON but do not write to DB.

Exit codes:
    0  success
    1  validation or DB error
    2  bad CLI args
    3  refused to reset without --confirm

Idempotent: re-running on the same files updates existing rows
(matched by `code` / `method_code`) instead of inserting duplicates.
For Probnik tasks: existing rows for the probnik are deleted and
re-inserted, so the file is treated as the source of truth.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

# Make project root importable when run as `python scripts/import_olympiad.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError  # noqa: E402

from app import app  # noqa: E402  (brings Flask app + db init)
from models import db  # noqa: E402
from models_olympiad import (  # noqa: E402
    Probnik,
    OlympiadTask,
    TheoryBlock,
    ProbnikTheory,
    TaskAttempt,
    StageAttempt,
)
from schemas.olympiad import (  # noqa: E402
    ProbnikSchema,
    TaskSchema,
    TheoryBlockSchema,
)


# ─── JSON loading ──────────────────────────────────────────────────────────────

def _load_json_list(path: str) -> List[dict]:
    """Load a JSON file expected to be a list of objects."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"JSON file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: top-level JSON must be a list, got {type(data).__name__}")
    return data


def _validate_each(items: List[dict], schema_cls, label: str) -> list:
    """Validate every dict against a Pydantic schema, accumulate errors."""
    parsed = []
    errors: List[str] = []
    for i, raw in enumerate(items):
        try:
            parsed.append(schema_cls.model_validate(raw))
        except ValidationError as e:
            errors.append(f"{label}[{i}]: {e}")
    if errors:
        msg = "\n\n".join(errors)
        raise ValueError(f"Validation failed for {len(errors)}/{len(items)} {label}:\n{msg}")
    return parsed


# ─── Upsert helpers ────────────────────────────────────────────────────────────

def _upsert_theory(items) -> Tuple[int, int]:
    """Upsert TheoryBlock-s by `method_code`. Returns (created, updated)."""
    created = updated = 0
    for item in items:
        row = TheoryBlock.query.filter_by(method_code=item.method_code).first()
        if row is None:
            row = TheoryBlock(method_code=item.method_code)
            db.session.add(row)
            created += 1
        else:
            updated += 1
        row.method_name = item.method_name
        row.section = item.section
        row.definition_md = item.definition_md
        row.main_theorems_md = item.main_theorems_md
        row.typical_techniques_md = item.typical_techniques_md
        row.triggers_md = item.triggers_md
        row.worked_example_md = item.worked_example_md
        row.pitfalls_md = item.pitfalls_md
        row.related_methods = list(item.related_methods) if item.related_methods else []
    db.session.flush()
    return created, updated


def _upsert_probniks(items) -> Tuple[Dict[str, int], int, int]:
    """Upsert Probnik-s by `code`. Returns (code -> id mapping, created, updated)."""
    created = updated = 0
    code_to_id: Dict[str, int] = {}
    for item in items:
        row = Probnik.query.filter_by(code=item.code).first()
        if row is None:
            row = Probnik(code=item.code)
            db.session.add(row)
            created += 1
        else:
            updated += 1
        row.type = item.type
        row.number = item.number
        row.title = item.title
        row.description = item.description
        row.competition = item.competition
        row.grade = item.grade
        row.season_year = item.season_year
        row.duration_minutes = item.duration_minutes
        row.max_score = item.max_score
        row.threshold_prize = item.threshold_prize
        row.threshold_winner = item.threshold_winner
        row.sort_order = item.sort_order
        row.is_published = item.is_published
        db.session.flush()
        code_to_id[item.code] = row.id

        # Replace theory links wholesale — the file is the source of truth.
        ProbnikTheory.query.filter_by(probnik_id=row.id).delete()
        if item.theory:
            for link in item.theory:
                theory = TheoryBlock.query.filter_by(method_code=link.method_code).first()
                if theory is None:
                    raise ValueError(
                        f"Probnik {item.code!r} references unknown theory "
                        f"method_code {link.method_code!r}. "
                        f"Did you forget to import theory.json first?"
                    )
                db.session.add(ProbnikTheory(
                    probnik_id=row.id,
                    theory_block_id=theory.id,
                    display_order=link.order,
                ))
        db.session.flush()
    return code_to_id, created, updated


def _replace_tasks(items, probnik_code_to_id: Dict[str, int]) -> Tuple[int, int]:
    """For each probnik, delete-and-insert its tasks.

    We *replace* rather than upsert because the file is the source of truth:
    if a task was removed from JSON, it should disappear from DB.

    Returns (deleted, inserted).
    """
    # Group input tasks by probnik_code.
    grouped: Dict[str, list] = {}
    for t in items:
        grouped.setdefault(t.probnik_code, []).append(t)

    # Sanity: every probnik_code must exist.
    unknown = [code for code in grouped if code not in probnik_code_to_id]
    if unknown:
        raise ValueError(
            f"Tasks reference unknown probnik_code(s): {unknown}. "
            f"Did you forget to add them to probniks.json?"
        )

    deleted = inserted = 0
    for code, tasks in grouped.items():
        probnik_id = probnik_code_to_id[code]
        # Wipe out existing tasks for this probnik.
        old_count = OlympiadTask.query.filter_by(probnik_id=probnik_id).count()
        if old_count:
            OlympiadTask.query.filter_by(probnik_id=probnik_id).delete()
            deleted += old_count
        for t in tasks:
            db.session.add(OlympiadTask(
                probnik_id=probnik_id,
                number=t.number,
                sort_order=t.sort_order,
                difficulty=t.difficulty,
                method_primary=t.method_primary,
                method_secondary=t.method_secondary,
                condition_md=t.condition_md,
                idea_md=t.idea_md,
                solution_md=t.solution_md,
                answer=t.answer,
                source_prototype=t.source_prototype,
                estimated_minutes=t.estimated_minutes,
                max_score=t.max_score,
            ))
            inserted += 1
    db.session.flush()
    return deleted, inserted


def _reset_all() -> None:
    """Wipe ALL rows from olympiad tables. Caller must confirm."""
    # Order matters: children before parents.
    StageAttempt.query.delete()
    TaskAttempt.query.delete()
    OlympiadTask.query.delete()
    ProbnikTheory.query.delete()
    Probnik.query.delete()
    TheoryBlock.query.delete()
    db.session.flush()


# ─── Driver ────────────────────────────────────────────────────────────────────

def import_data(probniks_path: str, tasks_path: str, theory_path: str,
                dry_run: bool = False, reset: bool = False) -> dict:
    """Main entrypoint. Returns a stats dict.

    Order of operations is strict:
        1. theory   — referenced by probnik.theory links.
        2. probniks — referenced by tasks (via probnik_code).
        3. tasks    — leaf data.
    """
    print(f"theory  : {theory_path}")
    print(f"probniks: {probniks_path}")
    print(f"tasks   : {tasks_path}")

    raw_theory = _load_json_list(theory_path)
    raw_probniks = _load_json_list(probniks_path)
    raw_tasks = _load_json_list(tasks_path)

    print(f"\nValidating {len(raw_theory)} theory + "
          f"{len(raw_probniks)} probniks + {len(raw_tasks)} tasks…")

    theory_items = _validate_each(raw_theory, TheoryBlockSchema, "theory")
    probnik_items = _validate_each(raw_probniks, ProbnikSchema, "probniks")
    task_items = _validate_each(raw_tasks, TaskSchema, "tasks")

    print("JSON validation OK")

    if dry_run:
        print("\n--dry-run: skipping DB writes.")
        return {
            'dry_run': True,
            'theory_items': len(theory_items),
            'probnik_items': len(probnik_items),
            'task_items': len(task_items),
        }

    with app.app_context():
        if reset:
            print("\n--reset: wiping all olympiad tables…")
            _reset_all()

        # Order: theory -> probniks (with theory links) -> tasks.
        theory_created, theory_updated = _upsert_theory(theory_items)
        probnik_code_to_id, p_created, p_updated = _upsert_probniks(probnik_items)
        tasks_deleted, tasks_inserted = _replace_tasks(task_items, probnik_code_to_id)

        db.session.commit()

    stats = {
        'theory':   {'created': theory_created, 'updated': theory_updated},
        'probniks': {'created': p_created, 'updated': p_updated},
        'tasks':    {'deleted_then_inserted': tasks_deleted, 'inserted': tasks_inserted},
    }
    print("\nImport complete:")
    for section, counts in stats.items():
        print(f"   {section:10s}: {counts}")
    return stats


# ─── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='import_olympiad',
        description="Import «Olympiads» section data from 3 JSON files.",
    )
    p.add_argument('--probniks', required=True, help='Path to probniks.json')
    p.add_argument('--tasks',    required=True, help='Path to tasks.json')
    p.add_argument('--theory',   required=True, help='Path to theory.json')
    p.add_argument('--reset',    action='store_true',
                   help='Wipe all olympiad tables before import.')
    p.add_argument('--confirm',  action='store_true',
                   help='Required together with --reset (safety net).')
    p.add_argument('--dry-run',  action='store_true',
                   help='Validate JSON only; do not touch the DB.')
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    if args.reset and not args.confirm:
        print("ERROR: --reset requires --confirm to avoid accidental data loss.",
              file=sys.stderr)
        return 3

    try:
        import_data(
            probniks_path=args.probniks,
            tasks_path=args.tasks,
            theory_path=args.theory,
            dry_run=args.dry_run,
            reset=args.reset,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # pragma: no cover  (defensive)
        print(f"ERROR: Unexpected error: {e!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
