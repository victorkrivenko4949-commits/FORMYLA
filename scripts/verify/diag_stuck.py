#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диагностика заедающей генерации."""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
db = os.path.join(BASE, "instance", "formyla.db")
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row

out = {}

# Последние job'ы
rows = con.execute(
    "SELECT id, status, current_stage, generation_mode, created_at, updated_at, "
    "error, aux_dropped_reason, answer_verdict, trust_level "
    "FROM figure_build_jobs ORDER BY id DESC LIMIT 30"
).fetchall()
out["recent_jobs"] = [dict(r) for r in rows]

# Незавершённые (застрявшие)
stuck = con.execute(
    "SELECT id, status, current_stage, generation_mode, created_at, updated_at, "
    "error FROM figure_build_jobs "
    "WHERE status NOT IN ('done','failed') ORDER BY id DESC LIMIT 50"
).fetchall()
out["stuck_jobs"] = [dict(r) for r in stuck]

# Счётчики по статусам
counts = con.execute(
    "SELECT status, COUNT(*) c FROM figure_build_jobs GROUP BY status"
).fetchall()
out["status_counts"] = [dict(r) for r in counts]

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out",
                       "diag_stuck.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2, default=str)

print(json.dumps(out, ensure_ascii=False, default=str)[:3000])
