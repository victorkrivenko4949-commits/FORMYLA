# -*- coding: utf-8 -*-
"""Import the fixed adaptive task bank into instance/formyla.db.

Strategy: FULL REPLACE.
  1. JSON dump of current `adaptive_tasks` to
     adaptive_data/_backups/adaptive_tasks_before_<tag>_<ts>.json (ensure_ascii=False).
  2. File-level copy of the SQLite DB to <db>.bak_before_<tag>.
  3. DELETE FROM adaptive_tasks; reset sqlite_sequence.
  4. INSERT all tasks from the source JSON (statement->task_text,
     answer->correct_answer, solution->solution, grade->class_level,
     level->difficulty_level, subject(en)->subject, topic mapped to "<Префикс>. <topic>"
     to match the registry used by the picker).
  5. Print before/after counts, distribution by class_level, and a coverage report
     for every (class_level, topic) pair with HOLES < 25 highlighted.

Usage:
    python scripts/import_adaptive_bank.py --dry-run
    python scripts/import_adaptive_bank.py
    python scripts/import_adaptive_bank.py --src adaptive_data/adaptive_full_9120_fixed.json \\
                                           --db instance/formyla.db --tag 9120_fixed

Defaults assume the file already sits at adaptive_data/adaptive_full_9120_fixed.json
and the DB is instance/formyla.db.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "instance", "formyla.db")
DEFAULT_SRC = os.path.join(ROOT, "adaptive_data", "adaptive_full_9120_fixed.json")
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")

# Columns we explicitly write. NB: id is autoincrement, we let SQLite assign it.
COLS = [
    "class_level", "difficulty_level", "topic", "subtopic",
    "task_text", "solution", "criteria_1_point", "criteria_2_points",
    "correct_answer", "is_flagged", "reports_count", "flagged_reason",
    "attempts_count", "solves_count", "actual_solve_rate",
    "suggested_level", "needs_reclassification", "last_calibrated_at",
    "subject",
    "created_at",
]

# subject(en) -> Russian topic-prefix used by the picker / registry.
SUBJECT_PREFIX = {
    "algebra":       "Алгебра",
    "geometry":      "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "logic":         "Комбинаторика",  # logic items live under the combinatorics super-topic in the UI
    "set_theory":    "Комбинаторика",
}

PLACEHOLDER_C1 = "(критерий 1 балл — не задан)"
PLACEHOLDER_C2 = "(критерий 2 балла — не задан)"
PLACEHOLDER_SOL = "(решение отсутствует)"


def make_topic(task: dict) -> str:
    """Build the DB `topic` field as "<Префикс>. <topic-from-json>".

    If the JSON `topic` already starts with the Russian prefix (because the
    file was pre-formatted), we return it unchanged. Otherwise we attach the
    prefix matching `subject`.
    """
    subj = (task.get("subject") or "").strip().lower()
    raw_topic = (task.get("topic") or "").strip()
    prefix = SUBJECT_PREFIX.get(subj, "Алгебра")
    if raw_topic:
        # Already prefixed?
        for p in set(SUBJECT_PREFIX.values()):
            if raw_topic.startswith(p + ".") or raw_topic.startswith(p + " ."):
                return raw_topic
            if raw_topic == p:
                return p
        return f"{prefix}. {raw_topic}"
    return prefix


def load_tasks(src: str):
    if not os.path.exists(src):
        print(f"[ERROR] Source not found: {src}")
        sys.exit(2)
    with open(src, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    if isinstance(data, dict):
        tasks = data.get("tasks") or data.get("items") or []
    elif isinstance(data, list):
        tasks = data
    else:
        print(f"[ERROR] Unexpected JSON top-level type: {type(data).__name__}")
        sys.exit(2)
    return tasks


def backup_existing(conn: sqlite3.Connection, db_path: str, tag: str) -> None:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_tasks'"
    )
    if not cur.fetchone():
        print("[backup] adaptive_tasks table does not exist yet — nothing to back up.")
        return
    cur.execute("SELECT * FROM adaptive_tasks")
    rows = cur.fetchall()
    col_names = [c[0] for c in cur.description]
    if rows:
        data = [dict(zip(col_names, r)) for r in rows]
        out = os.path.join(BACKUP_DIR, f"adaptive_tasks_before_{tag}_{ts}.json")
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, default=str)
        print(f"[backup] {len(data)} rows -> {out}")
    else:
        print("[backup] adaptive_tasks is empty, skipping JSON dump.")
    db_bak = f"{db_path}.bak_before_{tag}"
    try:
        shutil.copy2(db_path, db_bak)
        print(f"[backup] DB file snapshot -> {db_bak}")
    except Exception as e:
        print(f"[backup] DB file snapshot FAILED: {e}")


def print_db_stats(cur: sqlite3.Cursor, label: str) -> None:
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"\n[{label}] total rows: {total}")
    cur.execute(
        "SELECT class_level, COUNT(*) FROM adaptive_tasks "
        "GROUP BY class_level ORDER BY class_level"
    )
    print(f"[{label}] by class_level:")
    for c, n in cur.fetchall():
        print(f"  class {c}: {n}")

    cur.execute(
        "SELECT COALESCE(SUM(attempts_count),0), COALESCE(SUM(solves_count),0), "
        "COALESCE(SUM(reports_count),0), COALESCE(SUM(is_flagged),0) "
        "FROM adaptive_tasks"
    )
    att, solv, rep, flag = cur.fetchone()
    print(f"[{label}] aggregate stats: attempts={att} solves={solv} reports={rep} flagged={flag}")


def coverage_report(cur: sqlite3.Cursor, title: str, threshold: int = 25) -> None:
    cur.execute(
        "SELECT class_level, topic, COUNT(*) FROM adaptive_tasks "
        "GROUP BY class_level, topic ORDER BY class_level, topic"
    )
    rows = cur.fetchall()
    print(f"\n=== {title}: (class_level, topic) coverage ===")
    print(f"  total (class, topic) cells: {len(rows)}")
    holes = [(c, t, n) for c, t, n in rows if n < threshold]
    print(f"  cells with count < {threshold}: {len(holes)}")
    if holes:
        print(f"  --- holes (count < {threshold}) ---")
        for c, t, n in holes:
            print(f"    class {c:>2}  n={n:>4}  topic={t}")
    else:
        print(f"  ALL cells >= {threshold} — adaptive test has enough room.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--tag", default="9120_fixed",
                    help="tag used in backup file names")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print before/after stats from the source, do not touch DB")
    ap.add_argument("--threshold", type=int, default=25,
                    help="coverage threshold for hole detection (default 25)")
    args = ap.parse_args()

    print(f"DB:  {args.db}")
    print(f"SRC: {args.src}")

    if not os.path.exists(args.db):
        print(f"[ERROR] DB not found: {args.db}")
        return 2

    tasks = load_tasks(args.src)
    print(f"Source tasks: {len(tasks)}")

    # ---- Build rows ----
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    rows = []
    skipped_bad = 0
    skipped_dup_text = 0  # exact statement dup INSIDE THE SOURCE FILE — we keep them (cross-level)
    by_grade = Counter()
    by_subject = Counter()
    by_grade_topic = Counter()

    for t in tasks:
        if not isinstance(t, dict):
            skipped_bad += 1
            continue
        text = (t.get("statement") or "").strip()
        sol = (t.get("solution") or "").strip() or PLACEHOLDER_SOL
        ans = (t.get("answer") or "").strip() or None
        grade = t.get("grade")
        level = t.get("level")
        if not text or grade is None or level is None:
            skipped_bad += 1
            continue
        try:
            grade_int = int(grade)
            level_int = int(level)
        except (TypeError, ValueError):
            skipped_bad += 1
            continue
        topic = make_topic(t)
        subtopic = (t.get("topic") or "").strip() or None
        subj = (t.get("subject") or "").strip().lower() or None

        rows.append((
            grade_int, level_int, topic, subtopic,
            text, sol,
            PLACEHOLDER_C1, PLACEHOLDER_C2,
            ans,
            0, 0, None,           # is_flagged, reports_count, flagged_reason
            0, 0, None,           # attempts_count, solves_count, actual_solve_rate
            None, 0, None,        # suggested_level, needs_reclassification, last_calibrated_at
            subj,
            now,
        ))
        by_grade[grade_int] += 1
        by_subject[subj] += 1
        by_grade_topic[(grade_int, topic)] += 1

    print(f"Prepared rows: {len(rows)}")
    print(f"Skipped (bad/incomplete): {skipped_bad}")

    print("\n[source preview] by grade:")
    for g in sorted(by_grade):
        print(f"  grade {g}: {by_grade[g]}")
    print("\n[source preview] by subject:")
    for s in sorted(by_subject, key=lambda x: (x is None, x or "")):
        print(f"  {s!r}: {by_subject[s]}")

    print(f"\n[source preview] (grade, topic) cells: {len(by_grade_topic)}")
    holes_src = [(g, t, n) for (g, t), n in by_grade_topic.items() if n < args.threshold]
    holes_src.sort()
    print(f"[source preview] cells with count < {args.threshold}: {len(holes_src)}")
    if holes_src:
        print("  --- source-side holes (count < threshold) ---")
        for g, t, n in holes_src:
            print(f"    grade {g:>2}  n={n:>4}  topic={t}")

    # ---- DB BEFORE ----
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    print_db_stats(cur, "DB BEFORE")
    coverage_report(cur, "DB BEFORE", threshold=args.threshold)

    if args.dry_run:
        print("\n[dry-run] No DB changes. Aborting before write.")
        conn.close()
        return 0

    # ---- BACKUP ----
    backup_existing(conn, args.db, tag=args.tag)

    # ---- WIPE + INSERT ----
    cur.execute("DELETE FROM adaptive_tasks")
    try:
        cur.execute("DELETE FROM sqlite_sequence WHERE name='adaptive_tasks'")
    except Exception:
        pass
    conn.commit()
    print("\nWiped adaptive_tasks")

    placeholders = ", ".join(["?"] * len(COLS))
    sql = f"INSERT INTO adaptive_tasks ({', '.join(COLS)}) VALUES ({placeholders})"
    cur.executemany(sql, rows)
    conn.commit()
    print(f"Inserted: {len(rows)}")

    # ---- DB AFTER ----
    print_db_stats(cur, "DB AFTER")
    coverage_report(cur, "DB AFTER", threshold=args.threshold)

    conn.close()
    print("\nDONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
