#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Show 3 fresh manual_review_queue rows from level=6."""
import os
import sys
import json

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app
from models import db
from sqlalchemy import text


def main():
    with app.app_context():
        cols_rows = db.session.execute(text("PRAGMA table_info(manual_review_queue)")).fetchall()
        if not cols_rows:
            print("manual_review_queue: table missing or no columns")
            return 1
        col_names = [r[1] for r in cols_rows]
        print("manual_review_queue columns:")
        for cn in col_names:
            print("  -", cn)
        print()

        dist = db.session.execute(text(
            "SELECT level, COUNT(*) FROM manual_review_queue GROUP BY level ORDER BY level"
        )).fetchall()
        print("=== distribution by level ===")
        for lvl, n in dist:
            print("  level=%s: %s" % (lvl, n))
        print()

        examples = db.session.execute(text(
            "SELECT * FROM manual_review_queue WHERE level = 6 ORDER BY id DESC LIMIT 3"
        )).fetchall()
        if not examples:
            print("No level=6 rows in manual_review_queue")
            return 0

        print("=== 3 EXAMPLES from level=6 ===")
        for i, row in enumerate(examples, 1):
            d = dict(row._mapping) if hasattr(row, "_mapping") else dict(zip(col_names, row))
            print()
            print("--- EXAMPLE %d ---" % i)
            for key in col_names:
                val = d.get(key)
                if isinstance(val, str) and len(val) > 600:
                    val = val[:600] + "..."
                print("  %s: %s" % (key, val))
        return 0


if __name__ == "__main__":
    sys.exit(main())