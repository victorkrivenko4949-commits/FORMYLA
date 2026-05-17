# -*- coding: utf-8 -*-
"""Replace ALL adaptive tasks in instance/formyla.db with the new dataset
formyla_adaptive_full_7245_with_grade11_rechecked.json.

Run:
    python scripts/replace_adaptive_with_formyla_full.py
    python scripts/replace_adaptive_with_formyla_full.py --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "instance", "formyla.db")
DEFAULT_SRC = r"C:/Users/Victor/Downloads/formyla_adaptive_full_7245_with_grade11_rechecked.json"
BACKUP_DIR = os.path.join(ROOT, "adaptive_data", "_backups")

COLS = ["class_level", "difficulty_level", "topic", "subtopic", "task_text", "solution", "criteria_1_point", "criteria_2_points", "correct_answer", "is_flagged", "reports_count", "flagged_reason", "attempts_count", "solves_count", "actual_solve_rate", "suggested_level", "needs_reclassification", "last_calibrated_at", "created_at"]

SUBJECT_PREFIX = {
    "algebra":       "\u0410\u043b\u0433\u0435\u0431\u0440\u0430",
    "geometry":      "\u0413\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044f",
    "combinatorics": "\u041a\u043e\u043c\u0431\u0438\u043d\u0430\u0442\u043e\u0440\u0438\u043a\u0430",
    "number_theory": "\u0422\u0435\u043e\u0440\u0438\u044f \u0447\u0438\u0441\u0435\u043b",
    "logic":         "\u041b\u043e\u0433\u0438\u043a\u0430. \u0420\u044b\u0446\u0430\u0440\u0438 \u0438 \u043b\u0436\u0435\u0446\u044b",
    "set_theory":    "\u041a\u043e\u043c\u0431\u0438\u043d\u0430\u0442\u043e\u0440\u0438\u043a\u0430 (\u0442\u0435\u043e\u0440\u0438\u044f \u043c\u043d\u043e\u0436\u0435\u0441\u0442\u0432)",
}


def domain_to_prefix(domain):
    d = (domain or "").lower()
    if d.startswith("algebra") or d.startswith("linear_functions") or d.startswith("functions_inequalities") or d == "polynomials" or d == "exponential_logarithmic" or d == "trigonometry" or d == "calculus" or d == "inequalities":
        return SUBJECT_PREFIX["algebra"]
    if d == "natural_numbers" or d.startswith("fractions") or d == "integers_coordinates":
        return SUBJECT_PREFIX["algebra"]
    if d.startswith("geometry") or d == "stereometry" or d == "circles_measurement":
        return SUBJECT_PREFIX["geometry"]
    if d.startswith("combinator") or d == "counting_probability_8" or d == "binomial_coefficients" or d == "extremal_combinatorics" or d == "pigeonhole" or d == "graph_theory":
        return SUBJECT_PREFIX["combinatorics"]
    if d == "olympiad_logic_combinatorics" or d == "number_theory_combinatorics_7":
        return SUBJECT_PREFIX["combinatorics"]
    if d.startswith("number_theory") or d == "divisibility" or d == "modular_arithmetic":
        return SUBJECT_PREFIX["number_theory"]
    if d.startswith("logic") or d.startswith("olympiad_logic") or d == "invariants" or d == "set_theory":
        return SUBJECT_PREFIX["logic"]
    return SUBJECT_PREFIX["algebra"]


def make_topic(task):
    subj = (task.get("subject") or "").strip().lower()
    raw_topic = (task.get("topic") or "").strip()
    if subj == "math":
        prefix = domain_to_prefix(task.get("domain") or "")
    else:
        prefix = SUBJECT_PREFIX.get(subj, SUBJECT_PREFIX["algebra"])
    if raw_topic:
        return prefix + ". " + raw_topic
    return prefix


def backup_existing(conn, db_path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='adaptive_tasks'")
    if not cur.fetchone():
        print("[backup] adaptive_tasks table does not exist yet, nothing to back up.")
        return
    cur.execute("SELECT * FROM adaptive_tasks")
    rows = cur.fetchall()
    if rows:
        col_names = [c[0] for c in cur.description]
        data = [dict(zip(col_names, r)) for r in rows]
        out = os.path.join(BACKUP_DIR, "adaptive_tasks_before_formyla_full_" + ts + ".json")
        with open(out, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, default=str)
        print("[backup] " + str(len(data)) + " rows -> " + out)
    else:
        print("[backup] adaptive_tasks is empty, skipping JSON dump.")
    db_bak = db_path + ".bak_before_formyla_full"
    try:
        shutil.copy2(db_path, db_bak)
        print("[backup] DB file snapshot -> " + db_bak)
    except Exception as e:
        print("[backup] DB file snapshot FAILED: " + str(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--dry-run", action="store_true", help="Show stats only, do not modify the DB.")
    ap.add_argument("--no-wipe", action="store_true", help="Do NOT delete existing rows (append only).")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print("DB not found: " + args.db)
        return 2
    if not os.path.exists(args.src):
        print("Source not found: " + args.src)
        return 2

    print("Loading " + args.src + " ...")
    with open(args.src, "r", encoding="utf-8") as fp:
        data = json.load(fp)
    tasks = data.get("tasks") or []
    print("Source tasks: " + str(len(tasks)))

    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    rows = []
    skipped_bad = 0
    seen_text = set()
    skipped_dup = 0
    per_gs = {}

    placeholder_c1 = "(\u043a\u0440\u0438\u0442\u0435\u0440\u0438\u0439 1 \u0431\u0430\u043b\u043b \u2014 \u043d\u0435 \u0437\u0430\u0434\u0430\u043d)"
    placeholder_c2 = "(\u043a\u0440\u0438\u0442\u0435\u0440\u0438\u0439 2 \u0431\u0430\u043b\u043b\u0430 \u2014 \u043d\u0435 \u0437\u0430\u0434\u0430\u043d)"
    placeholder_sol = "(\u0440\u0435\u0448\u0435\u043d\u0438\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442)"

    for t in tasks:
        if not isinstance(t, dict):
            skipped_bad += 1
            continue
        text = (t.get("statement") or "").strip()
        sol = (t.get("solution") or "").strip() or placeholder_sol
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
        if text in seen_text:
            skipped_dup += 1
            continue
        seen_text.add(text)

        topic = make_topic(t)
        subtopic = (t.get("topic") or "").strip() or None

        rows.append((
            grade_int, level_int, topic, subtopic,
            text, sol,
            placeholder_c1, placeholder_c2,
            ans,
            0, 0, None,
            0, 0, None,
            None, 0, None,
            now,
        ))

        key = (grade_int, (t.get("subject") or "").strip().lower())
        per_gs.setdefault(key, []).append(topic)

    print("Prepared rows: " + str(len(rows)))
    print("Skipped (bad/incomplete): " + str(skipped_bad))
    print("Skipped (duplicate statement): " + str(skipped_dup))

    print("\nDB.topic prefix coverage by (grade, subject):")
    for key in sorted(per_gs.keys()):
        topics = per_gs[key]
        prefixes = {}
        for tp in topics:
            p = tp.split(".", 1)[0].strip()
            prefixes[p] = prefixes.get(p, 0) + 1
        parts = []
        for p, n in sorted(prefixes.items(), key=lambda x: -x[1]):
            parts.append(p + "=" + str(n))
        summary = ", ".join(parts)
        print("  g" + str(key[0]).rjust(2) + " " + key[1].ljust(14) + ": " + str(len(topics)).rjust(5) + "  [" + summary + "]")

    if args.dry_run:
        print("\n[dry-run] no DB changes.")
        return 0

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    backup_existing(conn, args.db)

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    before_n = cur.fetchone()[0]
    print("\nBefore: " + str(before_n) + " rows in adaptive_tasks")

    if not args.no_wipe:
        cur.execute("DELETE FROM adaptive_tasks")
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name='adaptive_tasks'")
        except Exception:
            pass
        conn.commit()
        print("Wiped adaptive_tasks")

    placeholders = ", ".join(["?"] * len(COLS))
    sql = "INSERT INTO adaptive_tasks (" + ", ".join(COLS) + ") VALUES (" + placeholders + ")"
    cur.executemany(sql, rows)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    after_n = cur.fetchone()[0]
    print("Inserted: " + str(len(rows)))
    print("After: " + str(after_n) + " rows in adaptive_tasks")

    cur.execute("SELECT class_level, COUNT(*) FROM adaptive_tasks GROUP BY class_level ORDER BY class_level")
    print("\nBy class_level:")
    for c, n in cur.fetchall():
        print("  class " + str(c) + ": " + str(n))

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
