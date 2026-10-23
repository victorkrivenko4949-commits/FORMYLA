#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выгрузить solution_json / base_plan_json job'а в файл.

Usage: python scripts/recon/dump_solution.py <job_id>
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT_DIR, exist_ok=True)


def _db_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "instance", "formyla.db",
    )


def main():
    job_id = int(sys.argv[1])
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT id, status, generation_mode, current_stage, "
        "answer_verdict, trust_level, aux_source, aux_usefulness, "
        "aux_dropped_reason, aux_status, solver_answer, measured_answer, "
        "error, solution_json, base_plan_json, aux_plan_json "
        "FROM figure_build_jobs WHERE id=?", (job_id,),
    ).fetchone()
    if row is None:
        print(f"job {job_id} not found")
        return

    meta = {k: row[k] for k in row.keys() if k not in
            ("solution_json", "base_plan_json", "aux_plan_json")}

    out = {
        "meta": meta,
        "solution_json": json.loads(row["solution_json"]) if row["solution_json"] else None,
        "base_plan_json": json.loads(row["base_plan_json"]) if row["base_plan_json"] else None,
        "aux_plan_json": json.loads(row["aux_plan_json"]) if row["aux_plan_json"] else None,
    }
    path = os.path.join(OUT_DIR, f"job_{job_id}_solution.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"written {path}")


if __name__ == "__main__":
    main()
