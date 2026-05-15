"""Fix double-backslash artifacts in adaptive_tasks introduced by JSON escaping.

Collapses any run of two or more backslashes to a single backslash so that
MathJax delimiters and LaTeX commands render correctly.
"""

from __future__ import annotations
import sqlite3
import re
import sys
import os

# Add parent dir for any imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "instance", "formyla.db")

FIELDS = ("task_text", "solution",
          "criteria_1_point", "criteria_2_points", "correct_answer")


def fix_text(s: str) -> str:
    """Collapse any sequence of >=2 consecutive backslashes to a single
    backslash. This is safe for our content because:
    - LaTeX commands use single backslash (\\frac, \\(, \\), \\[, \\])
    - Real Python escapes (\\n, \\t) are not used in plain task text
    - Path separators on web are forward slashes
    """
    if not s:
        return s
    # Replace runs of 2+ backslashes with single backslash
    fixed = re.sub(r"\\{2,}", r"\\", s)
    return fixed


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM adaptive_tasks")
    total = cur.fetchone()[0]
    print(f"Total tasks: {total}")

    # Count rows that have any double-backslash in any field
    where = " OR ".join(f"{f} LIKE ?" for f in FIELDS)
    params = [r"%\\%"] * len(FIELDS)
    cur.execute(f"SELECT COUNT(*) FROM adaptive_tasks WHERE {where}", params)
    affected = cur.fetchone()[0]
    print(f"Rows with double backslashes: {affected}")

    if affected == 0:
        print("Nothing to fix.")
        return

    # Fetch all affected rows
    cur.execute(f"SELECT id, {', '.join(FIELDS)} FROM adaptive_tasks WHERE {where}",
                params)
    rows = cur.fetchall()
    print(f"Fetched {len(rows)} rows for processing")

    updates = []
    for row in rows:
        rid = row[0]
        original = row[1:]
        fixed = tuple(fix_text(v) if v else v for v in original)
        if fixed != original:
            updates.append((*fixed, rid))

    print(f"Rows changed: {len(updates)}")

    if updates:
        set_clause = ", ".join(f"{f}=?" for f in FIELDS)
        cur.executemany(
            f"UPDATE adaptive_tasks SET {set_clause} WHERE id=?",
            updates,
        )
        conn.commit()
        print(f"Committed {len(updates)} updates")

    # Verify
    cur.execute(f"SELECT COUNT(*) FROM adaptive_tasks WHERE {where}", params)
    remaining = cur.fetchone()[0]
    print(f"Rows still containing double backslashes: {remaining}")

    conn.close()


if __name__ == "__main__":
    main()
