# -*- coding: utf-8 -*-
"""CH21 A2: показать СЫРЫЕ тексты нарушений для двух failed base-задач."""
import io
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from geometric_engine.engine import GeometricEngine  # noqa: E402

DB = os.path.join("output", "ch19", "_pilot.db")


def raw_violations(plan, attempts=3):
    engine = GeometricEngine()
    engine.settings.semantic_colors = True
    engine.settings.auto_fit = True
    canvas = plan.get("canvas", {})
    w = canvas.get("width", 600)
    h = canvas.get("height", 500)
    margin = canvas.get("margin", 40)

    all_v = Counter()
    examples = {}
    for attempt in range(attempts):
        seed = 42 + attempt * 137
        try:
            svg, ctx = engine.build(plan, seed=seed)
        except Exception as e:
            all_v[f"EXC:{type(e).__name__}:{e}"] += 1
            continue
        check = run_all_checks_import(ctx, w, h, margin, engine.settings)
        for v in check.violations:
            all_v[v] += 1
            examples.setdefault(v, 0)
    return all_v, examples


def run_all_checks_import(ctx, w, h, margin, settings):
    from geometric_engine.engine import run_all_checks
    return run_all_checks(ctx, w, h, margin, settings)


def main():
    import sqlite3
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    for r in con.execute("SELECT id, base_plan_json, error, status FROM figure_build_jobs"):
        if r["status"] != "failed" or not r["base_plan_json"]:
            continue
        plan = json.loads(r["base_plan_json"])
        all_v, _ = raw_violations(plan)
        print("=" * 100)
        print(f"job_id={r['id']} error={r['error']}")
        print(f"constructions={len(plan.get('constructions', []))}")
        for v, n in all_v.most_common(10):
            print(f"  [{n}x] {v}")
    con.close()


if __name__ == "__main__":
    main()
