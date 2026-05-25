# -*- coding: utf-8 -*-
"""
One-shot prod migration: re-apply the VsOsh-9 2027 importer logic
on every Flask boot, idempotently, without going through Render Shell.

Why this exists
---------------
``services/olympiad_autoseed.py`` only seeds probniks/tasks if the
relevant tables are GLOBALLY empty. As soon as another competition
populates them, vsosh-9-2027 fixtures never load on Render, even when
fresh v4 JSON is committed. The classic fix is to ssh into Render
Shell and run ``scripts/import_olympiad.py`` manually; this module
removes that manual step by inlining the importer's idempotent
upsert/replace logic.

Idempotency contract (matches scripts/import_olympiad.py)
---------------------------------------------------------
* theory:    upsert by ``method_code``
* probniks:  upsert by ``code`` (also replaces ProbnikTheory links)
* tasks:     delete-then-insert per probnik (file = source of truth)

Therefore calling this on every boot is safe: with the same JSON
fixtures the work amounts to no-op writes.

Failures NEVER abort app boot — the catch-all wraps everything and
rolls back the session on error.
"""
from __future__ import annotations

import json
import os
import time


DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "olympiads",
)

PROBNIKS_JSON = os.path.join(DATA_DIR, "vsosh_9_2027_probniks.json")
TASKS_JSON = os.path.join(DATA_DIR, "vsosh_9_2027_tasks.json")
THEORY_JSON = os.path.join(DATA_DIR, "vsosh_9_2027_theory.json")


def _load_list(path):
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return None
    return data


def run_v4_force_import(app, db):
    """Run the v4 importer logic against the live DB.

    Args:
        app: Flask application (for app_context).
        db:  SQLAlchemy() instance.
    """
    flag = os.environ.get("VSOSH9_2027_FORCE_IMPORT", "1").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        print("[VSOSH9-V4] disabled by env VSOSH9_2027_FORCE_IMPORT")
        return

    probniks_raw = _load_list(PROBNIKS_JSON)
    tasks_raw = _load_list(TASKS_JSON)
    theory_raw = _load_list(THEORY_JSON)
    if probniks_raw is None or tasks_raw is None or theory_raw is None:
        print(
            "[VSOSH9-V4] fixtures missing or malformed, skipping. "
            "probniks=%s tasks=%s theory=%s" % (
                "ok" if probniks_raw is not None else "MISSING",
                "ok" if tasks_raw is not None else "MISSING",
                "ok" if theory_raw is not None else "MISSING",
            )
        )
        return

    # Lazy imports: avoid circular import with app.py.
    try:
        from models_olympiad import (
            Probnik,
            OlympiadTask,
            TheoryBlock,
            ProbnikTheory,
        )
    except Exception as e:
        print("[VSOSH9-V4] models import failed: %r" % (e,))
        return

    # Pydantic validation is optional — we already trust the file because
    # it was committed by humans and verified by scripts/_check_v4_state.
    # Skipping it keeps boot time lower and avoids a hard pydantic dep
    # at startup. (The CLI importer still runs full validation.)

    t0 = time.time()
    try:
        with app.app_context():
            t_created, t_updated = _upsert_theory(db, TheoryBlock, theory_raw)
            code_to_id, p_created, p_updated = _upsert_probniks(
                db, Probnik, ProbnikTheory, TheoryBlock, probniks_raw,
            )
            tasks_deleted, tasks_inserted = _replace_tasks(
                db, OlympiadTask, tasks_raw, code_to_id,
            )
            db.session.commit()
        dt = time.time() - t0
        print(
            "[VSOSH9-V4] import OK in %.1fs: theory(+%d/~%d) "
            "probniks(+%d/~%d) tasks(del %d -> ins %d)" % (
                dt, t_created, t_updated, p_created, p_updated,
                tasks_deleted, tasks_inserted,
            )
        )
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        print("[VSOSH9-V4] import FAILED (non-fatal): %r" % (e,))


# ─── Upsert helpers (inlined from scripts/import_olympiad.py) ──────────────────

def _upsert_theory(db, TheoryBlock, items):
    """Upsert TheoryBlock by method_code. Returns (created, updated)."""
    created = 0
    updated = 0
    for item in items:
        code = item.get("method_code")
        if not code:
            continue
        row = TheoryBlock.query.filter_by(method_code=code).first()
        if row is None:
            row = TheoryBlock(method_code=code)
            db.session.add(row)
            created += 1
        else:
            updated += 1
        # Update only fields actually present in the JSON; do not wipe
        # editable text with None.
        for fld in (
            "method_name", "section", "definition_md", "main_theorems_md",
            "typical_techniques_md", "triggers_md", "worked_example_md",
            "pitfalls_md",
        ):
            v = item.get(fld)
            if v is not None:
                setattr(row, fld, v)
        rel = item.get("related_methods")
        if rel is not None:
            row.related_methods = list(rel)
    db.session.flush()
    return created, updated


def _upsert_probniks(db, Probnik, ProbnikTheory, TheoryBlock, items):
    created = 0
    updated = 0
    code_to_id = dict()
    for item in items:
        code = item.get("code")
        if not code:
            continue
        row = Probnik.query.filter_by(code=code).first()
        if row is None:
            row = Probnik(code=code)
            db.session.add(row)
            created += 1
        else:
            updated += 1
        row.type = item.get("type", "topic")
        row.number = int(item.get("number", 0) or 0)
        row.title = item.get("title") or code
        row.description = item.get("description")
        row.competition = item.get("competition", "ВсОШ")
        row.grade = int(item.get("grade", 9) or 9)
        row.season_year = int(item.get("season_year", 2027) or 2027)
        row.duration_minutes = item.get("duration_minutes")
        row.max_score = item.get("max_score")
        row.threshold_prize = item.get("threshold_prize")
        row.threshold_winner = item.get("threshold_winner")
        row.sort_order = int(item.get("sort_order", 0) or 0)
        row.is_published = bool(item.get("is_published", True))
        db.session.flush()
        code_to_id[code] = row.id
        ProbnikTheory.query.filter_by(probnik_id=row.id).delete()
        for link in (item.get("theory") or []):
            mc = link.get("method_code") if isinstance(link, dict) else None
            if not mc:
                continue
            tb = TheoryBlock.query.filter_by(method_code=mc).first()
            if tb is None:
                continue
            order = link.get("order", 0) if isinstance(link, dict) else 0
            db.session.add(ProbnikTheory(
                probnik_id=row.id,
                theory_block_id=tb.id,
                display_order=int(order or 0),
            ))
        db.session.flush()
    return code_to_id, created, updated


def _replace_tasks(db, OlympiadTask, items, probnik_code_to_id):
    grouped = dict()
    for t in items:
        pc = t.get("probnik_code")
        if not pc:
            continue
        grouped.setdefault(pc, []).append(t)

    deleted = 0
    inserted = 0
    for code, tasks in grouped.items():
        probnik_id = probnik_code_to_id.get(code)
        if not probnik_id:
            # Unknown probnik_code — skip this group silently rather than
            # raise: in production we'd rather load partial than crash boot.
            continue
        old_count = OlympiadTask.query.filter_by(probnik_id=probnik_id).count()
        if old_count:
            OlympiadTask.query.filter_by(probnik_id=probnik_id).delete()
            deleted += old_count
        for t in tasks:
            db.session.add(OlympiadTask(
                probnik_id=probnik_id,
                number=str(t.get("number", "")),
                sort_order=int(t.get("sort_order", 0) or 0),
                difficulty=t.get("difficulty"),
                method_primary=t.get("method_primary") or "A1",
                method_secondary=t.get("method_secondary"),
                condition_md=t.get("condition_md") or "",
                idea_md=t.get("idea_md") or "",
                solution_md=t.get("solution_md") or "",
                answer=t.get("answer"),
                source_prototype=t.get("source_prototype"),
                estimated_minutes=t.get("estimated_minutes"),
                max_score=int(t.get("max_score", 7) or 7),
            ))
            inserted += 1
    db.session.flush()
    return deleted, inserted
