"""Import merged adaptive tasks into the SQLite DB used by the Flask app.

Reads adaptive_data/_merged_inventory.json (produced by inventory_adaptive_sources.py)
and inserts records into the `adaptive_tasks` table via raw SQL (no need to
spin up the full Flask app).

Usage:
    python scripts/import_adaptive_to_db.py [--db instance/formyla.db] [--wipe]

By default appends; with --wipe truncates the table first.
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys
from datetime import datetime

DEFAULT_DB = os.path.join("instance", "formyla.db")
SRC = os.path.join("adaptive_data", "_merged_inventory.json")

COLS = [
    "class_level", "difficulty_level", "topic", "subtopic",
    "task_text", "solution", "criteria_1_point", "criteria_2_points",
    "correct_answer", "is_flagged", "reports_count", "flagged_reason",
    "attempts_count", "solves_count", "actual_solve_rate",
    "suggested_level", "needs_reclassification", "last_calibrated_at",
    "created_at",
]

def to_int(v, default=None):
    if v is None or v == "": return default
    try: return int(float(v))
    except Exception: return default

def to_float(v, default=None):
    if v is None or v == "": return default
    try: return float(v)
    except Exception: return default

def to_bool_int(v, default=0):
    if v is None: return default
    if isinstance(v, bool): return 1 if v else 0
    if isinstance(v, (int, float)): return 1 if v else 0
    s = str(v).strip().lower()
    if s in ("1","true","yes","y","да"): return 1
    if s in ("0","false","no","n","нет",""): return 0
    return default

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--wipe", action="store_true",
                    help="DELETE FROM adaptive_tasks before insert")
    ap.add_argument("--min-class", type=int, default=1,
                    help="skip records with class_level below this (default 1)")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"DB not found: {args.db}"); sys.exit(2)
    if not os.path.exists(args.src):
        print(f"Source not found: {args.src}"); sys.exit(2)

    with open(args.src, "r", encoding="utf-8") as f:
        records = json.load(f)
    print(f"Source records: {len(records)}")

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    # confirm table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_tasks'")
    if not cur.fetchone():
        print("Table adaptive_tasks does not exist in this DB. Run the Flask app once to create schema.")
        sys.exit(2)

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    print(f"Before: {cur.fetchone()[0]} rows in adaptive_tasks")

    if args.wipe:
        cur.execute("DELETE FROM adaptive_tasks")
        conn.commit()
        print("Wiped adaptive_tasks")

    # de-dup against existing rows by task_text
    cur.execute("SELECT task_text FROM adaptive_tasks")
    existing = {row[0] for row in cur.fetchall()}
    print(f"Existing task_text in DB: {len(existing)}")

    inserted = skipped_dup = skipped_bad = 0
    rows = []
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")

    for r in records:
        if not isinstance(r, dict): skipped_bad += 1; continue
        text = (r.get("task_text") or "").strip()
        topic = (r.get("topic") or "").strip()
        sol   = (r.get("solution") or "").strip() or "(решение отсутствует)"
        cl    = to_int(r.get("class_level"))
        dl    = to_int(r.get("difficulty_level"))
        if not text or not topic or cl is None or dl is None:
            skipped_bad += 1; continue
        if cl < args.min_class:
            skipped_bad += 1; continue
        if text in existing:
            skipped_dup += 1; continue
        existing.add(text)

        rows.append((
            cl, dl, topic, r.get("subtopic"),
            text, sol,
            r.get("criteria_1_point") or "(критерий 1 балл — не задан)",
            r.get("criteria_2_points") or "(критерий 2 балла — не задан)",
            r.get("correct_answer") or r.get("answer"),
            to_bool_int(r.get("is_flagged"), 0),
            to_int(r.get("reports_count"), 0),
            r.get("flagged_reason"),
            to_int(r.get("attempts_count"), 0),
            to_int(r.get("solves_count"), 0),
            to_float(r.get("actual_solve_rate")),
            to_int(r.get("suggested_level")),
            to_bool_int(r.get("needs_reclassification"), 0),
            r.get("last_calibrated_at"),
            r.get("created_at") or now,
        ))
        inserted += 1

    placeholders = ", ".join(["?"] * len(COLS))
    sql = f"INSERT INTO adaptive_tasks ({', '.join(COLS)}) VALUES ({placeholders})"
    cur.executemany(sql, rows)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    after = cur.fetchone()[0]
    print(f"\nInserted: {inserted}")
    print(f"Skipped (dup): {skipped_dup}")
    print(f"Skipped (bad/no class/topic): {skipped_bad}")
    print(f"After: {after} rows in adaptive_tasks")

    cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level")
    print("\nBy class_level:")
    for c, n in cur.fetchall():
        print(f"  class {c}: {n}")

    conn.close()

if __name__ == "__main__":
    main()
