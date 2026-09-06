#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sqlite3
import sys

db = "instance/formyla.db"
job_id = int(sys.argv[1])
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
r = con.execute(
    "SELECT id, status, current_stage, generation_mode, error, "
    "aux_dropped_reason, answer_verdict, trust_level, solver_answer, "
    "measured_answer FROM figure_build_jobs WHERE id=?",
    (job_id,),
).fetchone()
if r is None:
    print("NOT FOUND")
else:
    d = dict(r)
    # safe ascii output
    for k, v in d.items():
        if isinstance(v, str):
            v = v.encode("ascii", "replace").decode("ascii")
        print(f"{k}={v}")
